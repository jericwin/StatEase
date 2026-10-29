from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import DB, CurrentUser, audit, get_dataset, get_project
from ..errors import AppError, NotFound
from ..models import AnalysisConfiguration, AnalysisResult, AnalysisRun, Report
from ..reports import service
from ..services import latest_version
from ..stats.planner import parse_objectives, plan_compare

router = APIRouter(tags=["reports"])
BLOCK_TYPES = {"heading", "table", "chart", "text"}


def _report(db, user, report_id: int) -> Report:
    r = db.get(Report, report_id)
    if r is None:
        raise NotFound("Report")
    get_project(db, user, r.project_id)
    return r


# --------------------------------------------------------------------------- planning


class CompareIn(BaseModel):
    dataset_id: int
    mode: str = Field(pattern="^(groups|variables)$")
    group: str | None = None
    levels: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    var1: str | None = None
    var2: str | None = None
    relation: str | None = None
    test: str | None = None


@router.post("/analyses/compare/plan")
def compare_plan(body: CompareIn, user: CurrentUser, db: DB):
    ds = get_dataset(db, user, body.dataset_id)
    v = latest_version(ds)
    return {**plan_compare(v, body.model_dump()), "dataset_version_id": v.id}


class ObjectivesIn(BaseModel):
    dataset_id: int
    text: str = Field(min_length=3, max_length=20000)


@router.post("/reports/objectives/parse")
def objectives_parse(body: ObjectivesIn, user: CurrentUser, db: DB):
    ds = get_dataset(db, user, body.dataset_id)
    items = parse_objectives(latest_version(ds), body.text)
    if not items:
        raise AppError("no_objectives", "Enter one objective per line.", 422)
    return {"objectives": items}


# --------------------------------------------------------------------------- reports


class ReportIn(BaseModel):
    project_id: int
    dataset_id: int | None = None
    title: str = Field("Research Report", max_length=300)
    objectives: list[dict[str, Any]] | None = None


@router.get("/reports")
def list_reports(project_id: int, user: CurrentUser, db: DB):
    get_project(db, user, project_id)
    rows = db.scalars(select(Report).where(Report.project_id == project_id).order_by(Report.updated_at.desc()))
    return {"items": [{"id": r.id, "title": r.title, "objectives": len(r.objectives_json or []),
                       "blocks": len(r.blocks_json or []), "updated_at": r.updated_at.isoformat()} for r in rows]}


@router.post("/reports", status_code=201)
def create_report(body: ReportIn, user: CurrentUser, db: DB):
    project = get_project(db, user, body.project_id)
    ds = get_dataset(db, user, body.dataset_id) if body.dataset_id else None
    if ds and ds.project_id != project.id:
        raise AppError("invalid_dataset", "The dataset belongs to another project.", 422)
    report = service.build_report(db, project, ds, body.title.strip() or "Research Report", body.objectives)
    audit(db, user, "report.create", project.id, report=report.id)
    db.commit()
    return service.resolve(db, report)


@router.get("/reports/{report_id}")
def read_report(report_id: int, user: CurrentUser, db: DB):
    return service.resolve(db, _report(db, user, report_id))


class ReportPatch(BaseModel):
    title: str | None = Field(None, max_length=300)
    blocks: list[dict[str, Any]] | None = None
    options: dict[str, Any] | None = None


STORED_KEYS = {"id", "type", "include", "objective_id", "title", "title_edited", "text", "source", "edits"}


@router.put("/reports/{report_id}")
def save_report(report_id: int, body: ReportPatch, user: CurrentUser, db: DB):
    report = _report(db, user, report_id)
    if body.title is not None:
        report.title = body.title.strip() or report.title
    if body.blocks is not None:
        clean = []
        for b in body.blocks:
            if b.get("type") not in BLOCK_TYPES or not b.get("id"):
                raise AppError("invalid_block", "Invalid report block.", 422)
            clean.append({k: v for k, v in b.items() if k in STORED_KEYS})
        report.blocks_json = clean
    if body.options is not None:
        allowed = {"style", "decimals", "include_details", "include_methods", "interpretation", "author", "subtitle"}
        report.options_json = {**report.options_json, **{k: v for k, v in body.options.items() if k in allowed}}
    db.commit()
    return service.resolve(db, report)


class RebindIn(BaseModel):
    variables: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    filter: dict[str, Any] | None = None
    run_id: int | None = None
    table_id: str | None = None
    chart_id: str | None = None


@router.post("/reports/{report_id}/blocks/{block_id}/rebind")
def rebind_block(report_id: int, block_id: str, body: RebindIn, user: CurrentUser, db: DB):
    report = _report(db, user, report_id)
    project = get_project(db, user, report.project_id)
    payload = body.model_dump(exclude_unset=True)
    service.rebind(db, project, report, block_id, payload)
    return service.resolve(db, report)


@router.get("/reports/{report_id}/library")
def library(report_id: int, user: CurrentUser, db: DB, q: str | None = Query(None)):
    """Completed results in the project, with their tables and charts, for adding to the report."""
    report = _report(db, user, report_id)
    configs = db.scalars(select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == report.project_id)
                         .order_by(AnalysisConfiguration.id.desc())).all()
    items = []
    for c in configs:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.configuration_id == c.id, AnalysisRun.status == "completed")
                        .order_by(AnalysisRun.id.desc()))
        res = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == run.id)) if run else None
        if not res:
            continue
        r = res.result_json
        label = f"{r.get('title')}: {r.get('heading') or ''}".strip(": ")
        if q and q.lower() not in label.lower():
            continue
        items.append({"run_id": run.id, "title": r.get("title"), "heading": r.get("heading"),
                      "tables": [{"id": t["id"], "title": t["title"], "kind": t["kind"]} for t in r.get("tables", [])],
                      "charts": [{"id": ch["id"], "title": ch["title"], "type": ch["type"]} for ch in r.get("charts", [])]})
        if len(items) >= 100:
            break
    return {"items": items}


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, user: CurrentUser, db: DB):
    report = _report(db, user, report_id)
    db.delete(report)
    db.commit()
