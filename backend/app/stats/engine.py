"""Runs a configured analysis against a dataset version and returns the uniform result dict."""

from __future__ import annotations

import time
import traceback
import warnings
from typing import Any

from ..data.store import load_frame
from ..errors import AnalysisError
from ..models import DatasetVersion
from . import (  # noqa: F401 - imported for registration side effects
    anova,
    categorical,
    checks,
    codegen,
    compare,
    correlation,
    descriptives,
    nonparametric,
    regression,
    reliability,
    ttests,
)
from .base import CATEGORIES, REGISTRY, Context, VarMeta, validate_roles


def var_meta(version: DatasetVersion) -> dict[str, VarMeta]:
    return {v.column_name: VarMeta(name=v.column_name, label=v.variable_label or "", level=v.measurement_level,
                                   data_type=v.data_type, category_labels=v.category_labels_json or {},
                                   category_order=v.category_order_json or [], unit=v.unit,
                                   missing_codes=v.missing_value_codes_json or [])
            for v in version.variables}


def catalog() -> dict[str, Any]:
    return {"categories": CATEGORIES, "analyses": [s.catalog_entry() for s in REGISTRY.values()]}


def validate(analysis_type: str, config: dict[str, Any], version: DatasetVersion) -> list[str]:
    spec = REGISTRY.get(analysis_type)
    if spec is None:
        return [f"Unknown analysis type '{analysis_type}'."]
    return validate_roles(spec, config, var_meta(version))


def generate_code(analysis_type: str, config: dict[str, Any], version: DatasetVersion) -> str | None:
    spec = REGISTRY.get(analysis_type)
    if spec is None or spec.code is None:
        return None
    header = (f"# StatEase Analytics — reproducible code for: {spec.name}\n"
              f"# Dataset version {version.id} (sha256 {version.content_hash[:12]}…)\n"
              "# Requires: pandas, numpy, scipy, statsmodels, pingouin, pyarrow\n\n")
    token = codegen.FILTER.set(config.get("filter") or None)
    try:
        return header + spec.code(config, var_meta(version))
    except Exception:  # noqa: BLE001 - code generation must never break a run
        return None
    finally:
        codegen.FILTER.reset(token)


def heading(config: dict[str, Any], metas: dict[str, VarMeta]) -> str:
    """A short, variable-specific heading such as 'Satisfaction by Gender'."""
    v = config.get("variables") or {}

    def lab(x: Any) -> str:
        names = [x] if isinstance(x, str) else list(x or [])
        labels = [(metas[n].display if n in metas else n) for n in names if n]
        return ", ".join(labels[:3]) + (f" + {len(labels) - 3} more" if len(labels) > 3 else "")

    if v.get("dependent") and (v.get("group") or v.get("factor") or v.get("factors")):
        by = v.get("group") or v.get("factor") or v.get("factors")
        text = f"{lab(v['dependent'])} by {lab(by)}"
        if v.get("covariates"):
            text += f", adjusting for {lab(v['covariates'])}"
        return text
    if v.get("dependent") and v.get("predictors"):
        return f"{lab(v['dependent'])} from {lab(v['predictors'])}"
    if v.get("first") and v.get("second"):
        return f"{lab(v['first'])} vs {lab(v['second'])}"
    if v.get("rows") and v.get("columns"):
        return f"{lab(v['rows'])} × {lab(v['columns'])}"
    if v.get("x") and v.get("y"):
        return f"{lab(v['x'])} and {lab(v['y'])}"
    if v.get("within"):
        return lab(v["within"]) + (f" by {lab(v['between'])}" if v.get("between") else "")
    for key in ("variables", "items", "variable"):
        if v.get(key):
            return lab(v[key])
    return ""


def run(analysis_type: str, config: dict[str, Any], version: DatasetVersion, settings: dict[str, Any],
        max_rows: int | None = None) -> dict[str, Any]:
    """Returns {"status": "completed"|"failed", "result"|"error", "duration_ms"}."""
    spec = REGISTRY.get(analysis_type)
    if spec is None:
        return {"status": "failed", "error": {"code": "unknown_analysis", "message": f"Unknown analysis '{analysis_type}'."}}
    metas = var_meta(version)
    problems = validate_roles(spec, config, metas)
    if problems:
        return {"status": "failed", "error": {"code": "invalid_variables", "message": " ".join(problems),
                                              "problems": problems}}
    ctx = Context(lambda cols: load_frame(version, cols, max_rows), metas, settings)
    ctx.filter = config.get("filter") or None
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            res = spec.run(ctx, config)
        out = res.to_dict()
        for w in caught:
            msg = str(w.message)
            if any(s in msg for s in ("divide by zero", "invalid value", "Precision loss", "catastrophic cancellation")):
                out["warnings"].append("A numerical warning occurred during calculation (" + msg.split("\n")[0][:160]
                                       + "). Check the data for near-constant values.")
        if ctx.filter_note:
            out["notes"].insert(0, ctx.filter_note)
            out["filter"] = ctx.filter
        if ctx.scored_ordinals:
            out["notes"].append("Ordered text categories were scored 1, 2, … in their declared order for: "
                                + ", ".join(ctx.label(c) for c in sorted(ctx.scored_ordinals)) + ".")
        out["heading"] = heading(config, metas)
        if ctx.filter_note and config.get("filter"):
            out["heading"] += f" ({', '.join(str(v) for v in config['filter']['values'])})"
        out["code"] = generate_code(analysis_type, config, version)
        out["dataset_version_id"] = version.id
        return {"status": "completed", "result": out, "duration_ms": (time.perf_counter() - t0) * 1000}
    except AnalysisError as exc:
        return {"status": "failed", "duration_ms": (time.perf_counter() - t0) * 1000,
                "error": {"code": exc.code, "message": exc.message, "suggestion": exc.suggestion}}
    except Exception as exc:  # noqa: BLE001 - never crash the app on a statistical failure
        return {"status": "failed", "duration_ms": (time.perf_counter() - t0) * 1000,
                "error": {"code": "calculation_error",
                          "message": f"The analysis could not be completed: {type(exc).__name__}: {str(exc)[:300]}",
                          "trace": traceback.format_exc(limit=3)}}
