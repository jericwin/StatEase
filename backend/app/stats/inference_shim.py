"""Variable metadata for in-memory frames (used by the public demo previews)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ..data.inference import infer_variables
from .base import VarMeta


def infer_meta(df: pl.DataFrame, overrides: dict[str, tuple[str, list[Any] | None]] | None = None) -> dict[str, VarMeta]:
    out: dict[str, VarMeta] = {}
    for v in infer_variables(df):
        level, order = (overrides or {}).get(v["column_name"], (v["measurement_level"], None))
        out[v["column_name"]] = VarMeta(name=v["column_name"], label="", level=level, data_type=v["data_type"],
                                        category_labels={}, category_order=order or v.get("category_order") or [])
    return out
