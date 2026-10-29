from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import analyses, auth, datasets, exports, misc, projects, python_console, reports, sql
from .config import BACKEND_DIR, get_settings
from .errors import install_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    s.ensure_dirs()
    run_migrations()
    if s.environment == "production" and s.secret_key == "dev-insecure-change-me":
        raise RuntimeError("Set STATEASE_SECRET_KEY before running in production.")
    from .jobs import recover_interrupted

    recover_interrupted()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="StatEase Analytics API", version="1.0.0", lifespan=lifespan,
                  openapi_url=None, docs_url=None, redoc_url=None,
                  description="Statistical analysis API: projects, datasets, analyses, exports and developer tools.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    install_handlers(app)
    api = APIRouter(prefix="/api/v1")
    for r in (auth.router, projects.router, datasets.router, reports.router, analyses.router, exports.router, misc.router,
              sql.router, python_console.router):
        api.include_router(r)
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
