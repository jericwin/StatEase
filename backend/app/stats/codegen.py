"""Reproducible Python code for each analysis.

The generated script uses the same libraries and the same calls (SciPy, statsmodels, pingouin)
with the same options as the engine, so a user can reproduce every reported number.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from .base import VarMeta

# Row filter of the analysis being generated ({"column", "values"}), set by the engine.
FILTER: ContextVar[dict[str, Any] | None] = ContextVar("FILTER", default=None)


def _lit(v: Any) -> str:
    return repr(v)


def prelude(variables: dict[str, VarMeta], columns: list[str], imports: list[str], listwise: bool = True) -> str:
    flt = FILTER.get()
    read_cols = list(dict.fromkeys([*columns, *([flt["column"]] if flt else [])]))
    lines = ["import numpy as np", "import pandas as pd", *imports, "",
             "# Export the dataset from StatEase (Data > Download as Parquet) and adjust the path.",
             f"df = pd.read_parquet('dataset.parquet', columns={_lit(read_cols)})"]
    for c in read_cols:
        m = variables.get(c)
        if m and m.missing_codes:
            lines.append(f"df[{_lit(c)}] = df[{_lit(c)}].replace({_lit(list(m.missing_codes))}, np.nan)"
                         "  # declared missing-value codes")
        if m and m.category_labels:
            labels = {str(k): v for k, v in m.category_labels.items()}
            lines.append(f"df[{_lit(c)}] = df[{_lit(c)}].map(lambda v: v if pd.isna(v) else "
                         f"{_lit(labels)}.get(str(int(v)) if isinstance(v, float) and v.is_integer() else str(v), v))")
    if flt:
        lines.append(f"df = df[df[{_lit(flt['column'])}].astype(str).isin({_lit([str(v) for v in flt['values']])})]"
                     "  # analysis subset")
    if listwise:
        lines.append(f"df = df.dropna(subset={_lit(list(dict.fromkeys(columns)))})  # listwise deletion")
    return "\n".join(lines) + "\n"


def numeric_ordinal_note(variables: dict[str, VarMeta], columns: list[str]) -> str:
    text_ord = [c for c in columns if variables.get(c) and variables[c].level == "ordinal"
                and variables[c].data_type == "string"]
    if not text_ord:
        return ""
    lines = []
    for c in text_ord:
        order = variables[c].category_order
        lines.append(f"df[{_lit(c)}] = df[{_lit(c)}].map({ {v: i + 1 for i, v in enumerate(order)} !r})"
                     "  # ordered categories scored 1..k")
    return "\n".join(lines) + "\n"
