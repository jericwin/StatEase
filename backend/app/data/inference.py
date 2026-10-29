"""Measurement-level inference.

Numbers are not assumed to be continuous measurements: a column holding 1, 2 and 3 may be
category codes, and a 1-5 response is usually an ordinal rating. Every inferred level comes
with a note explaining why, and the user can override it.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl

LEVELS = ["numeric", "ordinal", "nominal", "binary", "date", "datetime", "text", "identifier"]
CATEGORICAL = {"ordinal", "nominal", "binary"}

_ID_NAME = re.compile(r"(^|[\s_.-])(id|uid|uuid|key|code|no|number|num|nr)$|^(id|respondent|record|case|row|serial|"
                      r"participant|subject|student[\s_]?(no|number|id))", re.I)
_NOMINAL_NAME = re.compile(r"gender|sex|group|region|province|city|country|department|dept|status|type|category|"
                           r"civil|marital|religion|course|program|programme|section|strand|track|school|college|"
                           r"ethnic|race|nationality|occupation|industry|sector|branch|treatment|condition|class\b|"
                           r"formulation|formula|product|brand|variant|recipe|batch|sample\b", re.I)
_ITEM_NAME = re.compile(r"^(?P<prefix>.*?[A-Za-z][A-Za-z _.-]*?)[\s_.-]*(?:q|item|i)?[\s_.-]*(?P<num>\d{1,3})$", re.I)

LIKERT_ORDERS: list[list[str]] = [
    ["strongly disagree", "disagree", "somewhat disagree", "neither agree nor disagree", "neutral", "undecided",
     "somewhat agree", "agree", "strongly agree"],
    ["never", "rarely", "seldom", "sometimes", "occasionally", "often", "usually", "frequently", "very often", "always"],
    ["very dissatisfied", "dissatisfied", "somewhat dissatisfied", "neutral", "somewhat satisfied", "satisfied",
     "very satisfied"],
    ["very poor", "poor", "fair", "average", "good", "very good", "excellent"],
    ["very unlikely", "unlikely", "neutral", "likely", "very likely"],
    ["not at all", "slightly", "somewhat", "moderately", "very", "extremely"],
    ["very low", "low", "moderate", "medium", "high", "very high"],
    ["strongly disagree", "disagree", "agree", "strongly agree"],
]
BINARY_TEXT = [{"yes", "no"}, {"true", "false"}, {"y", "n"}, {"male", "female"}, {"m", "f"}, {"pass", "fail"},
               {"present", "absent"}, {"positive", "negative"}]


def _likert_order(values: list[str]) -> list[str] | None:
    lowered = {v.strip().lower(): v for v in values}
    for scale in LIKERT_ORDERS:
        if set(lowered) <= set(scale) and len(lowered) >= 2:
            return [lowered[s] for s in scale if s in lowered]
    return None


def classify(name: str, s: pl.Series) -> dict[str, Any]:
    """Infer storage type and measurement level for one column."""
    dtype = s.dtype
    n = s.len()
    non_null = s.drop_nulls()
    n_missing = n - non_null.len()
    n_unique = non_null.n_unique() if non_null.len() else 0
    info: dict[str, Any] = {"column_name": name, "n_missing": n_missing, "n_unique": n_unique,
                            "examples": [str(v) for v in non_null.unique(maintain_order=True).head(5).to_list()],
                            "category_order": []}

    def done(level: str, data_type: str, note: str) -> dict[str, Any]:
        info.update(measurement_level=level, inferred_level=level, data_type=data_type, inference_note=note)
        if n_unique == 1:
            info["inference_note"] = note + " The column has only one distinct value (constant)."
            info["constant"] = True
        if non_null.len() == 0:
            info["inference_note"] = "All values are missing."
        return info

    if non_null.len() == 0:
        return done("text", "string", "All values are missing.")
    if dtype == pl.Boolean:
        return done("binary", "boolean", "True/false values.")
    if dtype == pl.Date:
        return done("date", "date", "Calendar dates.")
    if dtype.is_temporal():
        return done("datetime", "datetime", "Date and time values.")

    if dtype.is_numeric():
        is_int = dtype.is_integer() or bool((non_null.cast(pl.Float64) % 1 == 0).all())
        data_type = "integer" if is_int else "decimal"
        lo, hi = non_null.min(), non_null.max()
        if is_int and n_unique == non_null.len() and non_null.len() > 20:
            if _ID_NAME.search(name):
                return done("identifier", data_type, "Every value is unique and the name suggests an identifier.")
            diffs = non_null.cast(pl.Int64).diff().drop_nulls()
            if diffs.len() and bool((diffs == 1).all()):
                return done("identifier", data_type, "Values are a consecutive sequence (looks like a row number).")
        if n_unique == 2:
            return done("binary", data_type, f"Only two distinct values ({lo} and {hi}); treated as two categories.")
        if is_int and _NOMINAL_NAME.search(name) and n_unique <= 30:
            return done("nominal", data_type, "Number-coded categories (the name suggests group codes). "
                                              "Add category labels to make results readable.")
        if is_int and n_unique <= 11 and lo is not None and lo >= 0 and hi - lo <= 10:
            info["category_order"] = sorted(non_null.unique().to_list())
            return done("ordinal", data_type,
                        f"Whole numbers from {lo} to {hi} with {n_unique} distinct values, which looks like a rating "
                        "or code. Treated as ordinal. Change to 'numeric' if it is a count or measurement, or "
                        "'nominal' if the numbers are unordered category codes.")
        return done("numeric", data_type, f"{'Whole' if is_int else 'Decimal'} numbers with {n_unique} distinct values.")

    # Text-like columns
    str_vals = non_null.cast(pl.String)
    lowered = {v.strip().lower() for v in str_vals.unique().head(50).to_list()}
    if n_unique == 2 or (n_unique <= 2 and any(lowered <= b for b in BINARY_TEXT)):
        return done("binary", "string", "Two distinct categories.")
    if n_unique <= 12:
        order = _likert_order(str_vals.unique().to_list())
        if order:
            info["category_order"] = order
            return done("ordinal", "string", "Recognised as an ordered response scale; order set automatically.")
    avg_len = float(str_vals.str.len_chars().mean() or 0)
    if n_unique == non_null.len() and non_null.len() > 20 and (avg_len <= 40 or _ID_NAME.search(name)):
        if _ID_NAME.search(name) or avg_len <= 20:
            return done("identifier", "string", "Every value is unique; looks like an identifier or name.")
    if n_unique <= max(20, int(0.05 * non_null.len())) and avg_len <= 60:
        return done("nominal", "string", f"Text with {n_unique} distinct categories.")
    return done("text", "string", "Free text with many distinct values; not used in analyses by default.")


def detect_scale_groups(variables: list[dict[str, Any]]) -> None:
    """Group questionnaire items such as SQ1, SQ2, SQ3 (same prefix, rating-type levels)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in variables:
        if v["measurement_level"] not in {"ordinal", "numeric"}:
            continue
        m = _ITEM_NAME.match(v["column_name"].strip())
        if not m:
            continue
        prefix = m.group("prefix").strip(" _.-")
        if prefix:
            groups.setdefault(prefix.lower(), []).append(v)
    for items in groups.values():
        if len(items) >= 3:
            label = items[0]["column_name"]
            label = _ITEM_NAME.match(label.strip()).group("prefix").strip(" _.-")  # type: ignore[union-attr]
            for v in items:
                v["scale_group"] = label


def infer_variables(df: pl.DataFrame) -> list[dict[str, Any]]:
    variables = [classify(name, df[name]) for name in df.columns]
    detect_scale_groups(variables)
    return variables
