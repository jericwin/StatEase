from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..config import get_settings
from ..deps import DB, CurrentUser, audit, get_dataset, require_role
from ..dev.sandbox import TEMPLATES, run_code
from ..errors import AppError
from ..models import QueryHistory
from ..services import latest_version
from ..storage import resolve

router = APIRouter(prefix="/python", tags=["python console"])


class RunIn(BaseModel):
    code: str = Field(min_length=1, max_length=100_000)
    dataset_id: int | None = None


@router.get("/templates")
def templates(user: CurrentUser):
    require_role(user, "developer")
    s = get_settings()
    return {"enabled": s.enable_python_console, "templates": TEMPLATES,
            "limits": {"timeout_seconds": s.python_timeout_seconds, "memory_mb": s.python_memory_mb}}


@router.post("/run")
def run(body: RunIn, user: CurrentUser, db: DB):
    s = get_settings()
    if not s.enable_python_console:
        raise AppError("console_disabled", "The Python console is disabled on this server. An administrator can enable "
                                           "it with STATEASE_ENABLE_PYTHON_CONSOLE=true (see docs/SECURITY.md).", 403)
    require_role(user, "admin")
    path = None
    project_id = None
    if body.dataset_id:
        ds = get_dataset(db, user, body.dataset_id)
        path = resolve(latest_version(ds).data_path)
        project_id = ds.project_id
    result = run_code(body.code, path)
    db.add(QueryHistory(owner_id=user.id, project_id=project_id, language="python", body=body.code[:20000],
                        status=result["status"], duration_ms=result.get("duration_ms"),
                        error_message=(result.get("stderr") or "")[:2000] if result["status"] != "completed" else None))
    audit(db, user, "python.run", project_id, status=result["status"])
    db.commit()
    return result
