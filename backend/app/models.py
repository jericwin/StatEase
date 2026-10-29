"""Relational metadata schema. Analytical data lives in Parquet files, never in these tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JSONType, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    # admin: everything incl. destructive SQL and Python console
    # developer: developer tools (read-only SQL, API explorer)
    # analyst: statistical features only
    role: Mapped[str] = mapped_column(String(20), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Google account subject identifier (OpenID Connect "sub"), when linked.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    has_password: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Incremented on password reset or "sign out everywhere"; older tokens become invalid.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the token; the token itself is only ever sent to the user.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EmailCode(Base):
    """Short numeric code e-mailed to confirm an address. Only a keyed hash of the code is stored."""

    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20), default="verify")
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | archived
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    datasets: Mapped[list[Dataset]] = relationship(back_populates="project", cascade="all, delete-orphan",
                                                   passive_deletes=True)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_filename: Mapped[str | None] = mapped_column(String(255))
    # Relative path (under storage_dir) of the untouched original upload, if any.
    storage_path: Mapped[str | None] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20))  # csv | tsv | xlsx | xls | json | parquet | sql
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    # Lineage: datasets derived from another dataset via SQL or a transformation.
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL", use_alter=True), nullable=True)
    lineage_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="datasets")
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True,
        foreign_keys="DatasetVersion.dataset_id", order_by="DatasetVersion.version_number")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # Relative path (under storage_dir) of the Parquet file holding this version.
    data_path: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="versions", foreign_keys=[dataset_id])
    variables: Mapped[list[Variable]] = relationship(back_populates="version", cascade="all, delete-orphan",
                                                     passive_deletes=True, order_by="Variable.position")


class Variable(Base):
    __tablename__ = "variables"
    __table_args__ = (UniqueConstraint("dataset_version_id", "column_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"),
                                                    index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    column_name: Mapped[str] = mapped_column(String(255))
    variable_label: Mapped[str | None] = mapped_column(String(255))
    # numeric | ordinal | nominal | binary | date | datetime | text | identifier
    measurement_level: Mapped[str] = mapped_column(String(20))
    # Physical storage type: integer | decimal | string | boolean | date | datetime
    data_type: Mapped[str] = mapped_column(String(20))
    category_labels_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    category_order_json: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    missing_value_codes_json: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    unit: Mapped[str | None] = mapped_column(String(50))
    inferred_level: Mapped[str | None] = mapped_column(String(20))
    inference_note: Mapped[str | None] = mapped_column(Text)
    scale_group: Mapped[str | None] = mapped_column(String(120))

    version: Mapped[DatasetVersion] = relationship(back_populates="variables")


class AnalysisConfiguration(Base):
    __tablename__ = "analysis_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"),
                                                    index=True)
    analysis_type: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | recommended
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    runs: Mapped[list[AnalysisRun]] = relationship(back_populates="configuration", cascade="all, delete-orphan",
                                                   passive_deletes=True, order_by="AnalysisRun.id")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("analysis_configurations.id", ondelete="CASCADE"),
                                                  index=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    # queued | running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    configuration: Mapped[AnalysisConfiguration] = relationship(back_populates="runs")
    results: Mapped[list[AnalysisResult]] = relationship(back_populates="run", cascade="all, delete-orphan",
                                                         passive_deletes=True)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    result_type: Mapped[str] = mapped_column(String(40), default="full")
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # User-edited interpretation text (kept separate from the computed result).
    edited_interpretation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    run: Mapped[AnalysisRun] = relationship(back_populates="results")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    export_format: Mapped[str] = mapped_column(String(10))  # docx | xlsx | csv | parquet | json
    options_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | completed | failed
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DbConnection(Base):
    """External database connection profile. Secrets are stored encrypted and never returned."""

    __tablename__ = "db_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    engine: Mapped[str] = mapped_column(String(20))  # sqlite | postgresql | mysql
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    allow_writes: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("db_connections.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(10), default="sql")  # sql | python
    name: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("db_connections.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(10), default="sql")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class Report(Base):
    """An editable research report: objectives plus an ordered list of blocks (tables, charts, text)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    objectives_json: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    blocks_json: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
