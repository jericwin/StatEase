from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, audit, get_project, get_run
from ..errors import AppError, NotFound
from ..jobs import project_settings
from ..models import AnalysisResult, Dataset, DatasetVersion, Export
from ..reports.docx_export import build_docx, verify_docx
from ..reports.options import PRESETS, SECTION_KEYS, ReportOptions
from ..reports.xlsx_export import build_xlsx, verify_xlsx
from ..storage import new_relative_path, remove, resolve, safe_filename
from ..storage import resolve as resolve_path

router = APIRouter(prefix="/exports", tags=["exports"])
MEDIA = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
XLSX_DATA_LIMIT = 1_000_000


class ExportIn(BaseModel):
    project_id: int
    format: str = Field(pattern="^(docx|xlsx)$")
    options: ReportOptions | None = None
    report_id: int | None = None
    include_data: bool = False


def export_out(e: Export) -> dict[str, Any]:
    return {"id": e.id, "project_id": e.project_id, "format": e.export_format, "status": e.status,
            "filename": e.filename, "size_bytes": e.size_bytes, "error": e.error_message,
            "summary": (e.options_json or {}).get("_summary"), "created_at": e.created_at.isoformat(),
            "download_url": f"/api/v1/exports/{e.id}/download" if e.status == "completed" else None}


@router.get("/presets")
def presets(user: CurrentUser):
    return {"presets": PRESETS, "sections": SECTION_KEYS, "defaults": ReportOptions().model_dump()}


@router.post("", status_code=201)
def create_export(body: ExportIn, user: CurrentUser, db: DB):
    project = get_project(db, user, body.project_id)
    if body.report_id is not None:
        return _export_report(body, project, user, db)
    opts = body.options
    if opts is None:
        raise AppError("nothing_selected", "Choose a report or results to export.", 422)
    if not opts.run_ids:
        raise AppError("nothing_selected", "Select at least one analysis result to export.", 422)
    items, versions = [], {}
    for rid in opts.run_ids:
        r = get_run(db, user, rid)
        if r.configuration.project_id != project.id:
            raise AppError("invalid_run", "A selected result belongs to another project.", 422)
        res = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == r.id))
        if r.status != "completed" or res is None:
            raise AppError("run_not_completed", f"Result {rid} is not available (status: {r.status}).", 422)
        items.append({"run_id": r.id, "result": res.result_json, "edited_interpretation": res.edited_interpretation})
        versions[r.dataset_version_id] = db.get(DatasetVersion, r.dataset_version_id)
    vlist = list(versions.values())
    datasets = [db.get(Dataset, v.dataset_id) for v in vlist]
    main_v, main_ds = vlist[0], datasets[0]
    variables = [{"name": x.column_name, "label": x.variable_label, "level": x.measurement_level,
                  "data_type": x.data_type, "missing_codes": x.missing_value_codes_json,
                  "category_labels": x.category_labels_json, "unit": x.unit} for x in main_v.variables]
    lineage = None
    if main_ds.lineage_json.get("sql"):
        lineage = f"SQL query on dataset version {main_ds.parent_version_id}: {main_ds.lineage_json['sql'][:300]}"
    info = {"project": project.name, "dataset": "; ".join(f"{d.name} (v{v.version_number})" for d, v in
                                                          zip(datasets, vlist, strict=True)),
            "rows": main_v.row_count, "columns": len(variables), "source": main_ds.source_filename,
            "alpha": project_settings(project)["alpha"], "variables": variables, "lineage": lineage}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{safe_filename(opts.title, 'report')[:80]}-{stamp}.{body.format}"
    rel = new_relative_path("exports", f".{body.format}")
    path = resolve(rel)
    exp = Export(project_id=project.id, analysis_run_id=opts.run_ids[0], export_format=body.format,
                 options_json=opts.model_dump(), filename=filename, status="pending")
    db.add(exp)
    db.flush()
    try:
        if body.format == "docx":
            summary = build_docx(path, opts, info, items)
            check = verify_docx(path)
        else:
            data = None
            if opts.include_data:
                if main_v.row_count > XLSX_DATA_LIMIT:
                    raise AppError("too_many_rows", f"The dataset has {main_v.row_count:,} rows; Excel sheets hold at "
                                                    f"most {XLSX_DATA_LIMIT:,}. Export the data as CSV instead.", 422)
                frame = pl.read_parquet(resolve(main_v.data_path))
                data = (frame.columns, [list(r) for r in frame.iter_rows()])
            summary = build_xlsx(path, opts, info, items, data)
            check = verify_xlsx(path)
        size = path.stat().st_size if path.exists() else 0
        if size == 0:
            raise RuntimeError("The generated file is empty.")
        exp.status, exp.artifact_path, exp.size_bytes = "completed", rel, size
        exp.options_json = {**opts.model_dump(), "_summary": {**summary, "verified": check}}
    except AppError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001 - report failures; never hand out a broken file
        path.unlink(missing_ok=True)
        exp.status, exp.error_message = "failed", f"{type(exc).__name__}: {str(exc)[:400]}"
    audit(db, user, "export.create", project.id, export=exp.id, format=body.format, status=exp.status)
    db.commit()
    if exp.status != "completed":
        raise AppError("export_failed", f"The {body.format.upper()} file could not be generated: {exp.error_message}", 500,
                       export_out(exp))
    return export_out(exp)


