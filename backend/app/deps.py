from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import AppError, Forbidden, NotFound
from .models import AnalysisConfiguration, AnalysisRun, AuditLog, Dataset, DatasetVersion, Project, User
from .security import decode_token, hash_password

LOCAL_EMAIL = "local@statease.local"

DB = Annotated[Session, Depends(get_db)]

ROLE_RANK = {"analyst": 0, "developer": 1, "admin": 2}


def ensure_local_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == LOCAL_EMAIL))
    if user is None:
        import secrets

        user = User(email=LOCAL_EMAIL, password_hash=hash_password(secrets.token_urlsafe(24)),
                    display_name="Local user", role="admin")
        db.add(user)
        db.commit()
    return user


def get_current_user(db: DB, authorization: Annotated[str | None, Header()] = None) -> User:
    if get_settings().auth_mode == "local":
        return ensure_local_user(db)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("unauthorized", "Sign in to continue.", 401)
    decoded = decode_token(authorization.split(" ", 1)[1].strip())
    user = db.get(User, decoded[0]) if decoded else None
    if user is None or not user.is_active or decoded[1] != user.token_version:
        raise AppError("unauthorized", "Your session has expired. Sign in again.", 401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(user: User, role: str) -> None:
    if ROLE_RANK.get(user.role, 0) < ROLE_RANK[role]:
        raise Forbidden(f"This feature requires the '{role}' role.")


def get_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or (project.owner_id != user.id and user.role != "admin"):
        raise NotFound("Project")
    return project


def get_dataset(db: Session, user: User, dataset_id: int) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFound("Dataset")
    get_project(db, user, ds.project_id)
    return ds


def get_version(db: Session, user: User, version_id: int) -> DatasetVersion:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFound("Dataset version")
    get_dataset(db, user, v.dataset_id)
    return v


def get_configuration(db: Session, user: User, config_id: int) -> AnalysisConfiguration:
    c = db.get(AnalysisConfiguration, config_id)
    if c is None:
        raise NotFound("Analysis")
    get_project(db, user, c.project_id)
    return c


def get_run(db: Session, user: User, run_id: int) -> AnalysisRun:
    r = db.get(AnalysisRun, run_id)
    if r is None:
        raise NotFound("Analysis run")
    get_configuration(db, user, r.configuration_id)
    return r


def audit(db: Session, user: User | None, action: str, project_id: int | None = None, **details) -> None:
    db.add(AuditLog(user_id=user.id if user else None, project_id=project_id, action=action, details_json=details))
