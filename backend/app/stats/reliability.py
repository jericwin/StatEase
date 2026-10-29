"""Internal consistency (Cronbach's alpha) with item analysis."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..errors import AnalysisError
from . import codegen
from .base import SCALE_LEVELS, AnalysisSpec, Context, Option, Result, Role, assigned, col, listwise, register


def cronbach(items: np.ndarray) -> float:
    k = items.shape[1]
    item_var = items.var(axis=0, ddof=1).sum()
    total_var = items.sum(axis=1).var(ddof=1)
    return float(k / (k - 1) * (1 - item_var / total_var)) if total_var > 0 else math.nan


def alpha_ci(alpha: float, n: int, k: int, level: float) -> tuple[float, float]:
    """Feldt (1965) F-based confidence interval, as in pingouin.cronbach_alpha."""
    df1, df2 = n - 1, (n - 1) * (k - 1)
    lo = 1 - (1 - alpha) * stats.f.isf((1 - level) / 2, df1, df2)
    hi = 1 - (1 - alpha) * stats.f.isf(1 - (1 - level) / 2, df1, df2)
    return lo, hi


def _label(a: float) -> str:
    return ("excellent" if a >= 0.9 else "good" if a >= 0.8 else "acceptable" if a >= 0.7 else
            "questionable" if a >= 0.6 else "poor" if a >= 0.5 else "unacceptable")


def run_reliability(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(REL, config, ctx)
    o = {**REL.defaults(), **(config.get("options") or {})}
    items = assigned(config, "items")
    reverse = [r for r in (o.get("reverse") or []) if r in items]
    df = listwise(ctx.frame(items), items, res)
    X = pd.DataFrame({c: ctx.numeric(df, c) for c in items})
    n, k = X.shape
    if n < 3:
        raise AnalysisError("At least three complete responses are needed.")
    const = [ctx.label(c) for c in items if X[c].std() == 0]
    if const:
        raise AnalysisError(f"Item(s) with no variation cannot be included: {', '.join(const)}.")
    for c in reverse:
        lo, hi = (float(o["scale_min"]), float(o["scale_max"])) if o.get("scale_min") is not None and \
            o.get("scale_max") is not None else (X[c].min(), X[c].max())
        X[c] = lo + hi - X[c]
    if reverse:
        res.notes.append("Reverse-scored items: " + ", ".join(ctx.label(c) for c in reverse)
                         + " (score = min + max − value).")
    res.n = n
    arr = X.to_numpy(float)
    a = cronbach(arr)
    corr = np.corrcoef(arr, rowvar=False)
    mean_r = float(corr[np.triu_indices(k, 1)].mean())
    std_alpha = k * mean_r / (1 + (k - 1) * mean_r)
    level = float(o["ci_level"])
    lo, hi = alpha_ci(a, n, k, level)
    total = arr.sum(axis=1)
    res.table("main", "main", "Scale Reliability",
              [col("alpha", "Cronbach's α", "num", "statistic"), col("ci_lower", f"{level:.0%} CI lower", "num", "ci"),
               col("ci_upper", f"{level:.0%} CI upper", "num", "ci"), col("std_alpha", "Standardised α", "num"),
               col("mean_r", "Mean inter-item r", "num"), col("k", "Items", "int"), col("n", "N", "int", "n"),
               col("mean", "Scale mean", "num", "mean"), col("sd", "Scale SD", "num", "sd")],
              [{"alpha": a, "ci_lower": lo, "ci_upper": hi, "std_alpha": std_alpha, "mean_r": mean_r, "k": k, "n": n,
                "mean": total.mean(), "sd": total.std(ddof=1)}],
              ["Items included: " + ", ".join(ctx.label(c) for c in items) + ".",
               "CI: Feldt's F-based interval. Scale statistics refer to the sum score."])
    rows = []
    for i, c in enumerate(items):
        rest = np.delete(arr, i, axis=1)
        citc = float(np.corrcoef(arr[:, i], rest.sum(axis=1))[0, 1])
        rows.append({"item": ctx.label(c) + (" (R)" if c in reverse else ""), "mean": arr[:, i].mean(),
                     "sd": arr[:, i].std(ddof=1), "citc": citc,
                     "alpha_if_deleted": cronbach(rest) if k > 2 else None})
    res.table("items", "descriptives", "Item Statistics",
              [col("item", "Item", "text"), col("mean", "Mean", "num", "mean"), col("sd", "SD", "num", "sd"),
               col("citc", "Corrected item–total r", "num"), col("alpha_if_deleted", "α if item deleted", "num")], rows,
              ["Corrected item–total r correlates each item with the sum of the other items."])
    res.table("corr", "assumptions", "Inter-Item Correlations",
              [col("item", "", "text")] + [col(f"i{j}", ctx.label(c), "r") for j, c in enumerate(items)],
              [{"item": ctx.label(c), **{f"i{j}": corr[i, j] for j in range(k)}} for i, c in enumerate(items)])
    weak = [r["item"] for r in rows if r["citc"] < 0.3]
    neg = [r["item"] for r in rows if r["citc"] < 0]
    if neg:
        res.warn("Negative item–total correlation for: " + ", ".join(neg) + ". These items may need reverse scoring.")
    if weak:
        res.assumption("Item discrimination", "warning",
                       "Items with corrected item–total r below .30: " + ", ".join(weak) + ".")
    better = [r for r in rows if r["alpha_if_deleted"] is not None and r["alpha_if_deleted"] > a + 0.01]
    res.assumption("Interpretation limits", "info", "A high α does not show that the items measure a single construct "
                   "(unidimensionality) or that the scale is valid; α also rises with the number of items.")
    if k == 2:
        res.notes.append("With only two items, α equals the Spearman–Brown corrected correlation; interpret with care.")
    res.chart("heatmap", "heatmap", "Inter-item correlations", {"labels": [ctx.label(c) for c in items],
                                                                "matrix": corr.tolist()}, "", "",
              "Correlations between pairs of items.")
    res.summary = {"statistic": a, "effect": a, "effect_name": "α", "significant": None}
    res.interpretation = {
        "plain": (f"The {k} items have {_label(a)} internal consistency (Cronbach's α = {a:.2f}). "
                  + (f"Removing {better[0]['item']} would raise α to {better[0]['alpha_if_deleted']:.2f}. "
                     if better else "")
                  + "This shows how consistently the items are answered, not whether they measure what they intend to."),
        "technical": (f"Cronbach's α = {a:.3f}, {level:.0%} CI [{lo:.3f}, {hi:.3f}], standardised α = {std_alpha:.3f}, "
                      f"mean inter-item r = {mean_r:.3f}, k = {k}, n = {n}."),
    }
    return res


def code_rel(config, v):
    items = assigned(config, "items")
    return (codegen.prelude(v, items, ["import pingouin as pg"]) + codegen.numeric_ordinal_note(v, items)
            + f"print(pg.cronbach_alpha(df[{items!r}]))\n")


REL = register(AnalysisSpec(
    id="reliability", name="Reliability Analysis (Cronbach's α)", plain_name="Check if questionnaire items are consistent",
    category="reliability",
    description="Measures how consistently a set of items that form one scale are answered.",
    when_to_use="Three or more items intended to measure the same construct (e.g. SQ1–SQ5).",
    roles=[Role("items", "Scale items", "Items that form one scale.", SCALE_LEVELS, 2, 100, plain="Which items?")],
    options=[Option("reverse", "Reverse-scored items", "multiselect", [], depends_on="items",
                    help="Items worded in the opposite direction."),
             Option("scale_min", "Scale minimum (for reverse scoring)", "number", None, advanced=True),
             Option("scale_max", "Scale maximum (for reverse scoring)", "number", None, advanced=True),
             Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)],
    run=run_reliability, code=code_rel,
    assumptions=["Items measure the same construct (unidimensionality).", "Items are scored in the same direction.",
                 "Tau-equivalence for α to equal reliability."],
    method="Cronbach's α = k/(k−1)·(1 − Σσ²ᵢ/σ²ₜ); Feldt CI; corrected item–total correlations; α if item deleted.",
    references=["Cronbach, L. J. (1951). Psychometrika, 16, 297–334.", "Feldt, L. S. (1965). Psychometrika, 30, 357–370."],
    limitations=["α is not evidence of validity or unidimensionality."],
))