@router.get("")
def list_exports(project_id: int, user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0)):
    get_project(db, user, project_id)
    stmt = select(Export).where(Export.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Export.id.desc()).limit(limit).offset(offset))
    return {"items": [export_out(e) for e in rows], "total": total, "limit": limit, "offset": offset}


def _export(db, user, export_id: int) -> Export:
    e = db.get(Export, export_id)
    if e is None:
        raise NotFound("Export")
    get_project(db, user, e.project_id)
    return e


@router.get("/{export_id}")
def read_export(export_id: int, user: CurrentUser, db: DB):
    return export_out(_export(db, user, export_id))


@router.get("/{export_id}/download")
def download_export(export_id: int, user: CurrentUser, db: DB):
    e = _export(db, user, export_id)
    if e.status != "completed" or not e.artifact_path:
        raise AppError("not_ready", "This export is not available.", 404)
    path = resolve(e.artifact_path)
    if not path.exists():
        raise AppError("file_missing", "The export file no longer exists. Generate it again.", 410)
    return FileResponse(path, filename=e.filename, media_type=MEDIA.get(e.export_format, "application/octet-stream"))


@router.delete("/{export_id}", status_code=204)
def delete_export(export_id: int, user: CurrentUser, db: DB):
    e = _export(db, user, export_id)
    if e.artifact_path:
        remove(e.artifact_path)
    db.delete(e)
    db.commit()



def _export_report(body: ExportIn, project, user, db):
    """Export an edited report exactly as arranged by the user (order, titles, edits, inclusion)."""
    from ..models import Report
    from ..reports.docx_export import build_report_docx
    from ..reports.service import resolve
    from ..reports.xlsx_export import build_report_xlsx

    report = db.get(Report, body.report_id)
    if report is None or report.project_id != project.id:
        raise NotFound("Report")
    resolved = resolve(db, report, for_export=True)
    if not any(b.get("include") and not b.get("missing") for b in resolved["blocks"]):
        raise AppError("nothing_selected", "Select at least one item in the checklist.", 422)
    ds = db.get(Dataset, report.dataset_id) if report.dataset_id else None
    version = None
    if ds is not None:
        from ..services import latest_version

        version = latest_version(ds)
    info = {"project": project.name, "dataset": ds.name if ds else None, "alpha": project_settings(project)["alpha"],
            "synthetic": bool(ds and (ds.lineage_json or {}).get("synthetic"))}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{safe_filename(report.title, 'report')[:80]}-{stamp}.{body.format}"
    rel = new_relative_path("exports", f".{body.format}")
    path = resolve_path(rel)
    exp = Export(project_id=project.id, export_format=body.format, options_json={"report_id": report.id},
                 filename=filename, status="pending")
    db.add(exp)
    db.flush()
    try:
        if body.format == "docx":
            summary = build_report_docx(path, resolved, info)
            check = verify_docx(path)
        else:
            data = None
            if body.include_data and version is not None:
                if version.row_count > XLSX_DATA_LIMIT:
                    raise AppError("too_many_rows", f"The dataset has {version.row_count:,} rows; Excel sheets hold at "
                                                    f"most {XLSX_DATA_LIMIT:,}. Download the data as CSV instead.", 422)
                frame = pl.read_parquet(resolve_path(version.data_path))
                data = (frame.columns, [list(r) for r in frame.iter_rows()])
            summary = build_report_xlsx(path, resolved, info, data)
            check = verify_xlsx(path)
        size = path.stat().st_size if path.exists() else 0
        if size == 0:
            raise RuntimeError("The generated file is empty.")
        exp.status, exp.artifact_path, exp.size_bytes = "completed", rel, size
        exp.options_json = {"report_id": report.id, "_summary": {**summary, "verified": check}}
    except AppError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001 - never hand out a broken file
        path.unlink(missing_ok=True)
        exp.status, exp.error_message = "failed", f"{type(exc).__name__}: {str(exc)[:400]}"
    audit(db, user, "export.create", project.id, export=exp.id, format=body.format, report=report.id, status=exp.status)
    db.commit()
    if exp.status != "completed":
        raise AppError("export_failed", f"The {body.format.upper()} file could not be generated: {exp.error_message}", 500)
    return export_out(exp)
