"""Report configuration (the export checklist) and the filtering it drives.

The checklist decides exactly what appears in an export: a section that is switched off is not written.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from ..stats.base import fmt_p, fmt_r

SECTION_KEYS = ["title", "dataset_description", "variables", "descriptives", "main", "assumptions", "posthoc",
                "effect_sizes", "interpretation", "charts", "methods", "alpha", "references", "date", "code"]
INFERENTIAL_KEYS = ["statistic", "df", "p", "ci", "effect"]


class ReportOptions(BaseModel):
    title: str = "Statistical Analysis Report"
    subtitle: str | None = None
    author: str | None = None
    style: str = Field("apa", pattern="^(apa|academic)$")
    decimals: int = Field(2, ge=0, le=6)
    run_ids: list[int] = Field(default_factory=list)
    sections: dict[str, bool] = Field(default_factory=lambda: {k: k not in {"code", "references"} for k in SECTION_KEYS})
    descriptive_stats: list[str] | None = None  # None = keep every column the analysis produced
    inferential: dict[str, bool] = Field(default_factory=lambda: {k: True for k in INFERENTIAL_KEYS})
    charts: dict[str, list[str]] | None = None  # run_id -> chart ids; None = all charts
    interpretation_style: str = Field("technical", pattern="^(plain|technical|both)$")
    interpretations: dict[str, str] = Field(default_factory=dict)  # run_id -> edited text
    include_data: bool = False
    include_variable_dictionary: bool = True

    def on(self, key: str) -> bool:
        return bool(self.sections.get(key, False))


PRESETS: dict[str, dict[str, Any]] = {
    "basic": {"sections": {k: k in {"title", "descriptives", "main", "interpretation", "date"} for k in SECTION_KEYS},
              "inferential": {"statistic": True, "df": True, "p": True, "ci": False, "effect": False}},
    "complete": {"sections": {k: True for k in SECTION_KEYS}, "inferential": {k: True for k in INFERENTIAL_KEYS}},
    "thesis": {"sections": {k: k not in {"code"} for k in SECTION_KEYS},
               "inferential": {k: True for k in INFERENTIAL_KEYS}, "style": "academic",
               "descriptive_stats": ["n", "mean", "sd", "min", "max", "median", "frequency", "percent", "valid_percent",
                                     "cumulative_percent"]},
    "apa": {"sections": {k: k not in {"code", "dataset_description"} for k in SECTION_KEYS},
            "inferential": {k: True for k in INFERENTIAL_KEYS}, "style": "apa"},
}


def section_of(kind: str) -> str:
    return {"descriptives": "descriptives", "frequencies": "descriptives", "main": "main", "posthoc": "posthoc",
            "effect": "effect_sizes", "assumptions": "assumptions"}.get(kind, "main")


def filter_table(table: dict[str, Any], opts: ReportOptions) -> dict[str, Any] | None:
    if not opts.on(section_of(table["kind"])):
        return None
    cols = []
    for c in table["columns"]:
        g = c.get("group")
        if table["kind"] in {"descriptives", "frequencies"} and opts.descriptive_stats is not None and g \
                and g not in opts.descriptive_stats and g not in INFERENTIAL_KEYS:
            continue
        if g in INFERENTIAL_KEYS and not opts.inferential.get(g, True):
            continue
        if g == "effect" and not opts.on("effect_sizes"):
            continue
        if g == "assumptions" and not opts.on("assumptions"):
            continue
        cols.append(c)
    # Drop columns that are empty in every row.
    cols = [c for c in cols if any(r.get(c["key"]) not in (None, "") for r in table["rows"]) or c["fmt"] == "text"]
    if len([c for c in cols if c["fmt"] != "text"]) == 0 and table["kind"] not in {"frequencies"}:
        if not any(c["fmt"] == "text" for c in cols[1:]):
            return None
    return {**table, "columns": cols}


def fmt_value(v: Any, fmt: str, opts: ReportOptions) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "" if fmt != "p" else "—"
    d = opts.decimals
    if fmt == "text":
        return str(v)
    if fmt == "int":
        return f"{int(v):,}"
    if fmt == "p":
        return fmt_p(float(v), opts.style, with_symbol=False)
    if fmt == "pct":
        return f"{float(v):.1f}"
    if fmt == "r":
        return fmt_r(float(v), d, opts.style)
    if fmt == "stat":
        return f"{float(v):,.{d}f}"
    if isinstance(v, (int, float)):
        return f"{float(v):,.{d}f}"
    return str(v)


def chosen_charts(result: dict[str, Any], run_id: int, opts: ReportOptions) -> list[dict[str, Any]]:
    if not opts.on("charts"):
        return []
    charts = result.get("charts") or []
    if opts.charts is None or str(run_id) not in opts.charts:
        return charts if opts.charts is None else []
    wanted = set(opts.charts[str(run_id)])
    return [c for c in charts if c["id"] in wanted]


def interpretation_text(result: dict[str, Any], run_id: int, opts: ReportOptions, edited: str | None) -> str:
    if str(run_id) in opts.interpretations and opts.interpretations[str(run_id)].strip():
        return opts.interpretations[str(run_id)].strip()
    if edited:
        return edited
    i = result.get("interpretation") or {}
    if opts.interpretation_style == "plain":
        return i.get("plain", "")
    if opts.interpretation_style == "both":
        return "\n\n".join(t for t in (i.get("plain"), i.get("technical")) if t)
    return i.get("technical") or i.get("plain", "")
