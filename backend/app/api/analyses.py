from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, audit, get_configuration, get_dataset, get_project, get_run, get_version
from ..errors import AppError
from ..jobs import submit
from ..models import AnalysisConfiguration, AnalysisResult, AnalysisRun, Dataset, DatasetVersion
from ..services import latest_version
from ..stats import engine
from ..stats.base import REGISTRY
from ..stats.recommend import recommend

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("/catalog")
def catalog(user: CurrentUser):
    return engine.catalog()


@router.get("/recommendations")
def recommendations(dataset_id: int, user: CurrentUser, db: DB):
    ds = get_dataset(db, user, dataset_id)
    v = latest_version(ds)
    out = recommend(v)
    existing = {c.configuration_json.get("rec_key") for c in db.scalars(
        select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == ds.project_id))}
    for r in out["recommendations"]:
        r["added"] = r["key"] in existing
        spec = REGISTRY.get(r["analysis_type"])
        r["technical_name"] = spec.name if spec else r["test"]
    out["dataset_version_id"] = v.id
    out["profile_warnings"] = (v.profile_json or {}).get("warnings", [])
    return out


# --------------------------------------------------------------------------- configurations


class ConfigIn(BaseModel):
    project_id: int
    dataset_version_id: int
    analysis_type: str
    name: str | None = Field(None, max_length=255)
    variables: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    source: str = Field("manual", pattern="^(manual|recommended)$")
    rec_key: str | None = None


class ConfigPatch(BaseModel):
    name: str | None = Field(None, max_length=255)
    variables: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    dataset_version_id: int | None = None
    position: int | None = None


def config_out(db, c: AnalysisConfiguration, version: DatasetVersion | None = None) -> dict[str, Any]:
    spec = REGISTRY.get(c.analysis_type)
    last = db.scalar(select(AnalysisRun).where(AnalysisRun.configuration_id == c.id).order_by(AnalysisRun.id.desc()))
    v = version or db.get(DatasetVersion, c.dataset_version_id)
    latest = latest_version(db.get(Dataset, v.dataset_id))
    cfg = c.configuration_json or {}
    return {"id": c.id, "project_id": c.project_id, "dataset_version_id": c.dataset_version_id,
            "dataset_id": v.dataset_id, "dataset_version_number": v.version_number,
            "outdated": latest.id != v.id, "analysis_type": c.analysis_type,
            "analysis_name": spec.name if spec else c.analysis_type, "plain_name": spec.plain_name if spec else "",
            "category": spec.category if spec else None, "name": c.name, "variables": cfg.get("variables", {}),
            "options": cfg.get("options", {}), "source": c.source, "position": c.position,
            "problems": engine.validate(c.analysis_type, cfg, v),
            "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
            "last_run": run_out(last) if last else None}


