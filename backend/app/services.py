"""Domain operations shared by the API, SQL workbench, transformations and demo data."""

from __future__ import annotations

from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from .data import store
from .data.importer import file_hash
from .data.inference import infer_variables
from .models import Dataset, DatasetVersion, Project, Variable
from .storage import resolve

VAR_FIELDS = {"variable_label", "measurement_level", "category_labels_json", "category_order_json",
              "missing_value_codes_json", "unit", "scale_group"}


def _variables_from_parquet(data_path: str, overrides: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    sample = pl.scan_parquet(resolve(data_path)).head(20000).collect()
    inferred = infer_variables(sample)
    for v in inferred:
        o = (overrides or {}).get(v["column_name"]) or {}
        for k in ("measurement_level", "variable_label", "unit"):
            if o.get(k):
                v[k] = o[k]
        if o.get("category_order") is not None:
            v["category_order"] = o["category_order"]
        if o.get("category_labels"):
            v["category_labels"] = o["category_labels"]
        if o.get("missing_codes"):
            v["missing_codes"] = o["missing_codes"]
    return inferred


def add_version(db: Session, dataset: Dataset, data_path: str, *, note: str | None = None,
                overrides: dict[str, dict[str, Any]] | None = None,
                carry_from: DatasetVersion | None = None) -> DatasetVersion:
    """Register a Parquet file as a new dataset version with inferred (or carried-over) variable metadata."""
    path = resolve(data_path)
    rows = pl.scan_parquet(path).select(pl.len()).collect().item()
    number = (max((v.version_number for v in dataset.versions), default=0) + 1)
    version = DatasetVersion(version_number=number, data_path=data_path, content_hash=file_hash(path), row_count=rows,
                             note=note)
    dataset.versions.append(version)
    db.flush()
    inferred = _variables_from_parquet(data_path, overrides)
    previous = {v.column_name: v for v in carry_from.variables} if carry_from else {}
    for i, v in enumerate(inferred):
        prev = previous.get(v["column_name"])
        var = Variable(dataset_version_id=version.id, position=i, column_name=v["column_name"],
                       data_type=v["data_type"], inferred_level=v["inferred_level"],
                       inference_note=v["inference_note"], measurement_level=v["measurement_level"],
                       variable_label=v.get("variable_label"), unit=v.get("unit"),
                       category_order_json=v.get("category_order") or [],
                       category_labels_json=v.get("category_labels") or {},
                       missing_value_codes_json=v.get("missing_codes") or [], scale_group=v.get("scale_group"))
        if prev is not None:
            for f in VAR_FIELDS:
                setattr(var, f, getattr(prev, f))
        db.add(var)
    db.flush()
    db.refresh(version)
    version.schema_json = {"columns": [{"name": v.column_name, "type": v.data_type} for v in version.variables]}
    version.profile_json = store.profile(version)
    dataset.row_count = rows
    dataset.column_count = len(inferred)
    db.flush()
    return version


def create_dataset(db: Session, project: Project, *, name: str, data_path: str, fmt: str,
                   source_filename: str | None = None, original_path: str | None = None,
                   overrides: dict[str, dict[str, Any]] | None = None, parent_version_id: int | None = None,
                   lineage: dict[str, Any] | None = None, note: str | None = None) -> Dataset:
    ds = Dataset(project_id=project.id, name=name[:200], source_filename=source_filename, storage_path=original_path,
                 format=fmt, parent_version_id=parent_version_id, lineage_json=lineage or {})
    db.add(ds)
    db.flush()
    add_version(db, ds, data_path, note=note or "Initial import", overrides=overrides)
    return ds


def latest_version(ds: Dataset) -> DatasetVersion:
    return max(ds.versions, key=lambda v: v.version_number)


def refresh_profile(db: Session, version: DatasetVersion) -> None:
    version.profile_json = store.profile(version)
    db.flush()
