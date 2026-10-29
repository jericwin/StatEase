"""Chi-square tests of independence and goodness of fit, Fisher's exact test, one-sample proportion test."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..errors import AnalysisError
from . import codegen
from .base import (
    CATEGORICAL_LEVELS,
    AnalysisSpec,
    Context,
    Option,
    Result,
    Role,
    assigned,
    col,
    fmt_p,
    listwise,
    register,
    sig_phrase,
)
from .common import cramer_label


def _opts(spec, config):
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def run_crosstab(ctx: Context, config: dict[str, Any], spec: AnalysisSpec | None = None) -> Result:
    spec = spec or CHI
    res = Result(spec, config, ctx)
    o = _opts(spec, config)
    rv, cv = assigned(config, "rows")[0], assigned(config, "columns")[0]
    df = listwise(ctx.frame([rv, cv]), [rv, cv], res)
    r = ctx.categorical(df, rv).cat.remove_unused_categories()
    c = ctx.categorical(df, cv).cat.remove_unused_categories()
    table = pd.crosstab(r, c)
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise AnalysisError("Both variables need at least two categories with data to form a contingency table.")
    if table.size > 400:
        raise AnalysisError("The table has more than 400 cells; merge categories first.")
    obs = table.to_numpy()
    n = int(obs.sum())
    res.n = n
    chi = stats.chi2_contingency(obs, correction=bool(o["yates"]) and obs.shape == (2, 2))
    expected = chi.expected_freq
    rlabels, clabels = [str(x) for x in table.index], [str(x) for x in table.columns]
    rows = []
    for i, rl in enumerate(rlabels):
        row = {"row": rl, "_kind": "Count"}
        for j, _cl in enumerate(clabels):
            row[f"c{j}"] = int(obs[i, j])
        row["total"] = int(obs[i].sum())
        rows.append(row)
        if o["show_expected"]:
            rows.append({"row": "", "_kind": "Expected", **{f"c{j}": float(expected[i, j]) for j in range(len(clabels))},
                         "total": None, "_style": "muted"})
        if o["show_row_pct"]:
            rows.append({"row": "", "_kind": f"% within {ctx.label(rv)}",
                         **{f"c{j}": obs[i, j] / obs[i].sum() * 100 for j in range(len(clabels))}, "total": 100.0,
                         "_style": "muted"})
        if o["show_col_pct"]:
            rows.append({"row": "", "_kind": f"% within {ctx.label(cv)}",
                         **{f"c{j}": obs[i, j] / obs[:, j].sum() * 100 for j in range(len(clabels))}, "total": None,
                         "_style": "muted"})
        if o["show_residuals"]:
            adj = (obs[i] - expected[i]) / np.sqrt(expected[i] * (1 - obs[i].sum() / n) * (1 - obs.sum(0) / n))
            rows.append({"row": "", "_kind": "Adjusted residual", **{f"c{j}": float(adj[j]) for j in range(len(clabels))},
                         "total": None, "_style": "muted"})
    rows.append({"row": "Total", "_kind": "Count", **{f"c{j}": int(obs[:, j].sum()) for j in range(len(clabels))},
                 "total": n, "_style": "total"})
    for r_ in rows:
        r_["kind"] = r_.pop("_kind")
    res.table("crosstab", "descriptives", f"{ctx.label(rv)} × {ctx.label(cv)}",
              [col("row", ctx.label(rv), "text"), col("kind", "", "text")]
              + [col(f"c{j}", cl, "num") for j, cl in enumerate(clabels)] + [col("total", "Total", "num")], rows,
              ["Adjusted standardised residuals beyond ±1.96 mark cells that contribute most to the association."
               if o["show_residuals"] else ""])
    k = min(obs.shape) - 1
    V = math.sqrt(chi.statistic / (n * k)) if n and k else math.nan
    if obs.shape == (2, 2):
        a, b, c_, d = obs.ravel()
        den = math.sqrt((a + b) * (c_ + d) * (a + c_) * (b + d))
        phi = (a * d - b * c_) / den if den else math.nan
    else:
        phi = None
    low = (expected < 5).sum()
    pct_low = low / expected.size * 100
    test_rows = [{"test": "Pearson χ²" + (" (Yates continuity correction)" if o["yates"] and obs.shape == (2, 2) else ""),
                  "value": chi.statistic, "df": chi.dof, "p": chi.pvalue}]
    g = stats.chi2_contingency(obs, correction=False, lambda_="log-likelihood")
    test_rows.append({"test": "Likelihood ratio (G)", "value": g.statistic, "df": g.dof, "p": g.pvalue})
    fisher_p = None
    if obs.shape == (2, 2) and (o["fisher"] or spec.id == "fisher_exact" or low):
        fr = stats.fisher_exact(obs, alternative="two-sided")
        fisher_p = float(fr.pvalue)
        test_rows.append({"test": "Fisher's exact test (two-sided)", "value": float(fr.statistic), "df": None,
                          "p": fisher_p, "_note": "value = odds ratio"})
    elif spec.id == "fisher_exact":
        raise AnalysisError("Fisher's exact test is available for 2 × 2 tables. For larger tables use the chi-square "
                            "test, merging sparse categories if expected counts are small.")
    res.table("main", "main", "Chi-Square Tests",
              [col("test", "Test", "text"), col("value", "Value", "stat", "statistic"), col("df", "df", "int", "df"),
               col("p", "p", "p", "p")], test_rows,
              [f"{low} of {expected.size} cells ({pct_low:.0f}%) have expected counts below 5; minimum expected count "
               f"= {expected.min():.2f}."] + (["For Fisher's test the value shown is the sample odds ratio."]
                                               if fisher_p is not None else []))
    eff = [{"measure": "Cramér's V", "value": V, "label": cramer_label(V, k)}]
    if phi is not None:
        eff.insert(0, {"measure": "Phi (φ)", "value": phi, "label": cramer_label(abs(phi), 1)})
    res.table("effect", "effect", "Effect Size", [col("measure", "Measure", "text"), col("value", "Value", "r", "effect"),
                                                 col("label", "Magnitude", "text", "effect")], eff)
    if pct_low > 20 or expected.min() < 1:
        msg = (f"{pct_low:.0f}% of cells have expected counts below 5 (minimum {expected.min():.2f}). The chi-square "
               "approximation may be inaccurate.")
        res.assumption("Expected cell counts", "violated", msg + (" Fisher's exact test is reported." if fisher_p is not None
                                                                  else " Merge sparse categories or collect more data."))
    else:
        res.assumption("Expected cell counts", "ok", "At least 80% of cells have expected counts of 5 or more and none "
                       "are below 1.")
    res.assumption("Independence", "info", "Each case is counted in exactly one cell.")
    series = [{"name": cl, "values": [float(obs[i, j] / obs[i].sum() * 100) for i in range(len(rlabels))]}
              for j, cl in enumerate(clabels)]
    res.chart("stacked", "bar", f"{ctx.label(cv)} by {ctx.label(rv)}", {"categories": rlabels, "series": series,
                                                                         "stacked": True, "percent": True},
              ctx.label(rv), "Percent", f"Percentage of each {ctx.label(cv)} category within each {ctx.label(rv)} group.")
    p_main = fisher_p if (spec.id == "fisher_exact" or (fisher_p is not None and pct_low > 20)) else chi.pvalue
    sig, phrase = sig_phrase(p_main, ctx.alpha)
    res.summary = {"statistic": chi.statistic, "df": chi.dof, "p": p_main, "effect": V, "effect_name": "Cramér's V",
                   "significant": sig}
    res.interpretation = {
        "plain": (f"{ctx.label(rv)} and {ctx.label(cv)} are " + ("" if sig else "not ") + "significantly associated"
                  + (f": the distribution of {ctx.label(cv)} differs between {ctx.label(rv)} groups ({cramer_label(V, k)} "
                     "association)." if sig else ".")),
        "technical": (f"A chi-square test of independence: χ²({chi.dof}, N = {n}) = {chi.statistic:.2f}, "
                      f"{fmt_p(chi.pvalue, ctx.p_style)}, Cramér's V = {V:.2f}"
                      + (f"; Fisher's exact {fmt_p(fisher_p, ctx.p_style)}" if fisher_p is not None else "")
                      + f". The association is {phrase}."),
    }
    return res


def code_crosstab(config, v):
    rv, cv = assigned(config, "rows")[0], assigned(config, "columns")[0]
    return (codegen.prelude(v, [rv, cv], ["from scipy import stats"])
            + f"table = pd.crosstab(df[{rv!r}], df[{cv!r}])\nprint(table)\n"
            "res = stats.chi2_contingency(table, correction=False)\nprint(res)\n"
            "n = table.to_numpy().sum(); k = min(table.shape) - 1\nprint('Cramer V =', np.sqrt(res.statistic / (n * k)))\n"
            "if table.shape == (2, 2):\n    print(stats.fisher_exact(table))\n")


def run_gof(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(GOF, config, ctx)
    o = _opts(GOF, config)
    var = assigned(config, "variable")[0]
    df = listwise(ctx.frame([var]), [var], res)
    cat = ctx.categorical(df, var).cat.remove_unused_categories() if not o["include_empty"] else ctx.categorical(df, var)
    counts = cat.value_counts(sort=False)
    levels = [str(x) for x in counts.index]
    obs = counts.to_numpy(float)
    n = obs.sum()
    res.n = int(n)
    if len(levels) < 2:
        raise AnalysisError("At least two categories are needed.")
    props_text = (o.get("expected") or "").strip()
    if props_text:
        try:
            props = np.array([float(x) for x in props_text.replace(";", ",").split(",")])
        except ValueError as exc:
            raise AnalysisError("Expected proportions must be numbers separated by commas.") from exc
        if len(props) != len(levels):
            raise AnalysisError(f"Give one expected proportion per category ({len(levels)}: {', '.join(levels)}).")
        if (props <= 0).any():
            raise AnalysisError("Expected proportions must be positive.")
        props = props / props.sum()
    else:
        props = np.full(len(levels), 1 / len(levels))
    exp = props * n
    chi, p = stats.chisquare(obs, exp)
    res.table("desc", "descriptives", f"Observed and Expected: {ctx.label(var)}",
              [col("category", ctx.label(var), "text"), col("observed", "Observed", "int"),
               col("expected", "Expected", "num"), col("residual", "Residual", "num")],
              [{"category": lv, "observed": int(o_), "expected": e, "residual": o_ - e}
               for lv, o_, e in zip(levels, obs, exp, strict=True)])
    w = math.sqrt(chi / n)
    res.table("main", "main", "Chi-Square Goodness-of-Fit Test",
              [col("chi2", "χ²", "stat", "statistic"), col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("w", "Cohen's w", "num", "effect"), col("n", "N", "int", "n")],
              [{"chi2": chi, "df": len(levels) - 1, "p": p, "w": w, "n": int(n)}],
              ["Expected proportions: " + ("equal" if not props_text else ", ".join(f"{x:.3f}" for x in props)) + "."])
    if (exp < 5).any():
        res.assumption("Expected counts", "violated", f"Some expected counts are below 5 (minimum {exp.min():.2f}).")
    else:
        res.assumption("Expected counts", "ok", "All expected counts are 5 or more.")
    res.chart("bar", "bar", f"Observed vs expected: {ctx.label(var)}",
              {"categories": levels, "series": [{"name": "Observed", "values": obs.tolist()},
                                                {"name": "Expected", "values": exp.tolist()}]},
              ctx.label(var), "Count", "Observed counts compared with the counts expected under the hypothesis.")
    sig, phrase = sig_phrase(p, ctx.alpha)
    res.summary = {"statistic": chi, "df": len(levels) - 1, "p": p, "effect": w, "effect_name": "w", "significant": sig}
    res.interpretation = {
        "plain": f"The observed distribution of {ctx.label(var)} " + ("differs significantly from" if sig else
                                                                      "is consistent with") + " the expected distribution.",
        "technical": f"χ²({len(levels) - 1}, N = {int(n)}) = {chi:.2f}, {fmt_p(p, ctx.p_style)}, w = {w:.2f}; {phrase}.",
    }
    return res


def code_gof(config, v):
    var = assigned(config, "variable")[0]
    return (codegen.prelude(v, [var], ["from scipy import stats"])
            + f"counts = df[{var!r}].value_counts(sort=False)\nprint(stats.chisquare(counts))  # equal expected\n")


def run_proportion(ctx: Context, config: dict[str, Any]) -> Result:
    from statsmodels.stats.proportion import proportion_confint

    res = Result(PROP, config, ctx)
    o = _opts(PROP, config)
    var = assigned(config, "variable")[0]
    df = listwise(ctx.frame([var]), [var], res)
    cat = ctx.categorical(df, var)
    levels = [str(x) for x in cat.cat.categories if (cat == x).any()]
    success = o.get("success") if o.get("success") in levels else (levels[-1] if levels else None)
    if success is None:
        raise AnalysisError("The variable has no values.")
    k = int((cat.astype(str) == success).sum())
    n = len(cat)
    res.n = n
    p0 = float(o["p0"])
    if not 0 < p0 < 1:
        raise AnalysisError("The test proportion must be between 0 and 1.")
    level = float(o["ci_level"])
    bt = stats.binomtest(k, n, p0, alternative=o["alternative"])
    lo, hi = proportion_confint(k, n, alpha=1 - level, method="wilson")
    res.table("main", "main", "One-Sample Proportion Test",
              [col("category", "Category", "text"), col("k", "Count", "int"), col("n", "N", "int", "n"),
               col("prop", "Proportion", "num"), col("p0", "Test value", "num"), col("p", "p (exact binomial)", "p", "p"),
               col("ci_lower", f"{level:.0%} CI lower (Wilson)", "num", "ci"),
               col("ci_upper", f"{level:.0%} CI upper (Wilson)", "num", "ci")],
              [{"category": success, "k": k, "n": n, "prop": k / n, "p0": p0, "p": bt.pvalue, "ci_lower": lo,
                "ci_upper": hi}])
    sig, phrase = sig_phrase(bt.pvalue, ctx.alpha)
    res.summary = {"p": bt.pvalue, "effect": k / n, "effect_name": "proportion", "significant": sig}
    res.interpretation = {
        "plain": f"{k / n:.1%} of cases were '{success}', which is " + ("significantly different from" if sig else
                                                                        "not significantly different from") + f" {p0:.0%}.",
        "technical": (f"Exact binomial test: {k}/{n} = {k / n:.3f} vs p0 = {p0:g}, {fmt_p(bt.pvalue, ctx.p_style)}; "
                      f"{level:.0%} Wilson CI [{lo:.3f}, {hi:.3f}]; {phrase}."),
    }
    return res


def code_prop(config, v):
    o = _opts(PROP, config)
    var = assigned(config, "variable")[0]
    return (codegen.prelude(v, [var], ["from scipy import stats",
                                       "from statsmodels.stats.proportion import proportion_confint"])
            + f"k = (df[{var!r}].astype(str) == {str(o.get('success'))!r}).sum(); n = len(df)\n"
            f"print(stats.binomtest(k, n, {float(o['p0'])!r}))\nprint(proportion_confint(k, n, method='wilson'))\n")


CROSS_OPTS = [
    Option("fisher", "Fisher's exact test (2 × 2 tables)", "bool", False),
    Option("yates", "Yates continuity correction (2 × 2)", "bool", False, advanced=True),
    Option("show_expected", "Expected counts", "bool", True),
    Option("show_row_pct", "Row percentages", "bool", True),
    Option("show_col_pct", "Column percentages", "bool", False, advanced=True),
    Option("show_residuals", "Adjusted residuals", "bool", False, advanced=True),
]
ROLES = [Role("rows", "Row variable", "", CATEGORICAL_LEVELS, plain="First category variable"),
         Role("columns", "Column variable", "", CATEGORICAL_LEVELS, plain="Second category variable")]

CHI = register(AnalysisSpec(
    id="chi_square", name="Chi-Square Test of Independence", plain_name="Check whether two categorical variables are related",
    category="categorical",
    description="Tests whether the distribution of one categorical variable differs across the categories of another.",
    when_to_use="Two categorical variables, e.g. gender and preferred product.",
    roles=ROLES, options=CROSS_OPTS, run=run_crosstab, code=code_crosstab,
    assumptions=["Independent observations.", "Expected counts ≥ 5 in at least 80% of cells and none below 1."],
    method="Pearson χ² (scipy.stats.chi2_contingency), likelihood-ratio G, Fisher's exact for 2 × 2 tables; "
           "Cramér's V and φ.",
))
FISHER = register(AnalysisSpec(
    id="fisher_exact", name="Fisher's Exact Test", plain_name="Test a 2 × 2 table with small counts",
    category="categorical",
    description="Exact test of association for two binary variables; valid with small expected counts.",
    roles=ROLES, options=CROSS_OPTS,
    run=lambda ctx, cfg: run_crosstab(ctx, cfg, FISHER), code=code_crosstab,
    assumptions=["Independent observations.", "Fixed margins (conditional test)."],
    method="scipy.stats.fisher_exact (two-sided).",
))
GOF = register(AnalysisSpec(
    id="chi_square_gof", name="Chi-Square Goodness-of-Fit", plain_name="Compare category counts with expected proportions",
    category="categorical",
    description="Tests whether observed category frequencies match expected proportions (equal by default).",
    roles=[Role("variable", "Variable", "", CATEGORICAL_LEVELS)],
    options=[Option("expected", "Expected proportions", "text", "", help="Comma-separated, in category order. Blank = equal."),
             Option("include_empty", "Include categories with no cases", "bool", False, advanced=True)],
    run=run_gof, code=code_gof,
    assumptions=["Independent observations.", "Expected counts ≥ 5."],
    method="scipy.stats.chisquare; Cohen's w.",
))
PROP = register(AnalysisSpec(
    id="proportion_test", name="One-Sample Proportion Test", plain_name="Compare a percentage with a target value",
    category="categorical",
    description="Exact binomial test of whether the proportion in one category differs from a reference value.",
    roles=[Role("variable", "Variable", "", CATEGORICAL_LEVELS)],
    options=[Option("success", "Category of interest", "level", None, depends_on="variable"),
             Option("p0", "Test proportion", "number", 0.5, min=0.0, max=1.0),
             Option("alternative", "Alternative hypothesis", "select", "two-sided",
                    [{"value": "two-sided", "label": "Two-sided"}, {"value": "greater", "label": "Greater"},
                     {"value": "less", "label": "Less"}], advanced=True),
             Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)],
    run=run_proportion, code=code_prop,
    method="scipy.stats.binomtest (exact); Wilson score interval (statsmodels).",
))
