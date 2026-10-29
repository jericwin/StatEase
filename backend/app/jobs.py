"""Background execution of analysis runs (thread pool). Runs survive in the database across restarts."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import AnalysisConfiguration, AnalysisResult, AnalysisRun, DatasetVersion, Project
from .stats import engine

log = logging.getLogger("statease.jobs")
_executor: ThreadPoolExecutor | None = None


def executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=get_settings().analysis_workers, thread_name_prefix="analysis")
    return _executor


def project_settings(project: Project) -> dict:
    s = get_settings()
    return {"alpha": 0.05, "ci_level": 0.95, "p_style": "apa", "decimals": 2, "shapiro_max_n": s.shapiro_max_n,
            **(project.settings_json or {})}


def execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None or run.status != "queued":
            return
        run.status, run.started_at = "running", datetime.now(UTC)
        db.commit()
        config = db.get(AnalysisConfiguration, run.configuration_id)
        version = db.get(DatasetVersion, run.dataset_version_id)
        project = db.get(Project, config.project_id)
        settings = project_settings(project)
        out = engine.run(config.analysis_type, run.parameters_json, version, settings,
                         max_rows=get_settings().analysis_max_rows)
        db.refresh(run)
        if run.status == "cancelled":
            return
        run.completed_at = datetime.now(UTC)
        run.duration_ms = out.get("duration_ms")
        if out["status"] == "completed":
            result = out["result"]
            run.status = "completed"
            run.result_summary_json = {"title": result["title"], "n": result["n"], **(result.get("summary") or {}),
                                       "warnings": len(result.get("warnings") or [])}
            db.add(AnalysisResult(analysis_run_id=run.id, result_type="full", result_json=result))
        else:
            run.status = "failed"
            run.error_code = out["error"].get("code")
            run.error_message = out["error"].get("message")
            run.result_summary_json = {"suggestion": out["error"].get("suggestion"),
                                       "problems": out["error"].get("problems")}
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.exception("analysis run %s crashed", run_id)
        db.rollback()
        run = db.get(AnalysisRun, run_id)
        if run:
            run.status, run.error_code, run.error_message = "failed", "internal_error", str(exc)[:500]
            run.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def submit(run_id: int, sync: bool = False) -> None:
    if sync:
        execute(run_id)
    else:
        executor().submit(execute, run_id)


def recover_interrupted() -> None:
    """Re-queue runs that were queued or running when the server stopped."""
    db = SessionLocal()
    try:
        stale = db.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(["queued", "running"]))).all()
        for r in stale:
            r.status = "queued"
        db.commit()
        for r in stale:
            submit(r.id)
    finally:
        db.close()
