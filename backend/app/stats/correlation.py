"""Pearson, Spearman and Kendall correlations, and partial correlation."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
from scipy import stats

from ..errors import AnalysisError
from . import codegen
from .base import (
    SCALE_LEVELS,
    AnalysisSpec,
    Context,
    Option,
    Result,
    Role,
    assigned,
    col,
    fmt_p,
    fmt_r,
    listwise,
    register,
    require_n,
)
from .common import normality_assessment, p_adjust, r_label, scatter_data

METHOD_NAMES = {"pearson": "Pearson's r", "spearman": "Spearman's ρ", "kendall": "Kendall's τ-b"}
SYMBOL = {"pearson": "r", "spearman": "ρ", "kendall": "τ"}


def _opts(config):
    return {**CORR.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def correlate(x: np.ndarray, y: np.ndarray, method: str, level: float, alternative: str = "two-sided") -> dict:
    n = len(x)
    out: dict[str, Any] = {"n": n}
    if n < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        out["error"] = "constant" if n >= 3 else "too few"
        return out
    if method == "pearson":
        r = stats.pearsonr(x, y, alternative=alternative)
        est, p = float(r.statistic), float(r.pvalue)
        if n > 3 and abs(est) < 1 - 1e-12:
            ci = r.confidence_interval(confidence_level=level)
            out["ci_lower"], out["ci_upper"] = float(ci.low), float(ci.high)
    elif method == "spearman":
        r = stats.spearmanr(x, y, alternative=alternative)
        est, p = float(r.statistic), float(r.pvalue)
        if n > 3 and abs(est) < 1 - 1e-12:
            # Fisher z with Bonett & Wright (2000) variance 1.06/(n−3); approximate.
            z, se = math.atanh(est), math.sqrt(1.06 / (n - 3))
            q = stats.norm.ppf(0.5 + level / 2)
            out["ci_lower"], out["ci_upper"] = math.tanh(z - q * se), math.tanh(z + q * se)
    else:
        r = stats.kendalltau(x, y, alternative=alternative)
        est, p = float(r.statistic), float(r.pvalue)
    out.update(r=est, p=p, df=n - 2)
    return out


def run_correlation(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(CORR, config, ctx)
    o = _opts(config)
    names = assigned(config, "variables")
    methods = [m for m in (o["methods"] or ["pearson"]) if m in METHOD_NAMES] or ["pearson"]
    level = float(o["ci_level"])
    df = ctx.frame(names)
    if o["missing"] == "listwise":
        df = listwise(df, names, res)
    else:
        res.missing = {"total_rows": len(df), "method": "pairwise"}
        res.notes.append("Missing values were handled pairwise: each correlation uses all cases with values on "
                         "both variables, so N can differ between pairs.")
    data = {n: ctx.numeric(df, n) for n in names}
    for n, s in data.items():
        if s.dropna().nunique() <= 1:
            raise AnalysisError(f"'{ctx.label(n)}' is constant, so its correlations are undefined.")
    pairs = list(combinations(names, 2))
    if len(pairs) > 300:
        raise AnalysisError("Too many variables for a pairwise table (limit 25).")
    rows = []
    for m in methods:
        raw = []
        for a, b in pairs:
            mask = data[a].notna() & data[b].notna()
            c = correlate(data[a][mask].to_numpy(float), data[b][mask].to_numpy(float), m, level, o["alternative"])
            raw.append({"method": METHOD_NAMES[m], "_m": m, "var1": ctx.label(a), "var2": ctx.label(b), "_a": a,
                        "_b": b, **c})
        adj = p_adjust([r.get("p", math.nan) for r in raw], o["p_adjust"])
        for r, pa in zip(raw, adj, strict=True):
            if o["p_adjust"] != "none":
                r["p_unadjusted"], r["p"] = r.get("p"), pa
            r["strength"] = r_label(r["r"]) if r.get("r") is not None else None
        rows += raw
    if any(r.get("error") for r in rows):
        res.warn("Some pairs had too few observations or no variation; their coefficients are blank.")
    columns = [col("var1", "Variable 1", "text"), col("var2", "Variable 2", "text")]
    if len(methods) > 1:
        columns.insert(0, col("method", "Method", "text"))
    columns += [col("n", "N", "int", "n"), col("r", "Coefficient", "r", "statistic"), col("df", "df", "int", "df"),
                col("p", "p", "p", "p")]
    if o["p_adjust"] != "none":
        columns.insert(-1, col("p_unadjusted", "p (unadjusted)", "p", "p"))
    columns += [col("ci_lower", f"{level:.0%} CI lower", "r", "ci"), col("ci_upper", f"{level:.0%} CI upper", "r", "ci"),
                col("strength", "Strength", "text", "effect")]
    notes = [f"{', '.join(METHOD_NAMES[m] for m in methods)}; alternative: {o['alternative']}."]
    if "spearman" in methods:
        notes.append("Spearman CIs use Fisher's z with the Bonett–Wright variance (approximate).")
    if "kendall" in methods:
        notes.append("No confidence interval is reported for Kendall's τ.")
    if o["p_adjust"] != "none":
        notes.append(f"p-values adjusted for {len(pairs)} comparisons ({o['p_adjust'].title()}).")
    notes.append("Strength labels (Cohen, 1988): < .10 negligible, .10 weak, .30 moderate, .50 strong.")
    res.table("main", "main", "Correlations", columns, rows, notes)

    # Matrix for the first method
    m0 = methods[0]
    lookup = {(r["_a"], r["_b"]): r for r in rows if r["_m"] == m0}
    matrix, mrows = [], []
    for a in names:
        line, row = [], {"variable": ctx.label(a)}
        for b in names:
            if a == b:
                v, p = 1.0, None
            else:
                r = lookup.get((a, b)) or lookup.get((b, a)) or {}
                v, p = r.get("r"), r.get("p")
            line.append(v)
            row[f"c_{b}"] = v
            if p is not None and p < ctx.alpha and a != b:
                row[f"c_{b}_sig"] = "*" if p >= 0.01 else "**" if p >= 0.001 else "***"
        matrix.append(line)
        mrows.append(row)
    if len(names) > 2:
        res.table("matrix", "main", f"Correlation Matrix ({METHOD_NAMES[m0]})",
                  [col("variable", "", "text")] + [col(f"c_{b}", ctx.label(b), "r") for b in names], mrows,
                  [f"* p < {ctx.alpha:g}, ** p < .01, *** p < .001 (two-sided unless stated)."])
        res.chart("heatmap", "heatmap", f"Correlation heatmap ({METHOD_NAMES[m0]})",
                  {"labels": [ctx.label(n) for n in names], "matrix": matrix}, "", "",
                  "Colour shows direction and strength; values are printed in each cell.")
    for a, b in pairs[:6]:
        mask = data[a].notna() & data[b].notna()
        sd, note = scatter_data(data[a][mask].to_numpy(float), data[b][mask].to_numpy(float), fit=m0 == "pearson")
        res.chart(f"scatter_{a}_{b}", "scatter", f"{ctx.label(b)} vs {ctx.label(a)}", sd, ctx.label(a), ctx.label(b),
                  "Each point is one case" + ("; the line is the least-squares fit." if m0 == "pearson" else "."), note)
    if "pearson" in methods:
        for n in names[:10]:
            normality_assessment(res, data[n].dropna().to_numpy(float), ctx.label(n))
        res.assumption("Linearity", "info", "Pearson's r measures linear association. Inspect the scatter plots; "
                       "curved patterns are better described with Spearman's ρ or a different model.")
        res.assumption("Outliers", "info", "A few extreme points can strongly change Pearson's r; check the scatter "
                       "plots.")
    res.n = int(len(df))
    main = [r for r in rows if r["_m"] == m0 and r.get("r") is not None]
    sig = [r for r in main if r["p"] < ctx.alpha]
    sym = SYMBOL[m0]

    def sentence(r):
        dirn = "positive" if r["r"] > 0 else "negative"
        return (f"{r['var1']} and {r['var2']} showed a {r['strength']} {dirn} association "
                f"({sym} = {fmt_r(r['r'], ctx.decimals, ctx.p_style)}, {fmt_p(r['p'], ctx.p_style)})")

    if len(main) == 1:
        r = main[0]
        plain = (f"{r['var1']} and {r['var2']} are {'' if r['p'] < ctx.alpha else 'not '}significantly related"
                 + (f": when one is higher, the other tends to be {'higher' if r['r'] > 0 else 'lower'} "
                    f"({r['strength']} relationship)." if r["p"] < ctx.alpha else "."))
        tech = sentence(r) + f", n = {r['n']}."
    else:
        plain = (f"{len(sig)} of {len(main)} pairs of variables are significantly related." if main else "")
        tech = ("; ".join(sentence(r) for r in sig[:10]) + ".") if sig else "No pair was significantly correlated."
    plain += " Correlation shows association only; it does not show that one variable causes the other."
    res.summary = {"pairs": len(main), "significant_pairs": len(sig), "significant": bool(sig)}
    if len(main) == 1:
        res.summary.update(statistic=main[0]["r"], p=main[0]["p"], effect=main[0]["r"], effect_name=sym)
    for r in rows:
        for k in ("_a", "_b", "_m"):
            r.pop(k, None)
    res.tables[0]["rows"] = rows
    res.interpretation = {"plain": plain, "technical": tech}
    return res


def code_correlation(config, v):
    o = _opts(config)
    names = assigned(config, "variables")
    lines = codegen.prelude(v, names, ["from scipy import stats", "from itertools import combinations"],
                            listwise=o["missing"] == "listwise") + codegen.numeric_ordinal_note(v, names)
    fn = {"pearson": "pearsonr", "spearman": "spearmanr", "kendall": "kendalltau"}
    for m in o["methods"] or ["pearson"]:
        lines += (f"for a, b in combinations({names!r}, 2):\n"
                  "    d = df[[a, b]].dropna()\n"
                  f"    print(a, b, stats.{fn[m]}(d[a], d[b], alternative={o['alternative']!r}))\n")
    return lines


def run_partial(ctx: Context, config: dict[str, Any]) -> Result:
    import pingouin as pg

    res = Result(PARTIAL, config, ctx)
    x, y = assigned(config, "x")[0], assigned(config, "y")[0]
    covs = assigned(config, "covariates")
    method = (config.get("options") or {}).get("method", "pearson")
    df = listwise(ctx.frame([x, y, *covs]), [x, y, *covs], res)
    data = df.copy()
    for c in [x, y, *covs]:
        data[c] = ctx.numeric(df, c)
    require_n(len(data), len(covs) + 4, "The data")
    r = pg.partial_corr(data, x=x, y=y, covar=covs, method=method).iloc[0]
    zero = correlate(data[x].to_numpy(float), data[y].to_numpy(float), method, 0.95)
    ci = r.get("CI95") if "CI95" in r else r.get("CI95%")
    res.n = int(r["n"])
    res.table("main", "main", "Partial Correlation",
              [col("pair", "Pair", "text"), col("control", "Controlling for", "text"), col("n", "N", "int", "n"),
               col("r", "Partial r", "r", "statistic"), col("p", "p", "p", "p"), col("ci_lower", "95% CI lower", "r", "ci"),
               col("ci_upper", "95% CI upper", "r", "ci"), col("zero_order", "Zero-order r", "r")],
              [{"pair": f"{ctx.label(x)} – {ctx.label(y)}", "control": ", ".join(ctx.label(c) for c in covs),
                "n": int(r["n"]), "r": float(r["r"]), "p": float(r["p_val"]),
                "ci_lower": float(ci[0]) if ci is not None else None, "ci_upper": float(ci[1]) if ci is not None else None,
                "zero_order": zero.get("r")}],
              [f"Method: {method}. Computed with pingouin.partial_corr."])
    sig = float(r["p_val"]) < ctx.alpha
    ctl = ", ".join(ctx.label(c) for c in covs)
    res.summary = {"statistic": float(r["r"]), "p": float(r["p_val"]), "effect": float(r["r"]), "effect_name": "r",
                   "significant": sig}
    res.interpretation = {
        "plain": f"After accounting for {ctl}, {ctx.label(x)} and {ctx.label(y)} are "
                 + ("still significantly related." if sig else "not significantly related.")
                 + " This is an association, not evidence of cause and effect.",
        "technical": f"Partial correlation between {ctx.label(x)} and {ctx.label(y)} controlling for {ctl}: "
                     f"r = {fmt_r(float(r['r']), 2, ctx.p_style)}, {fmt_p(float(r['p_val']), ctx.p_style)}, n = {int(r['n'])} "
                     f"(zero-order r = {fmt_r(zero.get('r'), 2, ctx.p_style)}).",
    }
    return res


def code_partial(config, v):
    x, y, covs = assigned(config, "x")[0], assigned(config, "y")[0], assigned(config, "covariates")
    method = (config.get("options") or {}).get("method", "pearson")
    return (codegen.prelude(v, [x, y, *covs], ["import pingouin as pg"])
            + f"print(pg.partial_corr(df, x={x!r}, y={y!r}, covar={covs!r}, method={method!r}))\n")


CORR = register(AnalysisSpec(
    id="correlation", name="Correlation", plain_name="Check whether numeric variables are related",
    category="correlation",
    description="Measures the strength and direction of association between pairs of variables.",
    when_to_use="Two or more numeric or rating variables. Pearson for linear relationships between roughly normal "
                "variables; Spearman or Kendall for ranks, ordinal ratings, skewed data or outliers.",
    roles=[Role("variables", "Variables", "Two or more numeric or ordinal variables.", SCALE_LEVELS, 2, 25,
                plain="Which variables?")],
    options=[Option("methods", "Coefficients", "multiselect", ["pearson"],
                    [{"value": k, "label": v} for k, v in METHOD_NAMES.items()]),
             Option("missing", "Missing values", "select", "pairwise",
                    [{"value": "pairwise", "label": "Exclude pairwise"}, {"value": "listwise", "label": "Exclude listwise"}],
                    advanced=True),
             Option("p_adjust", "Multiple-comparison correction", "select", "none",
                    [{"value": "none", "label": "None"}, {"value": "holm", "label": "Holm"},
                     {"value": "bonferroni", "label": "Bonferroni"}, {"value": "fdr", "label": "False discovery rate (BH)"}],
                    advanced=True),
             Option("alternative", "Alternative hypothesis", "select", "two-sided",
                    [{"value": "two-sided", "label": "Two-sided"}, {"value": "greater", "label": "Positive"},
                     {"value": "less", "label": "Negative"}], advanced=True),
             Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)],
    run=run_correlation, code=code_correlation,
    assumptions=["Pearson: linear relationship, no extreme outliers, approximately normal variables for inference.",
                 "Spearman/Kendall: monotonic relationship."],
    method="scipy.stats pearsonr (exact t-test, Fisher-z CI), spearmanr, kendalltau (τ-b).",
    missing_data="Pairwise deletion by default (each pair uses all complete cases for that pair); listwise optional.",
    limitations=["Correlation does not imply causation.", "Pearson's r captures only linear association."],
    references=["Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.).",
                "Bonett, D. G., & Wright, T. A. (2000). Psychometrika, 65, 23–28."],
))
PARTIAL = register(AnalysisSpec(
    id="partial_correlation", name="Partial Correlation",
    plain_name="Check a relationship while controlling for other variables", category="correlation",
    description="Correlation between two variables after removing the linear influence of control variables.",
    roles=[Role("x", "Variable 1", "", SCALE_LEVELS), Role("y", "Variable 2", "", SCALE_LEVELS),
           Role("covariates", "Control variables", "", SCALE_LEVELS, 1, 10)],
    options=[Option("method", "Method", "select", "pearson",
                    [{"value": "pearson", "label": "Pearson"}, {"value": "spearman", "label": "Spearman"}])],
    run=run_partial, code=code_partial,
    assumptions=["Linear relationships with the control variables."],
    method="pingouin.partial_corr (residual-based partial correlation).",
))
