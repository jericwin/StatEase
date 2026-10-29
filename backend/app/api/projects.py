from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, audit, get_project
from ..models import (
    AnalysisConfiguration,
    AnalysisRun,
    AuditLog,
    Dataset,
    DatasetVersion,
    Export,
    Project,
    Variable,
)
from ..storage import new_relative_path, resolve

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    status: str | None = Field(None, pattern="^(active|archived)$")
    settings: dict[str, Any] | None = None


class ProjectSettings(BaseModel):
    alpha: float = Field(0.05, gt=0, lt=0.5)
    ci_level: float = Field(0.95, gt=0.5, lt=1)
    p_style: str = Field("apa", pattern="^(apa|academic)$")
    decimals: int = Field(2, ge=0, le=6)


def project_out(db, p: Project) -> dict:
    n_datasets = db.scalar(select(func.count(Dataset.id)).where(Dataset.project_id == p.id))
    n_analyses = db.scalar(select(func.count(AnalysisConfiguration.id)).where(AnalysisConfiguration.project_id == p.id))
    n_results = db.scalar(select(func.count(AnalysisRun.id)).join(AnalysisConfiguration)
                          .where(AnalysisConfiguration.project_id == p.id, AnalysisRun.status == "completed"))
    return {"id": p.id, "name": p.name, "description": p.description, "status": p.status, "is_demo": p.is_demo,
            "settings": {**ProjectSettings().model_dump(), **(p.settings_json or {})},
            "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat(),
            "counts": {"datasets": n_datasets, "analyses": n_analyses, "results": n_results}}


@router.get("")
def list_projects(user: CurrentUser, db: DB, status: str = Query("active", pattern="^(active|archived|all)$"),
                  q: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    stmt = select(Project).where(Project.owner_id == user.id)
    if status != "all":
        stmt = stmt.where(Project.status == status)
    if q:
        stmt = stmt.where(Project.name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [project_out(db, p) for p in rows], "total": total, "limit": limit, "offset": offset}


@router.post("", status_code=201)
def create_project(body: ProjectIn, user: CurrentUser, db: DB):
    p = Project(owner_id=user.id, name=body.name.strip(), description=body.description, settings_json={})
    db.add(p)
    db.flush()
    audit(db, user, "project.create", p.id)
    db.commit()
    return project_out(db, p)


@router.get("/{project_id}")
def read_project(project_id: int, user: CurrentUser, db: DB):
    return project_out(db, get_project(db, user, project_id))


@router.patch("/{project_id}")
def update_project(project_id: int, body: ProjectPatch, user: CurrentUser, db: DB):
    p = get_project(db, user, project_id)
    if body.name is not None:
        p.name = body.name.strip()
    if body.description is not None:
        p.description = body.description
    if body.status is not None:
        p.status = body.status
        audit(db, user, f"project.{'archive' if body.status == 'archived' else 'restore'}", p.id)
    if body.settings is not None:
        p.settings_json = ProjectSettings(**{**(p.settings_json or {}), **body.settings}).model_dump()
    db.commit()
    return project_out(db, p)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, user: CurrentUser, db: DB):
    p = get_project(db, user, project_id)
    paths = [v.data_path for d in p.datasets for v in d.versions] + [d.storage_path for d in p.datasets if d.storage_path]
    paths += [e.artifact_path for e in db.scalars(select(Export).where(Export.project_id == p.id)) if e.artifact_path]
    audit(db, user, "project.delete", None, deleted_project=p.id, name=p.name)
    db.delete(p)
    db.commit()
    for rel in paths:
        try:
            resolve(rel).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - metadata is gone; orphaned files are harmless
            pass


@router.post("/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: int, user: CurrentUser, db: DB):
    src = get_project(db, user, project_id)
    dst = Project(owner_id=user.id, name=f"{src.name} (copy)"[:200], description=src.description,
                  settings_json=dict(src.settings_json or {}))
    db.add(dst)
    db.flush()
    version_map: dict[int, int] = {}
    for ds in src.datasets:
        nd = Dataset(project_id=dst.id, name=ds.name, source_filename=ds.source_filename, storage_path=None,
                     format=ds.format, row_count=ds.row_count, column_count=ds.column_count,
                     lineage_json=dict(ds.lineage_json or {}))
        db.add(nd)
        db.flush()
        for v in ds.versions:
            rel = new_relative_path("datasets", ".parquet")
            shutil.copy2(resolve(v.data_path), resolve(rel))
            nv = DatasetVersion(dataset_id=nd.id, version_number=v.version_number, schema_json=v.schema_json,
                                profile_json=v.profile_json, data_path=rel, content_hash=v.content_hash,
                                row_count=v.row_count, note=v.note)
            db.add(nv)
            db.flush()
            version_map[v.id] = nv.id
            for var in v.variables:
                db.add(Variable(dataset_version_id=nv.id, **{c: getattr(var, c) for c in (
                    "position", "column_name", "variable_label", "measurement_level", "data_type",
                    "category_labels_json", "category_order_json", "missing_value_codes_json", "unit",
                    "inferred_level", "inference_note", "scale_group")}))
    for c in db.scalars(select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == src.id)):
        if c.dataset_version_id in version_map:
            db.add(AnalysisConfiguration(project_id=dst.id, dataset_version_id=version_map[c.dataset_version_id],
                                         analysis_type=c.analysis_type, name=c.name,
                                         configuration_json=c.configuration_json, source=c.source, position=c.position))
    audit(db, user, "project.duplicate", dst.id, source=src.id)
    db.commit()
    return project_out(db, dst)


@router.get("/{project_id}/export-metadata")
def export_metadata(project_id: int, user: CurrentUser, db: DB):
    """Project metadata (datasets, variables, analysis configurations) as JSON; no data values."""
    p = get_project(db, user, project_id)
    return {
        "project": {"name": p.name, "description": p.description, "settings": p.settings_json},
        "datasets": [{"name": d.name, "source_filename": d.source_filename, "rows": d.row_count,
                      "lineage": d.lineage_json,
                      "versions": [{"version": v.version_number, "sha256": v.content_hash, "note": v.note,
                                    "variables": [{"name": x.column_name, "label": x.variable_label,
                                                   "level": x.measurement_level, "categories": x.category_labels_json,
                                                   "order": x.category_order_json,
                                                   "missing_codes": x.missing_value_codes_json} for x in v.variables]}
                                   for v in d.versions]} for d in p.datasets],
        "analyses": [{"type": c.analysis_type, "name": c.name, "configuration": c.configuration_json}
                     for c in db.scalars(select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == p.id))],
    }


@router.get("/{project_id}/activity")
def activity(project_id: int, user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=200)):
    get_project(db, user, project_id)
    rows = db.scalars(select(AuditLog).where(AuditLog.project_id == project_id)
                      .order_by(AuditLog.created_at.desc()).limit(limit))
    return {"items": [{"action": a.action, "details": a.details_json, "created_at": a.created_at.isoformat()}
                      for a in rows]}