def run_out(r: AnalysisRun) -> dict[str, Any]:
    return {"id": r.id, "configuration_id": r.configuration_id, "status": r.status, "error_code": r.error_code,
            "error_message": r.error_message, "summary": r.result_summary_json, "duration_ms": r.duration_ms,
            "dataset_version_id": r.dataset_version_id, "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None}


@router.get("/configurations")
def list_configs(project_id: int, user: CurrentUser, db: DB, limit: int = Query(200, ge=1, le=500),
                 offset: int = Query(0, ge=0)):
    get_project(db, user, project_id)
    stmt = select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AnalysisConfiguration.position, AnalysisConfiguration.id).limit(limit).offset(offset))
    return {"items": [config_out(db, c) for c in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/configurations", status_code=201)
def create_config(body: ConfigIn, user: CurrentUser, db: DB):
    project = get_project(db, user, body.project_id)
    v = get_version(db, user, body.dataset_version_id)
    if db.get(Dataset, v.dataset_id).project_id != project.id:
        raise AppError("invalid_dataset", "The dataset does not belong to this project.", 422)
    if body.analysis_type not in REGISTRY:
        raise AppError("unknown_analysis", f"Unknown analysis type '{body.analysis_type}'.", 422)
    pos = (db.scalar(select(func.max(AnalysisConfiguration.position))
                     .where(AnalysisConfiguration.project_id == project.id)) or 0) + 1
    cfg = {"variables": body.variables, "options": body.options}
    if body.rec_key:
        cfg["rec_key"] = body.rec_key
    c = AnalysisConfiguration(project_id=project.id, dataset_version_id=v.id, analysis_type=body.analysis_type,
                              name=body.name, configuration_json=cfg, source=body.source, position=pos)
    db.add(c)
    project.updated_at = datetime.now(UTC)
    db.commit()
    return config_out(db, c, v)


@router.get("/configurations/{config_id}")
def read_config(config_id: int, user: CurrentUser, db: DB):
    return config_out(db, get_configuration(db, user, config_id))


@router.patch("/configurations/{config_id}")
def update_config(config_id: int, body: ConfigPatch, user: CurrentUser, db: DB):
    c = get_configuration(db, user, config_id)
    cfg = dict(c.configuration_json or {})
    if body.variables is not None:
        cfg["variables"] = body.variables
    if body.options is not None:
        cfg["options"] = body.options
    c.configuration_json = cfg
    if body.name is not None:
        c.name = body.name or None
    if body.position is not None:
        c.position = body.position
    if body.dataset_version_id is not None:
        v = get_version(db, user, body.dataset_version_id)
        old = db.get(DatasetVersion, c.dataset_version_id)
        if v.dataset_id != old.dataset_id:
            raise AppError("invalid_version", "Choose a version of the same dataset.", 422)
        c.dataset_version_id = v.id
    db.commit()
    return config_out(db, c)


@router.post("/configurations/{config_id}/duplicate", status_code=201)
def duplicate_config(config_id: int, user: CurrentUser, db: DB):
    c = get_configuration(db, user, config_id)
    cfg = {k: v for k, v in (c.configuration_json or {}).items() if k != "rec_key"}
    n = AnalysisConfiguration(project_id=c.project_id, dataset_version_id=c.dataset_version_id,
                              analysis_type=c.analysis_type, name=(c.name + " (copy)") if c.name else None,
                              configuration_json=cfg, source="manual", position=c.position)
    db.add(n)
    db.commit()
    return config_out(db, n)


@router.delete("/configurations/{config_id}", status_code=204)
def delete_config(config_id: int, user: CurrentUser, db: DB):
    c = get_configuration(db, user, config_id)
    db.delete(c)
    db.commit()


@router.get("/configurations/{config_id}/code")
def config_code(config_id: int, user: CurrentUser, db: DB):
    c = get_configuration(db, user, config_id)
    v = db.get(DatasetVersion, c.dataset_version_id)
    return {"code": engine.generate_code(c.analysis_type, c.configuration_json, v)}


# --------------------------------------------------------------------------- runs


class RunIn(BaseModel):
    configuration_ids: list[int] = Field(min_length=1, max_length=100)
    use_latest_version: bool = False
    wait: bool = False


@router.post("/runs", status_code=202)
def create_runs(body: RunIn, user: CurrentUser, db: DB):
    runs = []
    for cid in body.configuration_ids:
        c = get_configuration(db, user, cid)
        if body.use_latest_version:
            v = latest_version(db.get(Dataset, db.get(DatasetVersion, c.dataset_version_id).dataset_id))
            c.dataset_version_id = v.id
        r = AnalysisRun(configuration_id=c.id, dataset_version_id=c.dataset_version_id, status="queued",
                        parameters_json={"variables": (c.configuration_json or {}).get("variables", {}),
                                         "options": (c.configuration_json or {}).get("options", {})})
        db.add(r)
        runs.append(r)
    db.flush()
    if runs:
        audit(db, user, "analysis.run", get_configuration(db, user, body.configuration_ids[0]).project_id,
              runs=[r.id for r in runs])
    db.commit()
    for r in runs:
        submit(r.id, sync=body.wait)
    for r in runs:
        db.refresh(r)
    return {"items": [run_out(r) for r in runs]}


@router.get("/runs")
def list_runs(project_id: int, user: CurrentUser, db: DB, status: str | None = None,
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    get_project(db, user, project_id)
    stmt = select(AnalysisRun).join(AnalysisConfiguration).where(AnalysisConfiguration.project_id == project_id)
    if status:
        stmt = stmt.where(AnalysisRun.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AnalysisRun.id.desc()).limit(limit).offset(offset))
    return {"items": [run_out(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}")
def read_run(run_id: int, user: CurrentUser, db: DB):
    return run_out(get_run(db, user, run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, user: CurrentUser, db: DB):
    r = get_run(db, user, run_id)
    if r.status in ("queued", "running"):
        r.status = "cancelled"
        r.completed_at = datetime.now(UTC)
        db.commit()
    return run_out(r)


@router.get("/runs/{run_id}/results")
def run_results(run_id: int, user: CurrentUser, db: DB):
    r = get_run(db, user, run_id)
    res = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == r.id))
    if res is None:
        raise AppError("no_result", "This run has no result yet." if r.status in ("queued", "running")
                       else (r.error_message or "This run did not produce a result."), 404)
    return {"run": run_out(r), "result": res.result_json, "edited_interpretation": res.edited_interpretation,
            "result_id": res.id}


class InterpretationIn(BaseModel):
    text: str | None = Field(None, max_length=20000)


@router.put("/runs/{run_id}/interpretation")
def edit_interpretation(run_id: int, body: InterpretationIn, user: CurrentUser, db: DB):
    r = get_run(db, user, run_id)
    res = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == r.id))
    if res is None:
        raise AppError("no_result", "This run has no result.", 404)
    res.edited_interpretation = (body.text or "").strip() or None
    db.commit()
    return {"edited_interpretation": res.edited_interpretation}


@router.get("/results")
def latest_results(project_id: int, user: CurrentUser, db: DB):
    """Latest completed (or failed) run for every configuration, with full results, in workspace order."""
    get_project(db, user, project_id)
    configs = db.scalars(select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == project_id)
                         .order_by(AnalysisConfiguration.position, AnalysisConfiguration.id)).all()
    items = []
    for c in configs:
        r = db.scalar(select(AnalysisRun).where(AnalysisRun.configuration_id == c.id,
                                                AnalysisRun.status.in_(["completed", "failed"]))
                      .order_by(AnalysisRun.id.desc()))
        if r is None:
            continue
        res = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == r.id))
        items.append({"configuration": {"id": c.id, "name": c.name, "analysis_type": c.analysis_type},
                      "run": run_out(r), "result": res.result_json if res else None,
                      "edited_interpretation": res.edited_interpretation if res else None})
    return {"items": items}
