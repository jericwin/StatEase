from __future__ import annotations

import io
import sqlite3
import time
import uuid
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import sqlglot
from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import get_settings
from ..deps import DB, CurrentUser, audit, get_project, require_role
from ..dev import sql_engine
from ..dev.samples import EXAMPLE_QUERIES, ensure_sample_db
from ..errors import AppError, NotFound
from ..models import DbConnection, QueryHistory, SavedQuery, User
from ..security import encrypt_secret
from ..services import create_dataset
from ..storage import new_relative_path, resolve

router = APIRouter(prefix="/sql", tags=["sql workbench"])


def _dev(user: User) -> None:
    require_role(user, "developer")


def conn_out(c: DbConnection) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "engine": c.engine, "host": c.host, "port": c.port, "database": c.database,
            "username": c.username, "has_password": bool(c.secret_encrypted), "allow_writes": c.allow_writes,
            "options": {k: v for k, v in (c.options_json or {}).items() if k in {"sslmode"}},
            "created_at": c.created_at.isoformat()}


def _conn(db, user: User, cid: int | None) -> DbConnection | None:
    if cid is None:
        return None
    c = db.get(DbConnection, cid)
    if c is None or (c.owner_id != user.id and user.role != "admin"):
        raise NotFound("Connection")
    return c


def _target(db, user, project_id: int | None, connection_id: int | None):
    conn = _conn(db, user, connection_id)
    project = get_project(db, user, project_id) if project_id and conn is None else None
    return conn, project


# --------------------------------------------------------------------------- connections


class ConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    engine: str = Field(pattern="^(postgresql|mysql)$")
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str | None = Field(None, max_length=1000)
    sslmode: str | None = Field(None, pattern="^(disable|allow|prefer|require|verify-ca|verify-full)$")
    allow_writes: bool = False


class ConnectionPatch(BaseModel):
    name: str | None = Field(None, max_length=120)
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    allow_writes: bool | None = None


@router.get("/connections")
def list_connections(user: CurrentUser, db: DB):
    _dev(user)
    rows = db.scalars(select(DbConnection).where(DbConnection.owner_id == user.id).order_by(DbConnection.name))
    return {"items": [conn_out(c) for c in rows]}


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, user: CurrentUser, db: DB):
    _dev(user)
    if body.allow_writes:
        require_role(user, "admin")
    c = DbConnection(owner_id=user.id, name=body.name, engine=body.engine, host=body.host,
                     port=body.port or (5432 if body.engine == "postgresql" else 3306), database=body.database,
                     username=body.username, secret_encrypted=encrypt_secret(body.password) if body.password else None,
                     options_json={"sslmode": body.sslmode} if body.sslmode else {}, allow_writes=body.allow_writes)
    db.add(c)
    db.flush()
    audit(db, user, "connection.create", connection=c.id, engine=c.engine, host=c.host)
    db.commit()
    return conn_out(c)


@router.patch("/connections/{cid}")
def update_connection(cid: int, body: ConnectionPatch, user: CurrentUser, db: DB):
    _dev(user)
    c = _conn(db, user, cid)
    data = body.model_dump(exclude_unset=True)
    if data.get("allow_writes"):
        require_role(user, "admin")
    if "password" in data:
        c.secret_encrypted = encrypt_secret(data.pop("password")) if body.password else None
    for k, v in data.items():
        setattr(c, k, v)
    audit(db, user, "connection.update", connection=c.id, fields=[k for k in data])
    db.commit()
    return conn_out(c)


@router.delete("/connections/{cid}", status_code=204)
def delete_connection(cid: int, user: CurrentUser, db: DB):
    _dev(user)
    c = _conn(db, user, cid)
    if c.engine == "sqlite":
        try:
            (get_settings().sqlite_connections_dir / sql_engine.sqlite_path(c).rsplit("/", 1)[-1]).unlink(missing_ok=True)
        except AppError:
            pass
    audit(db, user, "connection.delete", connection=c.id)
    db.delete(c)
    db.commit()


@router.post("/connections/{cid}/test")
def test_connection(cid: int, user: CurrentUser, db: DB):
    _dev(user)
    c = _conn(db, user, cid)
    t0 = time.perf_counter()
    s = sql_engine.open_session(c, None)
    try:
        s.execute("SELECT 1", 1, 10)
    finally:
        s.close()
    return {"ok": True, "latency_ms": (time.perf_counter() - t0) * 1000}


