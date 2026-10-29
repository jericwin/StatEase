"""Standalone assumption checks: normality diagnostics and homogeneity of variance."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from . import codegen
from .base import (
    CATEGORICAL_LEVELS,
    SCALE_LEVELS,
    AnalysisSpec,
    Context,
    Result,
    Role,
    assigned,
    col,
    fmt_p,
    listwise,
    register,
)
from .common import describe, group_arrays, histogram_data, qq_data, shapiro


def run_normality(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(NORM, config, ctx)
    names = assigned(config, "variables")
    df = ctx.frame(names)
    res.n = len(df)
    rows = []
    for n in names:
        x = ctx.numeric(df, n).dropna().to_numpy(float)
        d = describe(x)
        sw = shapiro(x, ctx.shapiro_max_n)
        row = {"variable": ctx.label(n), "n": len(x), "skewness": d.get("skewness"), "se_skewness": d.get("se_skewness"),
               "kurtosis": d.get("kurtosis"), "se_kurtosis": d.get("se_kurtosis")}
        if sw and not sw.get("skipped"):
            row.update(W=sw["W"], p=sw["p"])
        if len(x) >= 20 and np.ptp(x) > 0:
            k2, pk = stats.normaltest(x)
            row.update(k2=k2, p_k2=pk)
        rows.append(row)
        if len(x) >= 3:
            res.chart(f"qq_{n}", "qq", f"Normal Q–Q plot: {ctx.label(n)}", qq_data(x), "Theoretical quantiles",
                      "Observed", "Points along the line indicate approximate normality.")
            res.chart(f"hist_{n}", "histogram", f"Distribution of {ctx.label(n)}", histogram_data(x), ctx.label(n),
                      "Frequency", "Histogram with a fitted normal curve.")
    res.table("main", "main", "Normality Diagnostics",
              [col("variable", "Variable", "text"), col("n", "N", "int", "n"), col("W", "Shapiro–Wilk W", "stat", "statistic"),
               col("p", "p (Shapiro–Wilk)", "p", "p"), col("k2", "D'Agostino K²", "stat", "statistic"),
               col("p_k2", "p (K²)", "p", "p"), col("skewness", "Skewness", "num"), col("se_skewness", "SE", "num"),
               col("kurtosis", "Excess kurtosis", "num"), col("se_kurtosis", "SE", "num")], rows,
              [f"Shapiro–Wilk is computed for n ≤ {ctx.shapiro_max_n:,}. With large samples, normality tests detect "
               "trivial departures; judge practical importance from skewness, kurtosis and the Q–Q plots."])
    nonnormal = [r["variable"] for r in rows if r.get("p") is not None and r["p"] < ctx.alpha]
    res.interpretation = {
        "plain": ("These variables depart significantly from a normal distribution: " + ", ".join(nonnormal) + ". "
                  if nonnormal else "No variable departed significantly from normality. ")
                 + "Use the plots to judge whether the departure is large enough to matter.",
        "technical": "; ".join(f"{r['variable']}: W = {r['W']:.3f}, {fmt_p(r['p'], ctx.p_style)}" for r in rows
                               if r.get("W") is not None) + ".",
    }
    return res


def run_homogeneity(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(HOMO, config, ctx)
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    df = listwise(ctx.frame([dv, factor]), [dv, factor], res)
    names, arrays = group_arrays(ctx.numeric(df, dv), ctx.categorical(df, factor))
    arrays = [a for a in arrays if len(a) > 1]
    res.n = sum(len(a) for a in arrays)
    rows = []
    for label, fn in (("Levene (mean-centred)", lambda: stats.levene(*arrays, center="mean")),
                      ("Brown–Forsythe (median-centred)", lambda: stats.levene(*arrays, center="median")),
                      ("Bartlett", lambda: stats.bartlett(*arrays))):
        s, p = fn()
        rows.append({"test": label, "statistic": s, "df1": len(arrays) - 1,
                     "df2": res.n - len(arrays) if label != "Bartlett" else None, "p": p})
    res.table("desc", "descriptives", "Group Variances",
              [col("group", ctx.label(factor), "text"), col("n", "N", "int", "n"), col("sd", "SD", "num", "sd"),
               col("variance", "Variance", "num", "variance")],
              [{"group": n, **describe(a)} for n, a in zip(names, arrays, strict=False)])
    res.table("main", "main", "Homogeneity of Variance Tests",
              [col("test", "Test", "text"), col("statistic", "Statistic", "stat", "statistic"),
               col("df1", "df1", "int", "df"), col("df2", "df2", "int", "df"), col("p", "p", "p", "p")], rows,
              ["Bartlett's test is sensitive to non-normality; Brown–Forsythe is the most robust."])
    bf = rows[1]
    res.interpretation = {
        "plain": "The spread of " + ctx.label(dv) + (" differs" if bf["p"] < ctx.alpha else " does not differ significantly")
                 + f" between {ctx.label(factor)} groups.",
        "technical": f"Brown–Forsythe F({bf['df1']}, {bf['df2']}) = {bf['statistic']:.2f}, {fmt_p(bf['p'], ctx.p_style)}.",
    }
    return res


def code_norm(config, v):
    names = assigned(config, "variables")
    return (codegen.prelude(v, names, ["from scipy import stats"], listwise=False)
            + f"for c in {names!r}:\n    x = df[c].dropna()\n    print(c, stats.shapiro(x), stats.skew(x, bias=False), "
              "stats.kurtosis(x, bias=False))\n")


def code_homo(config, v):
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    return (codegen.prelude(v, [dv, factor], ["from scipy import stats"])
            + f"groups = [g[{dv!r}] for _, g in df.groupby({factor!r}, observed=True)]\n"
              "print(stats.levene(*groups, center='mean'), stats.levene(*groups, center='median'), stats.bartlett(*groups))\n")


NORM = register(AnalysisSpec(
    id="normality", name="Normality Diagnostics", plain_name="Check whether data look normally distributed",
    category="assumptions",
    description="Shapiro–Wilk and D'Agostino tests, skewness, kurtosis, histograms and Q–Q plots.",
    roles=[Role("variables", "Variables", "", SCALE_LEVELS, 1, 20)],
    options=[], run=run_normality, code=code_norm,
    method="scipy.stats.shapiro, scipy.stats.normaltest; bias-corrected skewness and excess kurtosis.",
    missing_data="Each variable uses its available values.",
))
HOMO = register(AnalysisSpec(
    id="homogeneity", name="Homogeneity of Variance", plain_name="Check whether groups have similar spread",
    category="assumptions",
    description="Levene, Brown–Forsythe and Bartlett tests of equal variances across groups.",
    roles=[Role("dependent", "Variable", "", SCALE_LEVELS), Role("factor", "Grouping variable", "", CATEGORICAL_LEVELS)],
    options=[], run=run_homogeneity, code=code_homo,
    method="scipy.stats.levene (mean and median centring) and scipy.stats.bartlett.",
))
