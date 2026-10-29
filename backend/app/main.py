from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import storage
from .api import auth, misc, projects

try:
    from .api import datasets
except Exception:
    datasets = None

try:
    from .api import reports
except Exception:
    reports = None

try:
    from .api import analyses
except Exception:
    analyses = None

try:
    from .api import exports
except Exception:
    exports = None

try:
    from .api import sql
except Exception:
    sql = None

try:
    from .api import python_console
except Exception:
    python_console = None

from .config import BACKEND_DIR, get_settings
from .errors import install_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_migrations() -> None:
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
        command.upgrade(cfg, "head")
    except Exception as e:
        logging.warning("Migrations skipped or failed: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    s.ensure_dirs()
    if not os.environ.get("VERCEL") and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        run_migrations()
    if s.environment == "production" and s.secret_key == "dev-insecure-change-me":
        raise RuntimeError("Set STATEASE_SECRET_KEY before running in production.")
    try:
        from .jobs import recover_interrupted
        recover_interrupted()
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="StatEase Analytics API", version="1.0.0", lifespan=lifespan,
                  openapi_url=None, docs_url=None, redoc_url=None,
                  description="Statistical analysis API: projects, datasets, analyses, exports and developer tools.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    install_handlers(app)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    if s.persist_files_in_db:
        @app.middleware("http")
        async def persist_files(request: Request, call_next):
            touched = storage.track_request()
            try:
                return await call_next(request)
            finally:
                await run_in_threadpool(storage.persist_tracked, touched)

    api = APIRouter(prefix="/api/v1")
    for r in (auth.router, projects.router, misc.router):
        api.include_router(r)
    for opt in (datasets, reports, analyses, exports, sql, python_console):
        if opt and hasattr(opt, "router"):
            api.include_router(opt.router)
    app.include_router(api)

    # Serve the built frontend when present (single-container deployment).
    dist = Path(BACKEND_DIR).parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (dist / path).resolve()
            if path and target.is_file() and target.is_relative_to(dist.resolve()):
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