@router.post("/connections/sqlite", status_code=201)
def create_sqlite(user: CurrentUser, db: DB, name: str = Form(...), file: UploadFile | None = File(None)):
    """Upload an existing SQLite database file, or create an empty one."""
    _dev(user)
    fname = f"{uuid.uuid4().hex}.sqlite"
    path = get_settings().sqlite_connections_dir / fname
    if file is not None:
        head = file.file.read(16)
        if head != b"SQLite format 3\x00":
            raise AppError("invalid_file", "The file is not a SQLite 3 database.", 400)
        with path.open("wb") as out:
            out.write(head)
            while chunk := file.file.read(1024 * 1024):
                out.write(chunk)
    else:
        sqlite3.connect(path).close()
    c = DbConnection(owner_id=user.id, name=name[:120], engine="sqlite", database=fname, allow_writes=file is None)
    db.add(c)
    db.flush()
    audit(db, user, "connection.create", connection=c.id, engine="sqlite")
    db.commit()
    return conn_out(c)


@router.post("/connections/{cid}/import-table", status_code=201)
def import_table(cid: int, user: CurrentUser, db: DB, table: str = Form(...), file: UploadFile = File(...)):
    """Load a CSV/Excel file into a table of a managed SQLite database."""
    _dev(user)
    import polars as pl

    from ..data import importer

    c = _conn(db, user, cid)
    if c.engine != "sqlite":
        raise AppError("unsupported", "Importing files as tables is available for SQLite connections.", 422)
    if not c.allow_writes:
        raise AppError("read_only", "Enable writes on this connection to import tables.", 403)
    meta = importer.stage_upload(file.filename or "upload.csv", file.file)
    try:
        lf, issues, _ = importer._lazy_frame(importer.staged(meta["upload_id"])[1], meta["format"],
                                             importer.ImportOptions())
        df = lf.collect()
    finally:
        importer.discard_upload(meta["upload_id"])
    name = sql_engine.table_name(table, set())
    con = sqlite3.connect(sql_engine.sqlite_path(c))
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name = ?", [name]).fetchone():
            raise AppError("table_exists", f"Table '{name}' already exists.", 409)
        type_map = {pl.Int64: "INTEGER", pl.Int32: "INTEGER", pl.Float64: "REAL", pl.Boolean: "INTEGER"}
        cols = ", ".join(f'"{n}" {type_map.get(t, "TEXT")}' for n, t in df.schema.items())
        con.execute(f'CREATE TABLE "{name}" ({cols})')
        placeholders = ", ".join("?" for _ in df.columns)
        rows = [[(v.isoformat() if hasattr(v, "isoformat") else v) for v in r] for r in df.iter_rows()]
        con.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', rows)
        con.commit()
    finally:
        con.close()
    audit(db, user, "connection.import_table", connection=c.id, table=name, rows=df.height)
    db.commit()
    return {"table": name, "rows": df.height, "issues": issues}


# --------------------------------------------------------------------------- queries


class QueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=200_000)
    project_id: int | None = None
    connection_id: int | None = None
    max_rows: int = Field(1000, ge=1, le=100_000)
    confirm: bool = False


@router.get("/schema")
def schema(user: CurrentUser, db: DB, project_id: int | None = None, connection_id: int | None = None):
    _dev(user)
    conn, project = _target(db, user, project_id, connection_id)
    s = sql_engine.open_session(conn, project)
    try:
        return {"tables": s.schema(), "dialect": s.dialect, "read_only": conn is None or not conn.allow_writes,
                "target": "workspace" if conn is None else conn.engine}
    finally:
        s.close()


@router.post("/format")
def format_sql(body: QueryIn, user: CurrentUser, db: DB):
    _dev(user)
    conn = _conn(db, user, body.connection_id)
    return {"sql": sql_engine.format_sql(body.sql, sql_engine.DIALECT[conn.engine if conn else "duckdb"])}


