"""Application configuration, loaded from environment variables (prefix ``STATEASE_``)."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _get_default_database_url() -> str:
    url = (
        os.environ.get("STATEASE_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_PRISMA_URL")
    )
    if url:
        return url
    return f"sqlite:///{(BACKEND_DIR / 'var' / 'statease.db').as_posix()}"


def _get_default_storage_dir() -> Path:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/storage")
    return BACKEND_DIR / "var" / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STATEASE_", env_file=".env", extra="ignore")

    environment: Literal["development", "production", "test"] = "development"

    # Metadata database. SQLite by default (single-user local mode); set a
    # postgresql+psycopg:// URL for the full multi-user deployment.
    database_url: str = Field(default_factory=_get_default_database_url)

    @field_validator("database_url", mode="after")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        if not v or v.startswith("sqlite:///"):
            env_db = (
                os.environ.get("STATEASE_DATABASE_URL")
                or os.environ.get("POSTGRES_URL")
                or os.environ.get("DATABASE_URL")
            )
            if env_db:
                v = env_db
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # Root for uploaded files, Parquet datasets and generated reports.
    storage_dir: Path = Field(default_factory=_get_default_storage_dir)

    # "password" (default): accounts with email/password and optional Google sign-in.
    # "local": a single local administrator is provisioned automatically; no login (offline use only).
    auth_mode: Literal["local", "password"] = "password"
    secret_key: str = "dev-insecure-change-me"
    token_ttl_hours: int = 72
    allow_registration: bool = True

    # Public base URL of the app (used for OAuth redirect URIs and password-reset links).
    public_url: str = "http://localhost:8000"

    # Google OAuth 2.0 / OpenID Connect (Web application client). Leave empty to hide Google sign-in.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Outgoing e-mail for password resets. Without SMTP the reset link is written to the server log.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "StatEase Analytics <no-reply@localhost>"
    smtp_starttls: bool = True
    password_reset_minutes: int = 60
    # New email/password accounts must confirm their address with an e-mailed code.
    require_email_verification: bool = True
    verification_code_minutes: int = 15

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    cors_origins: list[str] = ["*"]

    # Resource limits
    max_upload_mb: int = 512
    max_excel_mb: int = 100
    preview_max_rows: int = 500
    analysis_max_rows: int = 5_000_000
    shapiro_max_n: int = 5000
    analysis_workers: int = 2

    # SQL workbench
    sql_timeout_seconds: float = 30.0
    sql_max_rows: int = 10_000
    sql_export_max_rows: int = 1_000_000

    # Python console (disabled by default; see docs/SECURITY.md)
    enable_python_console: bool = False
    python_timeout_seconds: float = 30.0
    python_memory_mb: int = 1024

    @property
    def datasets_dir(self) -> Path:
        return self.storage_dir / "datasets"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.storage_dir / "exports"

    @property
    def sqlite_connections_dir(self) -> Path:
        return self.storage_dir / "sqlite"

    @property
    def sandbox_dir(self) -> Path:
        return self.storage_dir / "sandbox"

    def ensure_dirs(self) -> None:
        try:
            for d in (self.storage_dir, self.datasets_dir, self.uploads_dir, self.exports_dir,
                      self.sqlite_connections_dir, self.sandbox_dir):
                d.mkdir(parents=True, exist_ok=True)
            if self.database_url.startswith("sqlite:///"):
                Path(self.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
