from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import get_settings
from ..demo import DEMOS, create_demo_project, list_demos, public_preview
from ..deps import DB, CurrentUser, audit
from ..errors import NotFound
from ..models import AnalysisConfiguration, AnalysisRun, Project
from .projects import project_out

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/jobs")
def jobs(user: CurrentUser, db: DB):
    """Queued and running analyses across the user's projects (polled by the UI for progress)."""
    rows = db.scalars(select(AnalysisRun).join(AnalysisConfiguration).join(Project, Project.id == AnalysisConfiguration.project_id)
                      .where(Project.owner_id == user.id, AnalysisRun.status.in_(["queued", "running"]))
                      .order_by(AnalysisRun.id))
    return {"items": [{"id": r.id, "type": "analysis", "status": r.status, "configuration_id": r.configuration_id,
                       "project_id": r.configuration.project_id, "created_at": r.created_at.isoformat()} for r in rows]}


class DemoIn(BaseModel):
    key: str = Field("fertilizer", pattern="^(fertilizer|experiment|survey)$")


@router.post("/demo", status_code=201)
def demo(user: CurrentUser, db: DB, body: DemoIn | None = None):
    project, report_id = create_demo_project(db, user, (body or DemoIn()).key)
    audit(db, user, "project.demo", project.id)
    db.commit()
    return {**project_out(db, project), "report_id": report_id}


# Public (no sign-in): demo listing and read-only previews for the landing page.


@router.get("/public/demos")
def public_demos():
    return {"items": list_demos()}


@router.get("/public/demos/{key}")
def public_demo(key: str):
    if key not in DEMOS:
        raise NotFound("Demo")
    return public_preview(key)


@router.get("/public/demos/{key}/sample.csv")
def demo_csv(key: str):
    if key not in DEMOS:
        raise NotFound("Demo")
    return Response(DEMOS[key]["data"]().write_csv(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sample_{key}_fictional.csv"'})


@router.get("/system/limits")
def limits(user: CurrentUser):
    s = get_settings()
    return {"max_upload_mb": s.max_upload_mb, "max_excel_mb": s.max_excel_mb, "analysis_max_rows": s.analysis_max_rows,
            "shapiro_max_n": s.shapiro_max_n, "sql_timeout_seconds": s.sql_timeout_seconds,
            "sql_max_rows": s.sql_max_rows, "python_console": s.enable_python_console, "auth_mode": s.auth_mode,
            "google_sign_in": s.google_enabled,
            "database": "postgresql" if s.database_url.startswith("postgresql") else "sqlite"}