@router.post("/execute")
def execute(body: QueryIn, user: CurrentUser, db: DB):
    _dev(user)
    s = get_settings()
    conn, project = _target(db, user, body.project_id, body.connection_id)
    dialect = sql_engine.DIALECT[conn.engine if conn else "duckdb"]
    stmts = sql_engine.classify(body.sql, dialect)
    sql_engine.authorize(stmts, allow_writes=bool(conn and conn.allow_writes), is_admin=user.role == "admin",
                         confirmed=body.confirm, local=conn is None)
    risky = any(st.kind != "read" for st in stmts)
    session = sql_engine.open_session(conn, project, writable=risky)
    t0 = time.perf_counter()
    status, error, result = "completed", None, None
    max_rows = min(body.max_rows, s.sql_max_rows)
    try:
        messages = []
        for i, st in enumerate(stmts):
            # Run the original text for the last statement so dialect-specific syntax is preserved exactly.
            sql_text = body.sql if len(stmts) == 1 else st.sql
            result = session.execute(sql_text, max_rows, s.sql_timeout_seconds)
            if not result["columns"]:
                messages.append(f"Statement {i + 1} ({st.type}) completed"
                                + (f"; {result.get('rowcount')} row(s) affected." if result.get("rowcount", -1) >= 0
                                   else "."))
        result = result or {"columns": [], "rows": [], "truncated": False}
        result["messages"] = messages
    except AppError as exc:
        status, error = ("timeout" if exc.code == "sql_timeout" else "failed"), exc
    finally:
        session.close()
    duration = (time.perf_counter() - t0) * 1000
    db.add(QueryHistory(owner_id=user.id, project_id=project.id if project else None,
                        connection_id=conn.id if conn else None, body=body.sql[:20000], status=status,
                        row_count=len(result["rows"]) if result else None, duration_ms=duration,
                        error_message=error.message[:2000] if error else None))
    if risky:
        audit(db, user, "sql.write", project.id if project else None, connection=conn.id if conn else None,
              statements=[st.type for st in stmts], status=status)
    db.commit()
    if error:
        raise error
    return {**result, "row_count": len(result["rows"]), "duration_ms": duration, "statements": len(stmts),
            "max_rows": max_rows}


def _read_only_select(body_sql: str, dialect: str) -> None:
    stmts = sql_engine.classify(body_sql, dialect)
    if len(stmts) != 1 or stmts[0].kind != "read":
        raise AppError("select_required", "Use a single SELECT query for this action.", 422)


class SaveDatasetIn(BaseModel):
    sql: str = Field(min_length=1, max_length=200_000)
    project_id: int
    connection_id: int | None = None
    name: str = Field(min_length=1, max_length=200)


@router.post("/save-dataset", status_code=201)
def save_dataset(body: SaveDatasetIn, user: CurrentUser, db: DB):
    """Save a query result as a new analysis dataset; source datasets are never modified."""
    _dev(user)
    project = get_project(db, user, body.project_id)
    conn = _conn(db, user, body.connection_id)
    dialect = sql_engine.DIALECT[conn.engine if conn else "duckdb"]
    _read_only_select(body.sql, dialect)
    session = sql_engine.open_session(conn, project)
    rel = new_relative_path("datasets", ".parquet")
    limit = get_settings().analysis_max_rows
    rows = 0
    writer = None
    try:
        for batch in session.iter_batches(body.sql):
            if writer is None:
                writer = pq.ParquetWriter(resolve(rel), batch.schema, compression="zstd")
            rows += batch.num_rows
            if rows > limit:
                raise AppError("too_many_rows", f"The result exceeds {limit:,} rows. Add filters or aggregation.", 422)
            writer.write_batch(batch)
    except AppError:
        if writer:
            writer.close()
        resolve(rel).unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        if writer:
            writer.close()
        resolve(rel).unlink(missing_ok=True)
        raise AppError("sql_error", str(exc).split("\n")[0], 422) from exc
    finally:
        session.close()
    if writer is None:
        raise AppError("empty_result", "The query returned no columns.", 422)
    writer.close()
    if rows == 0:
        resolve(rel).unlink(missing_ok=True)
        raise AppError("empty_result", "The query returned no rows; nothing was saved.", 422)
    parent = None
    if conn is None:
        ws = sql_engine.DuckWorkspace(project)
        try:
            referenced = {t.name for t in sqlglot.parse_one(body.sql, read="duckdb").find_all(sqlglot.exp.Table)}
            sources = [{"table": n, **{k: v for k, v in info.items() if k in ("dataset_id", "version_id", "dataset_name")}}
                       for n, info in ws.tables.items() if n in referenced]
        finally:
            ws.close()
        parent = sources[0]["version_id"] if sources else None
    else:
        sources = [{"connection": conn.name, "engine": conn.engine}]
    ds = create_dataset(db, project, name=body.name, data_path=rel, fmt="sql", parent_version_id=parent,
                        lineage={"sql": body.sql, "sources": sources}, note="Created from SQL query")
    audit(db, user, "dataset.from_sql", project.id, dataset=ds.id, rows=rows)
    db.commit()
    from .datasets import dataset_out

    return dataset_out(ds, full=True)


class ExportQueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=200_000)
    project_id: int | None = None
    connection_id: int | None = None
    format: str = Field("csv", pattern="^(csv|xlsx|parquet|json)$")


