from __future__ import annotations

from typing import Any

import pandas as pd

from app.stats import engine  # noqa: F401 - registers analyses
from app.stats.base import REGISTRY, Context, VarMeta, validate_roles


def run(df: pd.DataFrame, levels: dict[str, str], analysis: str, variables: dict[str, Any],
        options: dict[str, Any] | None = None, alpha: float = 0.05, **meta) -> dict[str, Any]:
    metas = {c: VarMeta(name=c, label="", level=levels.get(c, "numeric"),
                        data_type="string" if df[c].dtype == object else "decimal",
                        category_labels=meta.get("labels", {}).get(c, {}), category_order=meta.get("order", {}).get(c, []))
             for c in df.columns}
    spec = REGISTRY[analysis]
    config = {"variables": variables, "options": options or {}}
    problems = validate_roles(spec, config, metas)
    assert not problems, problems
    ctx = Context(lambda cols: df[cols].copy(), metas, {"alpha": alpha})
    out = spec.run(ctx, config).to_dict()
    out["_code"] = spec.code(config, metas) if spec.code else None
    return out


def table(result: dict[str, Any], table_id: str) -> list[dict[str, Any]]:
    return next(t for t in result["tables"] if t["id"] == table_id)["rows"]
