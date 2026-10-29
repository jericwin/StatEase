"""Rank-based tests: Mann–Whitney U, Wilcoxon signed-rank, Kruskal–Wallis (+ Dunn) and Friedman.

These tests compare distributions (stochastic ordering). They test medians only under the extra
assumption that the distributions have the same shape; interpretations are worded accordingly.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
from scipy import stats

from ..errors import AnalysisError
from . import codegen
from .base import (
    CATEGORICAL_LEVELS,
    SCALE_LEVELS,
    AnalysisSpec,
    Context,
    Option,
    Result,
    Role,
    assigned,
    col,
    fmt_num,
    fmt_p,
    listwise,
    register,
    require_n,
    sig_phrase,
)
from .common import box_stats, describe, p_adjust, r_label
from .ttests import two_groups

ALT = Option("alternative", "Alternative hypothesis", "select", "two-sided",
             [{"value": "two-sided", "label": "Two-sided"}, {"value": "greater", "label": "First > second"},
              {"value": "less", "label": "First < second"}], advanced=True)
NOTE = ("Rank-based tests compare whether values in one group tend to be larger than in the other. They compare "
        "medians only if the distributions have the same shape.")


def _opts(spec, config):
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def _median_table(res, label, names, arrays):
    rows = []
    for n, a in zip(names, arrays, strict=True):
        d = describe(a)
        rows.append({"group": n, "n": d["n"], "median": d.get("median"), "q1": d.get("q1"), "q3": d.get("q3"),
                     "mean_rank": None})
    allv = np.concatenate(arrays)
    ranks = stats.rankdata(allv)
    i = 0
    for r, a in zip(rows, arrays, strict=True):
        r["mean_rank"] = float(ranks[i:i + len(a)].mean()) if len(a) else None
        i += len(a)
    res.table("desc", "descriptives", "Group Descriptives",
              [col("group", label, "text"), col("n", "N", "int", "n"), col("median", "Median", "num", "median"),
               col("q1", "Q1", "num", "q1"), col("q3", "Q3", "num", "q3"), col("mean_rank", "Mean rank", "num")], rows)
    return rows


def run_mann_whitney(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(MW, config, ctx)
    o = _opts(MW, config)
    dv, group = assigned(config, "dependent")[0], assigned(config, "group")[0]
    df = listwise(ctx.frame([dv, group]), [dv, group], res)
    g, a, b = two_groups(ctx, df, group, o)
    y = ctx.numeric(df, dv)
    x1, x2 = y[g == a].to_numpy(float), y[g == b].to_numpy(float)
    require_n(len(x1), 1, f"Group '{a}'")
    require_n(len(x2), 1, f"Group '{b}'")
    n1, n2 = len(x1), len(x2)
    res.n = n1 + n2
    method = "auto" if o["method"] == "auto" else o["method"]
    r = stats.mannwhitneyu(x1, x2, alternative=o["alternative"], method=method, use_continuity=True)
    U = float(r.statistic)
    rbc = 2 * U / (n1 * n2) - 1  # rank-biserial correlation (positive: first group tends higher)
    _median_table(res, ctx.label(group), [a, b], [x1, x2])
    res.table("main", "main", "Mann–Whitney U Test",
              [col("U", "U", "stat", "statistic"), col("p", "p", "p", "p"), col("rbc", "Rank-biserial r", "r", "effect"),
               col("n1", f"n ({a})", "int", "n"), col("n2", f"n ({b})", "int", "n")],
              [{"U": U, "p": r.pvalue, "rbc": rbc, "n1": n1, "n2": n2}],
              [f"U is reported for '{a}'. Method: {method} (asymptotic with continuity correction for larger samples "
               "or ties, exact otherwise).", NOTE])
    res.chart("box", "box", f"{ctx.label(dv)} by {ctx.label(group)}", {"groups": [box_stats(a, x1), box_stats(b, x2)]},
              ctx.label(group), ctx.label(dv), "Box plots of each group.")
    sig, phrase = sig_phrase(r.pvalue, ctx.alpha)
    higher = a if rbc > 0 else b
    res.summary = {"statistic": U, "p": r.pvalue, "effect": rbc, "effect_name": "rank-biserial r", "significant": sig}
    res.interpretation = {
        "plain": (f"{ctx.label(dv)} values tended to be higher in {higher}" if sig else
                  f"There is no significant difference in {ctx.label(dv)} between {a} and {b}")
                 + f" ({r_label(rbc)} effect).",
        "technical": (f"A Mann–Whitney U test compared {ctx.label(dv)} between {a} (Mdn = {fmt_num(np.median(x1), 2)}, "
                      f"n = {n1}) and {b} (Mdn = {fmt_num(np.median(x2), 2)}, n = {n2}): U = {U:.1f}, "
                      f"{fmt_p(r.pvalue, ctx.p_style)}, rank-biserial r = {rbc:.2f}; {phrase}."),
    }
    return res


def code_mw(config, v):
    o = _opts(MW, config)
    dv, group = assigned(config, "dependent")[0], assigned(config, "group")[0]
    return (codegen.prelude(v, [dv, group], ["from scipy import stats"])
            + f"a, b = {o.get('group_a') or '<group A>'!r}, {o.get('group_b') or '<group B>'!r}\n"
            f"x1 = df.loc[df[{group!r}].astype(str) == a, {dv!r}]\nx2 = df.loc[df[{group!r}].astype(str) == b, {dv!r}]\n"
            f"r = stats.mannwhitneyu(x1, x2, alternative={o['alternative']!r}, method={o['method']!r})\n"
            "print(r, 'rank-biserial =', 2 * r.statistic / (len(x1) * len(x2)) - 1)\n")


def run_wilcoxon(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(WSR, config, ctx)
    o = _opts(WSR, config)
    v1, v2 = assigned(config, "first")[0], assigned(config, "second")[0]
    df = listwise(ctx.frame([v1, v2]), [v1, v2], res)
    x1, x2 = ctx.numeric(df, v1).to_numpy(float), ctx.numeric(df, v2).to_numpy(float)
    d = x1 - x2
    nz = d[d != 0]
    if len(nz) == 0:
        raise AnalysisError("All paired differences are zero; there is nothing to test.")
    require_n(len(nz), 2, "Non-zero paired differences")
    res.n = len(d)
    r = stats.wilcoxon(x1, x2, zero_method="wilcox", alternative=o["alternative"], method="auto")
    ranks = stats.rankdata(np.abs(nz))
    w_plus, w_minus = float(ranks[nz > 0].sum()), float(ranks[nz < 0].sum())
    rbc = (w_plus - w_minus) / (w_plus + w_minus)  # matched-pairs rank-biserial
    rows = [{"variable": ctx.label(v1), **describe(x1)}, {"variable": ctx.label(v2), **describe(x2)}]
    res.table("desc", "descriptives", "Descriptives",
              [col("variable", "Measurement", "text"), col("n", "N", "int", "n"), col("median", "Median", "num", "median"),
               col("q1", "Q1", "num", "q1"), col("q3", "Q3", "num", "q3")], rows)
    res.table("main", "main", "Wilcoxon Signed-Rank Test",
              [col("pair", "Pair", "text"), col("W", "W", "stat", "statistic"), col("p", "p", "p", "p"),
               col("rbc", "Rank-biserial r", "r", "effect"), col("n", "Non-zero pairs", "int", "n"),
               col("zeros", "Zero differences", "int")],
              [{"pair": f"{ctx.label(v1)} − {ctx.label(v2)}", "W": r.statistic, "p": r.pvalue, "rbc": rbc,
                "n": len(nz), "zeros": int(len(d) - len(nz))}],
              ["Zero differences are dropped (Wilcoxon method). W is the smaller of the positive and negative rank sums "
               "for two-sided tests.", NOTE])
    sig, phrase = sig_phrase(r.pvalue, ctx.alpha)
    res.summary = {"statistic": float(r.statistic), "p": float(r.pvalue), "effect": rbc,
                   "effect_name": "rank-biserial r", "significant": sig}
    res.interpretation = {
        "plain": (f"{ctx.label(v1)} tended to be {'higher' if rbc > 0 else 'lower'} than {ctx.label(v2)}"
                  if sig else f"There is no significant difference between {ctx.label(v1)} and {ctx.label(v2)}") + ".",
        "technical": (f"A Wilcoxon signed-rank test: W = {float(r.statistic):.1f}, {fmt_p(r.pvalue, ctx.p_style)}, "
                      f"rank-biserial r = {rbc:.2f}, n = {len(nz)} non-zero pairs; {phrase}."),
    }
    return res


def code_wsr(config, v):
    o = _opts(WSR, config)
    v1, v2 = assigned(config, "first")[0], assigned(config, "second")[0]
    return (codegen.prelude(v, [v1, v2], ["from scipy import stats"])
            + f"print(stats.wilcoxon(df[{v1!r}], df[{v2!r}], zero_method='wilcox', alternative={o['alternative']!r}))\n")


def dunn(arrays: list[np.ndarray], names: list[str], method: str) -> list[dict[str, Any]]:
    """Dunn (1964) test with tie correction."""
    allv = np.concatenate(arrays)
    N = len(allv)
    ranks = stats.rankdata(allv)
    _, counts = np.unique(allv, return_counts=True)
    tie = (counts**3 - counts).sum() / (12 * (N - 1))
    means, idx = [], 0
    for a in arrays:
        means.append(ranks[idx:idx + len(a)].mean())
        idx += len(a)
    raw = []
    for i, j in combinations(range(len(arrays)), 2):
        se = math.sqrt((N * (N + 1) / 12 - tie) * (1 / len(arrays[i]) + 1 / len(arrays[j])))
        z = (means[i] - means[j]) / se
        raw.append({"a": names[i], "b": names[j], "z": z, "p_unadjusted": 2 * stats.norm.sf(abs(z))})
    adj = p_adjust([r["p_unadjusted"] for r in raw], method)
    for r, p in zip(raw, adj, strict=True):
        r["p"] = p
    return raw


def run_kruskal(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(KW, config, ctx)
    o = _opts(KW, config)
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    df = listwise(ctx.frame([dv, factor]), [dv, factor], res)
    g = ctx.categorical(df, factor)
    y = ctx.numeric(df, dv)
    names, arrays = [], []
    for c in g.cat.categories:
        a = y[g == c].to_numpy(float)
        if len(a):
            names.append(str(c))
            arrays.append(a)
    if len(arrays) < 2:
        raise AnalysisError(f"'{ctx.label(factor)}' needs at least two groups with data.")
    if np.ptp(np.concatenate(arrays)) == 0:
        raise AnalysisError(f"'{ctx.label(dv)}' is constant.")
    H, p = stats.kruskal(*arrays)
    n, k = sum(len(a) for a in arrays), len(arrays)
    res.n = n
    eps2 = H / ((n**2 - 1) / (n + 1))
    _median_table(res, ctx.label(factor), names, arrays)
    res.table("main", "main", "Kruskal–Wallis Test",
              [col("H", "H", "stat", "statistic"), col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("eps2", "ε² (rank)", "num", "effect"), col("n", "N", "int", "n")],
              [{"H": H, "df": k - 1, "p": p, "eps2": eps2, "n": n}], ["H is corrected for ties.", NOTE])
    ph = []
    if (p < ctx.alpha or o["posthoc_always"]) and k > 2 and o["posthoc"] != "none":
        ph = dunn(arrays, names, o["posthoc"])
        res.table("posthoc", "posthoc", f"Dunn's Post Hoc Test ({o['posthoc'].title()})",
                  [col("a", "Group A", "text"), col("b", "Group B", "text"), col("z", "z", "stat", "statistic"),
                   col("p_unadjusted", "p (unadjusted)", "p", "p"), col("p", "p (adjusted)", "p", "p")], ph)
    res.chart("box", "box", f"{ctx.label(dv)} by {ctx.label(factor)}",
              {"groups": [box_stats(nm, a) for nm, a in zip(names, arrays, strict=True)]}, ctx.label(factor),
              ctx.label(dv), "Box plots of each group.")
    sig, phrase = sig_phrase(p, ctx.alpha)
    sig_pairs = [f"{r['a']} vs {r['b']}" for r in ph if r["p"] < ctx.alpha]
    res.summary = {"statistic": H, "df": k - 1, "p": p, "effect": eps2, "effect_name": "ε²", "significant": sig}
    res.interpretation = {
        "plain": (f"{ctx.label(dv)} differs significantly across {ctx.label(factor)} groups."
                  if sig else f"{ctx.label(dv)} does not differ significantly across {ctx.label(factor)} groups.")
                 + (f" Pairs that differ: {', '.join(sig_pairs)}." if sig_pairs else ""),
        "technical": (f"Kruskal–Wallis test: H({k - 1}) = {H:.2f}, {fmt_p(p, ctx.p_style)}, ε² = {eps2:.3f}, n = {n}; "
                      f"{phrase}."),
    }
    return res


def code_kw(config, v):
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    return (codegen.prelude(v, [dv, factor], ["from scipy import stats"])
            + f"groups = [g[{dv!r}].to_numpy(float) for _, g in df.groupby({factor!r}, observed=True)]\n"
            "print(stats.kruskal(*groups))\n")


def run_friedman(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(FRIED, config, ctx)
    o = _opts(FRIED, config)
    within = assigned(config, "within")
    df = listwise(ctx.frame(within), within, res)
    arrays = [ctx.numeric(df, c).to_numpy(float) for c in within]
    n, k = len(df), len(within)
    require_n(n, 2, "The repeated-measures data")
    res.n = n
    chi, p = stats.friedmanchisquare(*arrays)
    W = chi / (n * (k - 1))
    names = [ctx.label(c) for c in within]
    res.table("desc", "descriptives", "Descriptives",
              [col("group", "Condition", "text"), col("n", "N", "int", "n"), col("median", "Median", "num", "median"),
               col("q1", "Q1", "num", "q1"), col("q3", "Q3", "num", "q3")],
              [{"group": nm, **describe(a)} for nm, a in zip(names, arrays, strict=True)])
    res.table("main", "main", "Friedman Test",
              [col("chi2", "χ²", "stat", "statistic"), col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("W", "Kendall's W", "num", "effect"), col("n", "N", "int", "n")],
              [{"chi2": chi, "df": k - 1, "p": p, "W": W, "n": n}])
    ph = []
    if (p < ctx.alpha or o["posthoc_always"]) and k > 2 and o["posthoc"] != "none":
        raw = []
        for i, j in combinations(range(k), 2):
            try:
                r = stats.wilcoxon(arrays[i], arrays[j], zero_method="wilcox")
                raw.append({"a": names[i], "b": names[j], "W": float(r.statistic), "p_unadjusted": float(r.pvalue)})
            except ValueError:
                raw.append({"a": names[i], "b": names[j], "W": None, "p_unadjusted": None})
        adj = p_adjust([r["p_unadjusted"] if r["p_unadjusted"] is not None else math.nan for r in raw], o["posthoc"])
        for r, pa in zip(raw, adj, strict=True):
            r["p"] = pa
        ph = raw
        res.table("posthoc", "posthoc", f"Pairwise Wilcoxon Tests ({o['posthoc'].title()})",
                  [col("a", "Condition A", "text"), col("b", "Condition B", "text"), col("W", "W", "stat", "statistic"),
                   col("p_unadjusted", "p (unadjusted)", "p", "p"), col("p", "p (adjusted)", "p", "p")], ph)
    res.chart("box", "box", "Distributions by condition",
              {"groups": [box_stats(nm, a) for nm, a in zip(names, arrays, strict=True)]}, "Condition", "Value",
              "Box plots of each repeated measurement.")
    sig, phrase = sig_phrase(p, ctx.alpha)
    res.summary = {"statistic": chi, "df": k - 1, "p": p, "effect": W, "effect_name": "Kendall's W", "significant": sig}
    res.interpretation = {
        "plain": ("Scores differed significantly across the repeated measurements." if sig else
                  "Scores did not differ significantly across the repeated measurements."),
        "technical": f"Friedman test: χ²({k - 1}) = {chi:.2f}, {fmt_p(p, ctx.p_style)}, Kendall's W = {W:.3f}, n = {n}; {phrase}.",
    }
    return res


def code_friedman(config, v):
    within = assigned(config, "within")
    return (codegen.prelude(v, within, ["from scipy import stats"])
            + f"print(stats.friedmanchisquare(*[df[c] for c in {within!r}]))\n")


PH = [{"value": "holm", "label": "Holm"}, {"value": "bonferroni", "label": "Bonferroni"}, {"value": "none", "label": "None"}]
ALWAYS = Option("posthoc_always", "Run post hoc tests even if the overall test is not significant", "bool", False,
                advanced=True)

MW = register(AnalysisSpec(
    id="mann_whitney", name="Mann–Whitney U Test", plain_name="Compare two groups using ranks",
    category="nonparametric",
    description="Rank-based alternative to the independent-samples t-test.",
    when_to_use="Two independent groups with ordinal ratings, skewed data or outliers.",
    roles=[Role("dependent", "Test variable", "", SCALE_LEVELS), Role("group", "Grouping variable", "", CATEGORICAL_LEVELS)],
    options=[Option("method", "p-value method", "select", "auto",
                    [{"value": "auto", "label": "Automatic"}, {"value": "asymptotic", "label": "Asymptotic"},
                     {"value": "exact", "label": "Exact"}], advanced=True),
             Option("group_a", "First group", "level", None, depends_on="group", advanced=True),
             Option("group_b", "Second group", "level", None, depends_on="group", advanced=True), ALT],
    run=run_mann_whitney, code=code_mw,
    assumptions=["Independent observations.", "An ordinal or continuous outcome."],
    method="scipy.stats.mannwhitneyu; effect size: rank-biserial correlation.",
))
WSR = register(AnalysisSpec(
    id="wilcoxon", name="Wilcoxon Signed-Rank Test", plain_name="Compare two related measurements using ranks",
    category="nonparametric",
    description="Rank-based alternative to the paired-samples t-test.",
    roles=[Role("first", "Measurement 1", "", SCALE_LEVELS), Role("second", "Measurement 2", "", SCALE_LEVELS)],
    options=[ALT],
    run=run_wilcoxon, code=code_wsr,
    assumptions=["Paired observations.", "Differences roughly symmetric around their median."],
    method="scipy.stats.wilcoxon (zero differences dropped); matched-pairs rank-biserial correlation.",
))
KW = register(AnalysisSpec(
    id="kruskal_wallis", name="Kruskal–Wallis Test", plain_name="Compare three or more groups using ranks",
    category="nonparametric",
    description="Rank-based alternative to one-way ANOVA.",
    roles=[Role("dependent", "Test variable", "", SCALE_LEVELS), Role("factor", "Grouping variable", "", CATEGORICAL_LEVELS)],
    options=[Option("posthoc", "Dunn's post hoc adjustment", "select", "holm", PH), ALWAYS],
    run=run_kruskal, code=code_kw,
    assumptions=["Independent observations.", "Ordinal or continuous outcome."],
    method="scipy.stats.kruskal (tie-corrected H); ε² effect size; Dunn's test with tie correction.",
    references=["Dunn, O. J. (1964). Technometrics, 6, 241–252."],
))
FRIED = register(AnalysisSpec(
    id="friedman", name="Friedman Test", plain_name="Compare three or more related measurements using ranks",
    category="nonparametric",
    description="Rank-based alternative to repeated-measures ANOVA.",
    roles=[Role("within", "Repeated measurements", "", SCALE_LEVELS, 3, None)],
    options=[Option("posthoc", "Pairwise Wilcoxon adjustment", "select", "holm", PH), ALWAYS],
    run=run_friedman, code=code_friedman,
    assumptions=["The same cases measured under every condition."],
    method="scipy.stats.friedmanchisquare; Kendall's W; pairwise Wilcoxon tests with p-value adjustment.",
))