@router.post("/export")
def export_query(body: ExportQueryIn, user: CurrentUser, db: DB):
    _dev(user)
    conn, project = _target(db, user, body.project_id, body.connection_id)
    _read_only_select(body.sql, sql_engine.DIALECT[conn.engine if conn else "duckdb"])
    session = sql_engine.open_session(conn, project)
    limit = get_settings().sql_export_max_rows if body.format != "xlsx" else 1_000_000
    try:
        batches, n = [], 0
        for b in session.iter_batches(body.sql):
            n += b.num_rows
            if n > limit:
                raise AppError("too_many_rows", f"Exports are limited to {limit:,} rows.", 422)
            batches.append(b)
    finally:
        session.close()
    table = pa.Table.from_batches(batches) if batches else pa.table({})
    buf = io.BytesIO()
    import polars as pl

    frame = pl.from_arrow(table) if batches else pl.DataFrame()
    if body.format == "csv":
        frame.write_csv(buf)
        media = "text/csv"
    elif body.format == "parquet":
        pq.write_table(table, buf)
        media = "application/octet-stream"
    elif body.format == "json":
        frame.write_json(buf)
        media = "application/json"
    else:
        frame.write_excel(buf, worksheet="Query result", autofit=True, header_format={"bold": True})
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buf.seek(0)
    name = f"query-result-{time.strftime('%Y%m%d-%H%M%S')}.{body.format}"
    return StreamingResponse(buf, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --------------------------------------------------------------------------- history and saved queries


@router.get("/history")
def history(user: CurrentUser, db: DB, project_id: int | None = None, limit: int = Query(100, ge=1, le=500),
            offset: int = Query(0, ge=0)):
    _dev(user)
    stmt = select(QueryHistory).where(QueryHistory.owner_id == user.id)
    if project_id:
        stmt = stmt.where(QueryHistory.project_id == project_id)
    rows = db.scalars(stmt.order_by(QueryHistory.id.desc()).limit(limit).offset(offset))
    return {"items": [{"id": h.id, "sql": h.body, "status": h.status, "row_count": h.row_count,
                       "duration_ms": h.duration_ms, "error": h.error_message, "project_id": h.project_id,
                       "connection_id": h.connection_id, "language": h.language,
                       "created_at": h.created_at.isoformat()} for h in rows]}


class SavedIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=200_000)
    language: str = Field("sql", pattern="^(sql|python)$")
    project_id: int | None = None
    connection_id: int | None = None


def saved_out(q: SavedQuery) -> dict[str, Any]:
    return {"id": q.id, "name": q.name, "body": q.body, "language": q.language, "project_id": q.project_id,
            "connection_id": q.connection_id, "updated_at": q.updated_at.isoformat()}


@router.get("/saved")
def list_saved(user: CurrentUser, db: DB, project_id: int | None = None, language: str = "sql"):
    _dev(user)
    stmt = select(SavedQuery).where(SavedQuery.owner_id == user.id, SavedQuery.language == language)
    if project_id:
        stmt = stmt.where((SavedQuery.project_id == project_id) | (SavedQuery.project_id.is_(None)))
    return {"items": [saved_out(q) for q in db.scalars(stmt.order_by(SavedQuery.name))]}


@router.post("/saved", status_code=201)
def create_saved(body: SavedIn, user: CurrentUser, db: DB):
    _dev(user)
    if body.project_id:
        get_project(db, user, body.project_id)
    q = SavedQuery(owner_id=user.id, **body.model_dump())
    db.add(q)
    db.commit()
    return saved_out(q)


@router.put("/saved/{qid}")
def update_saved(qid: int, body: SavedIn, user: CurrentUser, db: DB):
    _dev(user)
    q = db.get(SavedQuery, qid)
    if q is None or q.owner_id != user.id:
        raise NotFound("Saved query")
    for k, v in body.model_dump().items():
        setattr(q, k, v)
    db.commit()
    return saved_out(q)


@router.delete("/saved/{qid}", status_code=204)
def delete_saved(qid: int, user: CurrentUser, db: DB):
    _dev(user)
    q = db.get(SavedQuery, qid)
    if q is None or q.owner_id != user.id:
        raise NotFound("Saved query")
    db.delete(q)
    db.commit()


@router.get("/samples")
def samples(user: CurrentUser, db: DB):
    """Example queries, plus a sample SQLite database connection (created on first request)."""
    _dev(user)
    existing = db.scalar(select(DbConnection).where(DbConnection.owner_id == user.id,
                                                    DbConnection.name == "Sample store (SQLite)"))
    if existing is None:
        fname = ensure_sample_db()
        existing = DbConnection(owner_id=user.id, name="Sample store (SQLite)", engine="sqlite", database=fname,
                                allow_writes=False)
        db.add(existing)
        db.commit()
    return {"connection": conn_out(existing), "examples": EXAMPLE_QUERIES}

