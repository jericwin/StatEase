"""SQL Workbench engine.

Two kinds of targets, kept clearly separate:
- The project workspace: an in-memory DuckDB session exposing the project's datasets as read-only views
  over their Parquet files. File-system access, extensions and configuration changes are locked.
- External connections (SQLite, PostgreSQL, MySQL/MariaDB) with read-only sessions by default.

Every statement is parsed with sqlglot and classified before it runs. Write and DDL statements are
rejected unless the connection allows writes, the user is an administrator and the request carries
an explicit confirmation.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

from ..config import get_settings
from ..errors import AppError
from ..models import DbConnection, Project
from ..security import decrypt_secret
from ..services import latest_version
from ..storage import resolve

DIALECT = {"duckdb": "duckdb", "sqlite": "sqlite", "postgresql": "postgres", "mysql": "mysql"}
READ_TYPES = (exp.Select, exp.Union, exp.Except, exp.Intersect, exp.Describe, exp.Show, exp.Values)
DESTRUCTIVE = (exp.Delete, exp.Drop, exp.TruncateTable, exp.Update, exp.Alter)
WRITE_TYPES = (exp.Insert, exp.Merge, exp.Create, exp.Copy, *DESTRUCTIVE)


@dataclass
class Statement:
    sql: str
    kind: str  # read | write | destructive | other
    type: str


def table_name(name: str, used: set[str]) -> str:
    base = re.sub(r"\W+", "_", name.lower()).strip("_") or "dataset"
    if base[0].isdigit():
        base = "t_" + base
    cand, i = base, 2
    while cand in used:
        cand, i = f"{base}_{i}", i + 1
    used.add(cand)
    return cand


def classify(sql: str, dialect: str) -> list[Statement]:
    try:
        trees = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        msg = str(exc).split("\n")[0]
        raise AppError("sql_syntax", f"SQL syntax error: {msg}", 422) from exc
    out = []
    for tree in trees:
        if tree is None:
            continue
        text = tree.sql(dialect=dialect)
        if isinstance(tree, READ_TYPES) and not any(isinstance(n, WRITE_TYPES) for n in tree.walk()):
            kind = "read"
        elif isinstance(tree, DESTRUCTIVE):
            kind = "destructive"
        elif isinstance(tree, WRITE_TYPES):
            kind = "write"
        elif isinstance(tree, exp.Pragma) and dialect == "sqlite" and "=" not in text:
            kind = "read"
        else:
            kind = "other"
        out.append(Statement(text, kind, type(tree).__name__))
    if not out:
        raise AppError("sql_empty", "Enter a SQL statement to run.", 422)
    return out


def format_sql(sql: str, dialect: str) -> str:
    try:
        return ";\n\n".join(t.sql(dialect=dialect, pretty=True) for t in sqlglot.parse(sql, read=dialect) if t) + ";"
    except sqlglot.errors.ParseError as exc:
        raise AppError("sql_syntax", f"Cannot format: {str(exc).splitlines()[0]}", 422) from exc


def authorize(stmts: list[Statement], *, allow_writes: bool, is_admin: bool, confirmed: bool, local: bool) -> None:
    risky = [s for s in stmts if s.kind != "read"]
    if not risky:
        return
    if local:
        raise AppError("read_only", "Project datasets are read-only. To keep a modified copy, run a SELECT and use "
                                    "'Save as dataset'; the original is never changed.", 403)
    if not allow_writes:
        raise AppError("read_only", f"This connection is read-only; {risky[0].type.upper()} statements are not "
                                    "allowed. An administrator can enable writes on the connection profile.", 403)
    if not is_admin:
        raise AppError("forbidden", "Only administrators can run statements that change data.", 403)
    if not confirmed:
        raise AppError("confirmation_required", "This statement can change or delete data. Confirm to run it.", 409,
                       {"statements": [{"type": s.type, "kind": s.kind, "sql": s.sql[:500]} for s in risky]})


# --------------------------------------------------------------------------- sessions


class Session:
    dialect = "duckdb"

    def execute(self, sql: str, max_rows: int, timeout: float) -> dict[str, Any]:
        raise NotImplementedError

    def iter_batches(self, sql: str, batch: int = 50_000):
        raise NotImplementedError

    def schema(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def close(self) -> None:
        pass


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


class DuckWorkspace(Session):
    """Project datasets as read-only DuckDB views."""

    def __init__(self, project: Project):
        s = get_settings()
        self.con = duckdb.connect(":memory:")
        self.tables: dict[str, dict[str, Any]] = {}
        used: set[str] = set()
        for ds in project.datasets:
            v = latest_version(ds)
            name = table_name(ds.name, used)
            path = resolve(v.data_path).as_posix()
            self.con.execute(f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet(\'{path}\')')
            self.tables[name] = {"dataset_id": ds.id, "version_id": v.id, "dataset_name": ds.name,
                                 "rows": v.row_count, "variables": {x.column_name: x for x in v.variables}}
        datasets_dir = s.datasets_dir.resolve().as_posix()
        self.con.execute(f"SET allowed_directories=['{datasets_dir}/']")
        self.con.execute("SET enable_external_access=false")
        self.con.execute("SET memory_limit='1GB'")
        self.con.execute("SET threads=2")
        self.con.execute("SET lock_configuration=true")

    def execute(self, sql, max_rows, timeout):
        timer = threading.Timer(timeout, self.con.interrupt)
        timer.start()
        try:
            cur = self.con.execute(sql)
            if cur.description is None:
                return {"columns": [], "rows": [], "truncated": False}
            cols = [{"name": d[0], "type": str(d[1])} for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
            return {"columns": cols, "rows": [[_jsonable(x) for x in r] for r in rows[:max_rows]],
                    "truncated": len(rows) > max_rows}
        except duckdb.InterruptException as exc:
            raise AppError("sql_timeout", f"The query exceeded the {timeout:g}-second time limit and was cancelled.",
                           408) from exc
        except duckdb.Error as exc:
            raise AppError("sql_error", str(exc).split("\n")[0], 422) from exc
        finally:
            timer.cancel()

    def iter_batches(self, sql, batch=50_000):
        reader = self.con.execute(sql).to_arrow_reader(batch)
        yield from reader

    def schema(self):
        out = []
        for name, info in self.tables.items():
            cols = self.con.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = ? "
                "ORDER BY ordinal_position", [name]).fetchall()
            out.append({"name": name, "type": "view", "rows": info["rows"], "dataset_id": info["dataset_id"],
                        "description": f"Dataset '{info['dataset_name']}' (read-only)",
                        "columns": [{"name": c, "type": t, "nullable": n == "YES", "primary_key": False,
                                     "level": info["variables"].get(c).measurement_level
                                     if info["variables"].get(c) else None} for c, t, n in cols],
                        "foreign_keys": []})
        return out

    def close(self):
        self.con.close()


class SqliteSession(Session):
    dialect = "sqlite"

    def __init__(self, path: str, writable: bool):
        mode = "rw" if writable else "ro"
        self.con = sqlite3.connect(f"file:{path}?mode={mode}", uri=True, check_same_thread=False)
        self.deadline = None
        self.con.set_progress_handler(self._progress, 10000)

    def _progress(self):
        return 1 if self.deadline and time.monotonic() > self.deadline else 0

    def execute(self, sql, max_rows, timeout):
        self.deadline = time.monotonic() + timeout
        try:
            cur = self.con.execute(sql)
            if cur.description is None:
                self.con.commit()
                return {"columns": [], "rows": [], "truncated": False, "rowcount": cur.rowcount}
            rows = cur.fetchmany(max_rows + 1)
            return {"columns": [{"name": d[0], "type": ""} for d in cur.description],
                    "rows": [[_jsonable(x) for x in r] for r in rows[:max_rows]], "truncated": len(rows) > max_rows}
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise AppError("sql_timeout", f"The query exceeded the {timeout:g}-second limit.", 408) from exc
            raise AppError("sql_error", str(exc), 422) from exc
        except sqlite3.Error as exc:
            raise AppError("sql_error", str(exc), 422) from exc
        finally:
            self.deadline = None

    def iter_batches(self, sql, batch=50_000):
        import pyarrow as pa

        cur = self.con.execute(sql)
        names = [d[0] for d in cur.description]
        while rows := cur.fetchmany(batch):
            yield pa.RecordBatch.from_pylist([dict(zip(names, r, strict=True)) for r in rows])

    def schema(self):
        out = []
        for name, typ in self.con.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                                          "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            cols = self.con.execute(f'PRAGMA table_info("{name}")').fetchall()
            fks = self.con.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
            out.append({"name": name, "type": typ, "rows": None,
                        "columns": [{"name": c[1], "type": c[2], "nullable": not c[3], "primary_key": bool(c[5])}
                                    for c in cols],
                        "foreign_keys": [{"column": f[3], "references": f"{f[2]}.{f[4]}"} for f in fks]})
        return out

    def close(self):
        self.con.close()


class PostgresSession(Session):
    dialect = "postgres"

    def __init__(self, c: DbConnection, password: str | None, writable: bool, timeout: float):
        import psycopg

        try:
            self.con = psycopg.connect(host=c.host, port=c.port or 5432, dbname=c.database, user=c.username,
                                       password=password, connect_timeout=10,
                                       options=f"-c statement_timeout={int(timeout * 1000)}"
                                               + ("" if writable else " -c default_transaction_read_only=on"),
                                       sslmode=(c.options_json or {}).get("sslmode", "prefer"))
        except psycopg.Error as exc:
            raise AppError("connection_failed", f"Could not connect: {str(exc).splitlines()[0]}", 502) from exc

    def execute(self, sql, max_rows, timeout):
        import psycopg

        try:
            with self.con.cursor() as cur:
                cur.execute(sql)
                if cur.description is None:
                    self.con.commit()
                    return {"columns": [], "rows": [], "truncated": False, "rowcount": cur.rowcount}
                rows = cur.fetchmany(max_rows + 1)
                self.con.commit()
                return {"columns": [{"name": d.name, "type": str(d.type_code)} for d in cur.description],
                        "rows": [[_jsonable(x) for x in r] for r in rows[:max_rows]], "truncated": len(rows) > max_rows}
        except psycopg.errors.QueryCanceled as exc:
            self.con.rollback()
            raise AppError("sql_timeout", f"The query exceeded the {timeout:g}-second limit.", 408) from exc
        except psycopg.Error as exc:
            self.con.rollback()
            raise AppError("sql_error", str(exc).split("\n")[0], 422) from exc

    def iter_batches(self, sql, batch=50_000):
        import pyarrow as pa

        with self.con.cursor(name="statease_export") as cur:
            cur.execute(sql)
            names = None
            while rows := cur.fetchmany(batch):
                names = names or [d.name for d in cur.description]
                yield pa.RecordBatch.from_pylist([dict(zip(names, r, strict=True)) for r in rows])
        self.con.rollback()

    def schema(self):
        q = """SELECT c.table_schema, c.table_name, t.table_type, c.column_name, c.data_type, c.is_nullable,
                      EXISTS (SELECT 1 FROM information_schema.table_constraints tc
                              JOIN information_schema.key_column_usage k ON tc.constraint_name = k.constraint_name
                               AND tc.table_schema = k.table_schema
                              WHERE tc.constraint_type = 'PRIMARY KEY' AND k.table_schema = c.table_schema
                                AND k.table_name = c.table_name AND k.column_name = c.column_name)
               FROM information_schema.columns c
               JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
               WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
               ORDER BY c.table_schema, c.table_name, c.ordinal_position LIMIT 20000"""
        fkq = """SELECT tc.table_schema, tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
                 FROM information_schema.table_constraints tc
                 JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                 JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                 WHERE tc.constraint_type = 'FOREIGN KEY'"""
        return _group_schema(self._fetch(q), self._fetch(fkq))

    def _fetch(self, q):
        with self.con.cursor() as cur:
            cur.execute(q)
            rows = cur.fetchall()
        self.con.rollback()
        return rows

    def close(self):
        self.con.close()


class MysqlSession(Session):
    dialect = "mysql"

    def __init__(self, c: DbConnection, password: str | None, writable: bool, timeout: float):
        import pymysql

        try:
            self.con = pymysql.connect(host=c.host, port=c.port or 3306, user=c.username, password=password or "",
                                       database=c.database, connect_timeout=10, read_timeout=int(timeout) + 5,
                                       autocommit=True)
            with self.con.cursor() as cur:
                if not writable:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
                try:
                    cur.execute(f"SET SESSION max_execution_time = {int(timeout * 1000)}")
                except pymysql.Error:
                    pass  # MariaDB uses max_statement_time instead
                    try:
                        cur.execute(f"SET SESSION max_statement_time = {timeout}")
                    except pymysql.Error:
                        pass
        except pymysql.Error as exc:
            raise AppError("connection_failed", f"Could not connect: {exc}", 502) from exc

    def execute(self, sql, max_rows, timeout):
        import pymysql

        try:
            with self.con.cursor() as cur:
                cur.execute(sql)
                if cur.description is None:
                    return {"columns": [], "rows": [], "truncated": False, "rowcount": cur.rowcount}
                rows = cur.fetchmany(max_rows + 1)
                return {"columns": [{"name": d[0], "type": str(d[1])} for d in cur.description],
                        "rows": [[_jsonable(x) for x in r] for r in rows[:max_rows]], "truncated": len(rows) > max_rows}
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] in (3024, 1969):
                raise AppError("sql_timeout", f"The query exceeded the {timeout:g}-second limit.", 408) from exc
            raise AppError("sql_error", str(exc), 422) from exc
        except pymysql.Error as exc:
            raise AppError("sql_error", str(exc), 422) from exc

    def iter_batches(self, sql, batch=50_000):
        import pyarrow as pa
        import pymysql

        with self.con.cursor(pymysql.cursors.SSCursor) as cur:
            cur.execute(sql)
            names = [d[0] for d in cur.description]
            while rows := cur.fetchmany(batch):
                yield pa.RecordBatch.from_pylist([dict(zip(names, r, strict=True)) for r in rows])

    def schema(self):
        with self.con.cursor() as cur:
            cur.execute("""SELECT c.table_schema, c.table_name, t.table_type, c.column_name, c.data_type,
                                  c.is_nullable, c.column_key = 'PRI'
                           FROM information_schema.columns c JOIN information_schema.tables t
                             ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                           WHERE c.table_schema = DATABASE() ORDER BY c.table_name, c.ordinal_position LIMIT 20000""")
            cols = cur.fetchall()
            cur.execute("""SELECT table_schema, table_name, column_name, referenced_table_name, referenced_column_name
                           FROM information_schema.key_column_usage
                           WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL""")
            fks = cur.fetchall()
        return _group_schema(cols, fks)

    def close(self):
        self.con.close()


def _group_schema(cols, fks) -> list[dict[str, Any]]:
    tables: dict[tuple, dict[str, Any]] = {}
    for schema, table, ttype, col, typ, nullable, pk in cols:
        t = tables.setdefault((schema, table), {"name": f"{schema}.{table}" if schema not in ("public",) else table,
                                                "type": "view" if "VIEW" in str(ttype) else "table", "rows": None,
                                                "columns": [], "foreign_keys": []})
        t["columns"].append({"name": col, "type": typ, "nullable": nullable == "YES", "primary_key": bool(pk)})
    for schema, table, col, rtable, rcol in fks:
        if (schema, table) in tables:
            tables[(schema, table)]["foreign_keys"].append({"column": col, "references": f"{rtable}.{rcol}"})
    return list(tables.values())


def open_session(conn: DbConnection | None, project: Project | None, *, writable: bool = False) -> Session:
    timeout = get_settings().sql_timeout_seconds
    if conn is None:
        if project is None:
            raise AppError("no_target", "Choose a project or a database connection.", 422)
        return DuckWorkspace(project)
    password = decrypt_secret(conn.secret_encrypted) if conn.secret_encrypted else None
    writable = writable and conn.allow_writes
    if conn.engine == "sqlite":
        path = sqlite_path(conn)
        return SqliteSession(path, writable)
    if conn.engine == "postgresql":
        return PostgresSession(conn, password, writable, timeout)
    if conn.engine == "mysql":
        return MysqlSession(conn, password, writable, timeout)
    raise AppError("unsupported_engine", f"Unsupported engine '{conn.engine}'.", 422)


def sqlite_path(conn: DbConnection) -> str:
    """SQLite files must live in the managed sqlite directory (no arbitrary server paths)."""
    from pathlib import Path

    root = get_settings().sqlite_connections_dir.resolve()
    p = (root / Path(conn.database or "").name).resolve()
    if not p.is_relative_to(root) or not p.exists():
        raise AppError("connection_failed", "The SQLite database file was not found.", 404)
    return p.as_posix()
