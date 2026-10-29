"""Analysis of variance: one-way, Welch, factorial, repeated measures, mixed design and ANCOVA.

These are distinct procedures and are presented as such:
- One-way ANOVA: one between-subjects factor, equal variances assumed.
- Welch's ANOVA: one between-subjects factor, variances may differ.
- Factorial (two-way and higher) ANOVA: several between-subjects factors with main and interaction effects.
- Repeated-measures ANOVA: the same cases measured under several conditions (within-subjects factor).
- Mixed-design ANOVA: one within-subjects factor and one between-subjects factor.
- ANCOVA: a between-subjects factor while statistically adjusting for one or more covariates.
"""

from __future__ import annotations

import math
import re
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..errors import AnalysisError
from . import codegen
from .base import (
    CATEGORICAL_LEVELS,
    NUMERIC_LEVELS,
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
from .common import (
    box_stats,
    describe,
    eta_label,
    levene,
    mean_ci,
    normality_assessment,
    p_adjust,
    qq_data,
)

POSTHOC_CHOICES = [{"value": "tukey", "label": "Tukey HSD (equal variances)"},
                   {"value": "games_howell", "label": "Games–Howell (unequal variances)"},
                   {"value": "bonferroni", "label": "Pairwise t-tests, Bonferroni"},
                   {"value": "holm", "label": "Pairwise t-tests, Holm"},
                   {"value": "none", "label": "None"}]
ANOVA_COLS = [col("source", "Source", "text"), col("ss", "Sum of squares", "num"), col("df", "df", "num", "df"),
              col("ms", "Mean square", "num"), col("F", "F", "stat", "statistic"), col("p", "p", "p", "p")]


def _opts(spec: AnalysisSpec, config: dict[str, Any]) -> dict[str, Any]:
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def _safe(name: str) -> str:
    return "v_" + re.sub(r"\W", "_", name)


def _group_desc(res: Result, ctx: Context, names: list[str], arrays: list[np.ndarray], factor_label: str,
                level: float) -> None:
    rows = [{"group": n, **describe(a, level)} for n, a in zip(names, arrays, strict=True)]
    res.table("desc", "descriptives", "Group Descriptives",
              [col("group", factor_label, "text"), col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"),
               col("sd", "SD", "num", "sd"), col("se", "SE", "num", "se"),
               col("ci_lower", f"{level:.0%} CI lower", "num", "ci"), col("ci_upper", f"{level:.0%} CI upper", "num", "ci")],
              rows)


def _posthoc(res: Result, method: str, names: list[str], arrays: list[np.ndarray], dv: str, factor: str,
             df: pd.DataFrame, level: float) -> list[dict[str, Any]]:
    if method == "none" or len(names) < 3:
        return []
    rows: list[dict[str, Any]] = []
    if method == "tukey":
        r = stats.tukey_hsd(*arrays)
        ci = r.confidence_interval(confidence_level=level)
        for i, j in combinations(range(len(names)), 2):
            rows.append({"a": names[i], "b": names[j], "diff": float(np.mean(arrays[i]) - np.mean(arrays[j])),
                         "ci_lower": float(ci.low[i, j]), "ci_upper": float(ci.high[i, j]), "p": float(r.pvalue[i, j])})
        title, note = "Post Hoc Comparisons (Tukey HSD)", "p-values and CIs are adjusted for all pairwise comparisons " \
                                                          "(Tukey–Kramer for unequal group sizes)."
    elif method == "games_howell":
        import pingouin as pg

        long = pd.DataFrame({"y": np.concatenate(arrays),
                             "g": np.concatenate([[n] * len(a) for n, a in zip(names, arrays, strict=True)])})
        gh = pg.pairwise_gameshowell(long, dv="y", between="g")
        order = {n: i for i, n in enumerate(names)}
        for _, row in gh.iterrows():
            a, b = str(row["A"]), str(row["B"])
            diff, se, dof = float(row["diff"]), float(row["se"]), float(row["df"])
            if order[a] > order[b]:
                a, b, diff = b, a, -diff
            q = stats.studentized_range.ppf(level, len(names), dof) / math.sqrt(2)
            rows.append({"a": a, "b": b, "diff": diff, "ci_lower": diff - q * se, "ci_upper": diff + q * se,
                         "p": float(row["pval"])})
        title, note = "Post Hoc Comparisons (Games–Howell)", "Does not assume equal variances or group sizes."
    else:
        raw = []
        for i, j in combinations(range(len(names)), 2):
            t = stats.ttest_ind(arrays[i], arrays[j], equal_var=True)
            d = float(np.mean(arrays[i]) - np.mean(arrays[j]))
            raw.append((names[i], names[j], d, float(t.pvalue)))
        adj = p_adjust([r[3] for r in raw], method)
        rows = [{"a": a, "b": b, "diff": d, "p_unadjusted": p, "p": pa}
                for (a, b, d, p), pa in zip(raw, adj, strict=True)]
        title = f"Post Hoc Comparisons (pairwise t-tests, {method.title()} correction)"
        note = f"p-values are {method.title()}-adjusted for {len(rows)} comparisons."
    columns = [col("a", "Group A", "text"), col("b", "Group B", "text"), col("diff", "Mean difference (A − B)", "num")]
    if rows and "ci_lower" in rows[0]:
        columns += [col("ci_lower", f"{level:.0%} CI lower", "num", "ci"), col("ci_upper", f"{level:.0%} CI upper", "num", "ci")]
    if rows and "p_unadjusted" in rows[0]:
        columns.append(col("p_unadjusted", "p (unadjusted)", "p", "p"))
    columns.append(col("p", "p (adjusted)", "p", "p"))
    res.table("posthoc", "posthoc", title, columns, rows, [note])
    return rows


def _posthoc_text(rows: list[dict[str, Any]], alpha: float, dv: str, d: int) -> str:
    sig = [r for r in rows if r["p"] is not None and r["p"] < alpha]
    if not rows:
        return ""
    if not sig:
        return " Post hoc comparisons found no pair of groups that differed significantly."
    parts = [f"{r['a']} {'>' if r['diff'] > 0 else '<'} {r['b']} (difference = {fmt_num(r['diff'], d)})" for r in sig]
    return f" Post hoc comparisons showed significant differences in {dv} for: " + "; ".join(parts) + "."


# --------------------------------------------------------------------------- one-way


def _prepare_oneway(ctx: Context, res: Result, config: dict[str, Any]):
    dv = assigned(config, "dependent")[0]
    factor = assigned(config, "factor")[0]
    df = listwise(ctx.frame([dv, factor]), [dv, factor], res)
    g = ctx.categorical(df, factor)
    y = ctx.numeric(df, dv)
    names, arrays = [], []
    for c in g.cat.categories:
        a = y[g == c].to_numpy(float)
        if len(a):
            names.append(str(c))
            arrays.append(a)
    if len(names) < 2:
        raise AnalysisError(f"'{ctx.label(factor)}' has fewer than two groups with data.")
    if len(names) > 50:
        raise AnalysisError(f"'{ctx.label(factor)}' has {len(names)} groups; ANOVA needs a factor with a manageable "
                            "number of groups.")
    small = [n for n, a in zip(names, arrays, strict=True) if len(a) < 2]
    if small:
        raise AnalysisError(f"Group(s) {', '.join(small)} of '{ctx.label(factor)}' have fewer than two observations.",
                            suggestion="Merge sparse groups or exclude them.")
    if np.ptp(np.concatenate(arrays)) == 0:
        raise AnalysisError(f"'{ctx.label(dv)}' is constant; there is no variation to analyse.")
    res.n = int(sum(len(a) for a in arrays))
    return dv, factor, names, arrays


def run_oneway(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(ONEWAY, config, ctx)
    o = _opts(ONEWAY, config)
    level = float(o["ci_level"])
    dv, factor, names, arrays = _prepare_oneway(ctx, res, config)
    k, n = len(arrays), res.n
    allv = np.concatenate(arrays)
    grand = allv.mean()
    ssb = float(sum(len(a) * (a.mean() - grand) ** 2 for a in arrays))
    ssw = float(sum(((a - a.mean()) ** 2).sum() for a in arrays))
    dfb, dfw = k - 1, n - k
    if dfw <= 0:
        raise AnalysisError("Not enough observations for the number of groups.")
    msb, msw = ssb / dfb, ssw / dfw
    if msw == 0:
        raise AnalysisError("There is no variation within groups, so F is undefined.")
    F = msb / msw
    p = float(stats.f.sf(F, dfb, dfw))
    eta2 = ssb / (ssb + ssw)
    omega2 = max(0.0, (ssb - dfb * msw) / (ssb + ssw + msw))
    _group_desc(res, ctx, names, arrays, ctx.label(factor), level)
    res.table("main", "main", f"One-Way ANOVA: {ctx.label(dv)}",
              ANOVA_COLS + [col("eta2", "η²", "num", "effect"), col("omega2", "ω²", "num", "effect")],
              [{"source": ctx.label(factor), "ss": ssb, "df": dfb, "ms": msb, "F": F, "p": p, "eta2": eta2,
                "omega2": omega2},
               {"source": "Residuals", "ss": ssw, "df": dfw, "ms": msw},
               {"source": "Total", "ss": ssb + ssw, "df": n - 1, "_style": "total"}],
              ["η² = SS between / SS total. ω² is a less biased estimate of the population effect."])
    lev = levene(res, arrays)
    resid = np.concatenate([a - a.mean() for a in arrays])
    normality_assessment(res, resid, ctx.label(dv), what="residuals")
    res.assumption("Independence", "info", "Each case should appear in only one group (between-subjects design).")
    if lev and not lev["equal"]:
        res.warn("Group variances differ (Levene's test). Welch's ANOVA with Games–Howell post hoc tests is more "
                 "appropriate; it is available as a separate analysis and was not substituted automatically.")
    method = o["posthoc"]
    if method == "auto":
        method = "games_howell" if lev and not lev["equal"] else "tukey"
    ph = _posthoc(res, method, names, arrays, dv, factor, None, level) if p < ctx.alpha or o["posthoc_always"] else []
    if p >= ctx.alpha and not o["posthoc_always"] and k > 2:
        res.notes.append("Post hoc comparisons were not run because the overall ANOVA was not significant.")
    _charts(res, ctx, dv, factor, names, arrays, level, resid)
    sig, phrase = sig_phrase(p, ctx.alpha)
    d = ctx.decimals
    res.summary = {"statistic": F, "df": [dfb, dfw], "p": p, "effect": eta2, "effect_name": "η²", "significant": sig}
    means = ", ".join(f"{nm} M = {fmt_num(a.mean(), d)}" for nm, a in zip(names, arrays, strict=True))
    res.interpretation = {
        "plain": ((f"The average {ctx.label(dv)} differed significantly across {ctx.label(factor)} groups "
                   f"(a {eta_label(eta2)} effect)." if sig else
                   f"The average {ctx.label(dv)} did not differ significantly across {ctx.label(factor)} groups.")
                  + (" The overall test shows that at least one group differs; the post hoc table identifies which."
                     if sig and k > 2 else "")),
        "technical": (f"A one-way ANOVA examined {ctx.label(dv)} across {k} {ctx.label(factor)} groups ({means}): "
                      f"F({dfb}, {dfw}) = {F:.2f}, {fmt_p(p, ctx.p_style)}, η² = {eta2:.3f}, ω² = {omega2:.3f}. "
                      f"The effect is {phrase} at α = {ctx.alpha:g}." + _posthoc_text(ph, ctx.alpha, ctx.label(dv), d)),
    }
    return res


def _charts(res, ctx, dv, factor, names, arrays, level, resid=None):
    res.chart("box", "box", f"{ctx.label(dv)} by {ctx.label(factor)}",
              {"groups": [box_stats(n, a) for n, a in zip(names, arrays, strict=True)]}, ctx.label(factor),
              ctx.label(dv), "Box plots of each group.")
    res.chart("means", "meanci", f"Mean {ctx.label(dv)} by {ctx.label(factor)}",
              {"groups": [mean_ci(n, a, level) for n, a in zip(names, arrays, strict=True)]}, ctx.label(factor),
              ctx.label(dv), f"Group means with {level:.0%} confidence intervals.")
    if resid is not None:
        res.chart("qq", "qq", "Normal Q–Q plot of residuals", qq_data(resid), "Theoretical quantiles", "Residuals",
                  "Checks whether residuals are approximately normal.")


def code_oneway(config, v):
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    o = _opts(ONEWAY, config)
    return (codegen.prelude(v, [dv, factor], ["from scipy import stats"]) + codegen.numeric_ordinal_note(v, [dv])
            + f"groups = [g[{dv!r}].to_numpy(float) for _, g in df.groupby({factor!r}, observed=True)]\n"
            "print(stats.f_oneway(*groups))\nprint(stats.levene(*groups, center='median'))\n"
            + ("print(stats.tukey_hsd(*groups))\n" if o["posthoc"] in ("tukey", "auto") else "")
            + (f"import pingouin as pg\nprint(pg.pairwise_gameshowell(df, dv={dv!r}, between={factor!r}))\n"
               if o["posthoc"] == "games_howell" else ""))


# --------------------------------------------------------------------------- Welch


def run_welch(ctx: Context, config: dict[str, Any]) -> Result:
    import pingouin as pg

    res = Result(WELCH, config, ctx)
    o = _opts(WELCH, config)
    level = float(o["ci_level"])
    dv, factor, names, arrays = _prepare_oneway(ctx, res, config)
    long = pd.DataFrame({"y": np.concatenate(arrays),
                         "g": np.concatenate([[n] * len(a) for n, a in zip(names, arrays, strict=True)])})
    w = pg.welch_anova(long, dv="y", between="g").iloc[0]
    F, df1, df2, p = float(w["F"]), float(w["ddof1"]), float(w["ddof2"]), float(w["p_unc"])
    grand = long["y"].mean()
    ssb = float(sum(len(a) * (a.mean() - grand) ** 2 for a in arrays))
    sst = float(((long["y"] - grand) ** 2).sum())
    eta2 = ssb / sst
    _group_desc(res, ctx, names, arrays, ctx.label(factor), level)
    res.table("main", "main", f"Welch's ANOVA: {ctx.label(dv)}",
              [col("source", "Source", "text"), col("F", "F", "stat", "statistic"), col("df1", "df1", "num", "df"),
               col("df2", "df2", "num", "df"), col("p", "p", "p", "p"), col("eta2", "η²", "num", "effect")],
              [{"source": ctx.label(factor), "F": F, "df1": df1, "df2": df2, "p": p, "eta2": eta2}],
              ["Welch's F does not assume equal group variances. η² is descriptive (based on the ordinary sums of "
               "squares)."])
    levene(res, arrays)
    resid = np.concatenate([a - a.mean() for a in arrays])
    normality_assessment(res, resid, ctx.label(dv), what="residuals")
    ph = _posthoc(res, o["posthoc"], names, arrays, dv, factor, None, level) if p < ctx.alpha or o["posthoc_always"] else []
    _charts(res, ctx, dv, factor, names, arrays, level, resid)
    sig, phrase = sig_phrase(p, ctx.alpha)
    d = ctx.decimals
    res.summary = {"statistic": F, "df": [df1, df2], "p": p, "effect": eta2, "effect_name": "η²", "significant": sig}
    res.interpretation = {
        "plain": (f"Allowing for unequal spread between groups, the average {ctx.label(dv)} "
                  + ("differed significantly" if sig else "did not differ significantly")
                  + f" across {ctx.label(factor)} groups."),
        "technical": (f"Welch's ANOVA: F({df1:.0f}, {df2:.2f}) = {F:.2f}, {fmt_p(p, ctx.p_style)}, η² = {eta2:.3f}; "
                      f"{phrase} at α = {ctx.alpha:g}." + _posthoc_text(ph, ctx.alpha, ctx.label(dv), d)),
    }
    return res


def code_welch(config, v):
    dv, factor = assigned(config, "dependent")[0], assigned(config, "factor")[0]
    return (codegen.prelude(v, [dv, factor], ["import pingouin as pg"]) + codegen.numeric_ordinal_note(v, [dv])
            + f"print(pg.welch_anova(df, dv={dv!r}, between={factor!r}))\n"
            f"print(pg.pairwise_gameshowell(df, dv={dv!r}, between={factor!r}))\n")


# --------------------------------------------------------------------------- factorial


def run_factorial(ctx: Context, config: dict[str, Any]) -> Result:
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    res = Result(FACT, config, ctx)
    o = _opts(FACT, config)
    level = float(o["ci_level"])
    dv = assigned(config, "dependent")[0]
    factors = assigned(config, "factors")
    df = listwise(ctx.frame([dv, *factors]), [dv, *factors], res)
    data = pd.DataFrame({"y": ctx.numeric(df, dv)})
    for f in factors:
        data[_safe(f)] = ctx.categorical(df, f).cat.remove_unused_categories()
        if len(data[_safe(f)].cat.categories) < 2:
            raise AnalysisError(f"'{ctx.label(f)}' has fewer than two groups with data.")
    res.n = len(data)
    terms = [f"C({_safe(f)}, Sum)" for f in factors]
    rhs = " * ".join(terms) if o["interaction"] else " + ".join(terms)
    cells = data.groupby([_safe(f) for f in factors], observed=True)["y"]
    sizes = cells.size()
    n_cells = int(np.prod([len(data[_safe(f)].cat.categories) for f in factors]))
    if o["interaction"] and len(sizes) < n_cells:
        raise AnalysisError("Some combinations of the factors have no observations, so the interaction cannot be "
                            "estimated.", suggestion="Turn off the interaction term or merge sparse groups.")
    model = smf.ols(f"y ~ {rhs}", data=data).fit()
    if model.df_resid <= 0:
        raise AnalysisError("Not enough observations to estimate this model.")
    typ = int(o["ss_type"])
    table = anova_lm(model, typ=typ)
    ss_res = float(table.loc["Residual", "sum_sq"])
    rows = []
    label_map = {t: ctx.label(f) for t, f in zip(terms, factors, strict=True)}
    for src, r in table.iterrows():
        if src in ("Intercept",):
            continue
        name = " × ".join(label_map.get(p, p) for p in str(src).split(":")) if src != "Residual" else "Residuals"
        ss, dfv = float(r["sum_sq"]), float(r["df"])
        row = {"source": name, "ss": ss, "df": dfv, "ms": ss / dfv if dfv else None}
        if src != "Residual":
            row.update(F=float(r["F"]), p=float(r["PR(>F)"]), partial_eta2=ss / (ss + ss_res))
        rows.append(row)
    res.table("main", "main", f"{len(factors)}-Way ANOVA: {ctx.label(dv)}",
              ANOVA_COLS + [col("partial_eta2", "Partial η²", "num", "effect")], rows,
              [f"Type {'II' if typ == 2 else 'III'} sums of squares with sum-to-zero contrasts. Partial η² = "
               "SS effect / (SS effect + SS residual)."])
    cell_rows = []
    for key, grp in cells:
        key = key if isinstance(key, tuple) else (key,)
        d = describe(grp.to_numpy(float), level)
        cell_rows.append({**{f"f{i}": str(k) for i, k in enumerate(key)}, **d})
    res.table("desc", "descriptives", "Cell Descriptives",
              [col(f"f{i}", ctx.label(f), "text") for i, f in enumerate(factors)]
              + [col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"), col("sd", "SD", "num", "sd"),
                 col("se", "SE", "num", "se")], cell_rows)
    if sizes.nunique() > 1:
        res.notes.append("Cell sizes are unequal (unbalanced design); Type II and Type III sums of squares give "
                         "different answers. Type III is reported by SPSS; Type II is preferred when the interaction "
                         "is negligible.")
    levene(res, [g.to_numpy(float) for _, g in cells])
    normality_assessment(res, model.resid.to_numpy(float), ctx.label(dv), what="residuals")
    res.assumption("Independence", "info", "Each case contributes one observation to one cell.")
    if len(factors) >= 2:
        f0, f1 = factors[0], factors[1]
        series = []
        lv0 = [str(c) for c in data[_safe(f0)].cat.categories]
        for lv1 in data[_safe(f1)].cat.categories:
            vals, lows, highs = [], [], []
            for lv in data[_safe(f0)].cat.categories:
                arr = data.loc[(data[_safe(f0)] == lv) & (data[_safe(f1)] == lv1), "y"].to_numpy(float)
                m = mean_ci("", arr, level)
                vals.append(m.get("mean"))
                lows.append(m.get("lower"))
                highs.append(m.get("upper"))
            series.append({"name": str(lv1), "values": vals, "lower": lows, "upper": highs})
        res.chart("interaction", "interaction", f"Interaction plot: {ctx.label(dv)}",
                  {"categories": lv0, "series": series}, ctx.label(f0), f"Mean {ctx.label(dv)}",
                  f"Cell means of {ctx.label(dv)} by {ctx.label(f0)}, separate lines for {ctx.label(f1)}. Non-parallel "
                  "lines suggest an interaction.")
    res.chart("qq", "qq", "Normal Q–Q plot of residuals", qq_data(model.resid.to_numpy(float)),
              "Theoretical quantiles", "Residuals", "Checks the normality of the model residuals.")
    effects = [r for r in rows if "p" in r]
    sig_eff = [r for r in effects if r["p"] < ctx.alpha]
    inter = [r for r in effects if "×" in r["source"]]
    d = ctx.decimals
    tech = "; ".join(f"{r['source']}: F({r['df']:.0f}, {model.df_resid:.0f}) = {r['F']:.2f}, "
                     f"{fmt_p(r['p'], ctx.p_style)}, partial η² = {r['partial_eta2']:.3f}" for r in effects)
    plain = (("Significant effects were found for " + ", ".join(r["source"] for r in sig_eff) + ".")
             if sig_eff else "None of the factors or their interaction had a significant effect.")
    if any(r["p"] < ctx.alpha for r in inter):
        plain += " Because the interaction is significant, the effect of one factor depends on the level of the " \
                 "other; interpret main effects with care and examine the interaction plot."
    res.summary = {"effects": effects, "significant": bool(sig_eff)}
    res.interpretation = {"plain": plain, "technical": f"A {len(factors)}-way ANOVA on {ctx.label(dv)} (Type "
                                                       f"{'II' if typ == 2 else 'III'} SS): {tech}."}
    return res


def code_factorial(config, v):
    dv, factors = assigned(config, "dependent")[0], assigned(config, "factors")
    o = _opts(FACT, config)
    terms = [f"C(Q({f!r}), Sum)" for f in factors]
    rhs = " * ".join(terms) if o["interaction"] else " + ".join(terms)
    return (codegen.prelude(v, [dv, *factors], ["import statsmodels.formula.api as smf",
                                                 "from statsmodels.stats.anova import anova_lm"])
            + codegen.numeric_ordinal_note(v, [dv])
            + f"model = smf.ols(\"Q({dv!r}) ~ {rhs}\", data=df).fit()\n"
            f"print(anova_lm(model, typ={int(o['ss_type'])}))\n")


# --------------------------------------------------------------------------- repeated measures


def _long(ctx: Context, df: pd.DataFrame, within: list[str], between: str | None = None) -> pd.DataFrame:
    parts = []
    for c in within:
        part = pd.DataFrame({"subject": np.arange(len(df)), "condition": ctx.label(c), "y": ctx.numeric(df, c).values})
        if between:
            part["group"] = ctx.categorical(df, between).astype(str).values
        parts.append(part)
    long = pd.concat(parts, ignore_index=True)
    long["condition"] = pd.Categorical(long["condition"], categories=[ctx.label(c) for c in within])
    return long


def _hf_epsilon(gg: float, n: int, k: int, groups: int = 1) -> float:
    num = (n - groups + 1) * (k - 1) * gg - 2
    den = (k - 1) * (n - groups - (k - 1) * gg)
    return float(min(1.0, num / den)) if den > 0 else 1.0


def _sphericity(res: Result, ctx: Context, long: pd.DataFrame, k: int) -> None:
    import pingouin as pg

    if k < 3:
        res.assumption("Sphericity", "ok", "With only two conditions sphericity holds automatically.")
        return
    s = pg.sphericity(long, dv="y", within="condition", subject="subject")
    ok = bool(s.pval >= ctx.alpha) if np.isfinite(s.pval) else True
    res.assumption("Sphericity (Mauchly's test)", "ok" if ok else "violated",
                   f"W = {s.W:.3f}, χ²({s.dof}) = {s.chi2:.2f}, {fmt_p(s.pval, ctx.p_style)}. "
                   + ("No evidence of a sphericity violation." if ok else
                      "Sphericity is violated; use the Greenhouse–Geisser or Huynh–Feldt corrected results."),
                   statistic=float(s.W), p=float(s.pval), test="Mauchly")


def _rm_posthoc(res: Result, ctx: Context, long: pd.DataFrame, method: str, between: str | None = None) -> list:
    if method == "none":
        return []
    import pingouin as pg

    if long["condition"].nunique() < 3:
        return []
    pw = pg.pairwise_tests(long, dv="y", within="condition", subject="subject", padjust=method)
    rows = []
    for _, r in pw.iterrows():
        if "Contrast" in r and r["Contrast"] != "condition":
            continue
        a, b = str(r["A"]), str(r["B"])
        da = long.loc[long["condition"] == a, "y"].mean() - long.loc[long["condition"] == b, "y"].mean()
        rows.append({"a": a, "b": b, "diff": float(da), "t": float(r["T"]), "df": float(r["dof"]),
                     "p_unadjusted": float(r["p_unc"]), "p": float(r.get("p_corr", r["p_unc"]))})
    res.table("posthoc", "posthoc", f"Pairwise Comparisons of Conditions ({method.title()})",
              [col("a", "Condition A", "text"), col("b", "Condition B", "text"), col("diff", "Mean difference", "num"),
               col("t", "t", "stat", "statistic"), col("df", "df", "num", "df"),
               col("p_unadjusted", "p (unadjusted)", "p", "p"), col("p", "p (adjusted)", "p", "p")], rows,
              [f"Paired t-tests with {method.title()} adjustment."])
    return rows


def run_rm(ctx: Context, config: dict[str, Any]) -> Result:
    import pingouin as pg

    res = Result(RM, config, ctx)
    o = _opts(RM, config)
    level = float(o["ci_level"])
    within = assigned(config, "within")
    df = listwise(ctx.frame(within), within, res)
    k, n = len(within), len(df)
    require_n(n, 3, "The repeated-measures data", "Each row must contain every measurement.")
    res.n = n
    long = _long(ctx, df, within)
    arrays = [ctx.numeric(df, c).to_numpy(float) for c in within]
    _group_desc(res, ctx, [ctx.label(c) for c in within], arrays, "Condition", level)
    a = pg.rm_anova(long, dv="y", within="condition", subject="subject", correction=True, detailed=True)
    eff, err = a.iloc[0], a.iloc[1]
    gg = float(eff["eps"]) if "eps" in a and np.isfinite(eff["eps"]) else 1.0
    hf = _hf_epsilon(gg, n, k)
    F, df1, df2 = float(eff["F"]), float(eff["DF"]), float(err["DF"])
    ss_e, ss_err = float(eff["SS"]), float(err["SS"])
    peta = ss_e / (ss_e + ss_err)
    rows = []
    for label, e in (("Sphericity assumed", 1.0), ("Greenhouse–Geisser", gg), ("Huynh–Feldt", hf)):
        if k < 3 and e != 1.0:
            continue
        rows.append({"source": "Condition", "correction": label, "ss": ss_e, "df": df1 * e, "df_error": df2 * e,
                     "F": F, "p": float(stats.f.sf(F, df1 * e, df2 * e)), "epsilon": e, "partial_eta2": peta,
                     "ges": float(eff["ng2"])})
    res.table("main", "main", f"Repeated-Measures ANOVA ({k} conditions)",
              [col("source", "Effect", "text"), col("correction", "Correction", "text"), col("ss", "SS", "num"),
               col("df", "df", "num", "df"), col("df_error", "df error", "num", "df"), col("F", "F", "stat", "statistic"),
               col("p", "p", "p", "p"), col("epsilon", "ε", "num"), col("partial_eta2", "Partial η²", "num", "effect"),
               col("ges", "Generalised η²", "num", "effect")], rows,
              ["Within-subject dependence is modelled by removing between-subject variability from the error term."])
    _sphericity(res, ctx, long, k)
    viol = any(x["status"] == "violated" for x in res.assumptions)
    chosen = rows[1] if (viol and len(rows) > 1) else rows[0]
    if viol:
        res.notes.append("Because sphericity is violated, the Greenhouse–Geisser corrected result is used in the "
                         "interpretation (ε < 0.75 favours GG; ε ≥ 0.75 the less conservative Huynh–Feldt).")
        if gg >= 0.75:
            chosen = rows[2]
    resid = (long["y"] - long.groupby("subject")["y"].transform("mean")
             - long.groupby("condition", observed=True)["y"].transform("mean") + long["y"].mean()).to_numpy(float)
    normality_assessment(res, resid, "condition × subject", what="residuals")
    ph = _rm_posthoc(res, ctx, long, o["posthoc"]) if chosen["p"] < ctx.alpha or o["posthoc_always"] else []
    res.chart("means", "meanci", "Means by condition",
              {"groups": [mean_ci(ctx.label(c), a_, level) for c, a_ in zip(within, arrays, strict=True)]},
              "Condition", "Mean", f"Condition means with {level:.0%} confidence intervals (between-subject "
                                   "intervals; they do not reflect the paired structure).")
    sig, phrase = sig_phrase(chosen["p"], ctx.alpha)
    res.summary = {"statistic": F, "df": [chosen["df"], chosen["df_error"]], "p": chosen["p"], "effect": peta,
                   "effect_name": "partial η²", "significant": sig}
    res.interpretation = {
        "plain": ("Scores changed significantly across the measurements" if sig
                  else "Scores did not change significantly across the measurements")
                 + f" ({eta_label(peta)} effect).",
        "technical": (f"A repeated-measures ANOVA ({chosen['correction']}) found that the condition effect was {phrase}: "
                      f"F({chosen['df']:.2f}, {chosen['df_error']:.2f}) = {F:.2f}, {fmt_p(chosen['p'], ctx.p_style)}, "
                      f"partial η² = {peta:.3f}, n = {n}." + _posthoc_text(ph, ctx.alpha, "the scores", ctx.decimals)),
    }
    return res


def _long_code(within: list[str], between: str | None = None) -> str:
    ids = ["'subject'"] + ([repr(between)] if between else [])
    return ("df['subject'] = np.arange(len(df))\n"
            f"long = df.melt(id_vars=[{', '.join(ids)}], value_vars={within!r}, var_name='condition', value_name='y')\n")


def code_rm(config, v):
    within = assigned(config, "within")
    return (codegen.prelude(v, within, ["import pingouin as pg"]) + codegen.numeric_ordinal_note(v, within)
            + _long_code(within)
            + "print(pg.rm_anova(long, dv='y', within='condition', subject='subject', correction=True, detailed=True))\n"
            "print(pg.sphericity(long, dv='y', within='condition', subject='subject'))\n"
            f"print(pg.pairwise_tests(long, dv='y', within='condition', subject='subject', "
            f"padjust={_opts(RM, config)['posthoc']!r}))\n")


def run_mixed(ctx: Context, config: dict[str, Any]) -> Result:
    import pingouin as pg

    res = Result(MIXED, config, ctx)
    o = _opts(MIXED, config)
    level = float(o["ci_level"])
    within = assigned(config, "within")
    between = assigned(config, "between")[0]
    df = listwise(ctx.frame([*within, between]), [*within, between], res)
    res.n = len(df)
    long = _long(ctx, df, within, between)
    if long["group"].nunique() < 2:
        raise AnalysisError(f"'{ctx.label(between)}' needs at least two groups with data.")
    if df.shape[0] < long["group"].nunique() + 2:
        raise AnalysisError("Too few cases for a mixed-design ANOVA.")
    a = pg.mixed_anova(long, dv="y", within="condition", subject="subject", between="group", correction=True)
    k = len(within)
    labels = {"group": ctx.label(between), "condition": "Condition", "Interaction": f"Condition × {ctx.label(between)}"}
    rows = []
    for _, r in a.iterrows():
        eps = float(r["eps"]) if "eps" in r and pd.notna(r.get("eps")) else None
        row = {"source": labels.get(str(r["Source"]), str(r["Source"])), "ss": float(r["SS"]), "df1": float(r["DF1"]),
               "df2": float(r["DF2"]), "F": float(r["F"]), "p": float(r["p_unc"]), "partial_eta2": float(r["np2"]),
               "epsilon": eps}
        if eps is not None and k > 2:
            row["p_gg"] = float(stats.f.sf(row["F"], row["df1"] * eps, row["df2"] * eps))
        rows.append(row)
    res.table("main", "main", "Mixed-Design ANOVA",
              [col("source", "Effect", "text"), col("ss", "SS", "num"), col("df1", "df1", "num", "df"),
               col("df2", "df2", "num", "df"), col("F", "F", "stat", "statistic"), col("p", "p", "p", "p"),
               col("epsilon", "GG ε", "num"), col("p_gg", "p (GG)", "p", "p"),
               col("partial_eta2", "Partial η²", "num", "effect")], rows,
              [f"Within-subjects factor: Condition ({k} levels). Between-subjects factor: {ctx.label(between)}. "
               "Greenhouse–Geisser corrected p-values apply to within-subject effects."])
    cells = long.groupby(["group", "condition"], observed=True)["y"]
    res.table("desc", "descriptives", "Cell Descriptives",
              [col("group", ctx.label(between), "text"), col("condition", "Condition", "text"),
               col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"), col("sd", "SD", "num", "sd")],
              [{"group": g, "condition": c, **describe(v.to_numpy(float), level)} for (g, c), v in cells])
    _sphericity(res, ctx, long, k)
    levene(res, [g["y"].to_numpy(float) for _, g in long.groupby("group")])
    series = []
    for g in sorted(long["group"].unique()):
        sub = long[long["group"] == g]
        ms = [mean_ci("", sub.loc[sub["condition"] == c, "y"].to_numpy(float), level) for c in long["condition"].cat.categories]
        series.append({"name": g, "values": [m.get("mean") for m in ms], "lower": [m.get("lower") for m in ms],
                       "upper": [m.get("upper") for m in ms]})
    res.chart("interaction", "interaction", "Means by condition and group",
              {"categories": list(map(str, long["condition"].cat.categories)), "series": series}, "Condition", "Mean",
              f"Condition means for each {ctx.label(between)} group with {level:.0%} CIs.")
    sig_rows = [r for r in rows if (r.get("p_gg") or r["p"]) < ctx.alpha]
    res.summary = {"effects": rows, "significant": bool(sig_rows)}
    res.interpretation = {
        "plain": ("Significant effects: " + ", ".join(r["source"] for r in sig_rows) + "."
                  if sig_rows else "No significant effects of condition, group, or their interaction were found."),
        "technical": "Mixed-design ANOVA: " + "; ".join(
            f"{r['source']}: F({r['df1']:.0f}, {r['df2']:.0f}) = {r['F']:.2f}, "
            f"{fmt_p(r.get('p_gg') or r['p'], ctx.p_style)}, partial η² = {r['partial_eta2']:.3f}" for r in rows) + ".",
    }
    return res


def code_mixed(config, v):
    within, between = assigned(config, "within"), assigned(config, "between")[0]
    return (codegen.prelude(v, [*within, between], ["import pingouin as pg"]) + _long_code(within, between)
            + f"print(pg.mixed_anova(long, dv='y', within='condition', subject='subject', between={between!r}, "
              "correction=True))\n")


# --------------------------------------------------------------------------- ANCOVA


def run_ancova(ctx: Context, config: dict[str, Any]) -> Result:
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    res = Result(ANCOVA, config, ctx)
    o = _opts(ANCOVA, config)
    dv = assigned(config, "dependent")[0]
    factor = assigned(config, "factor")[0]
    covs = assigned(config, "covariates")
    df = listwise(ctx.frame([dv, factor, *covs]), [dv, factor, *covs], res)
    data = pd.DataFrame({"y": ctx.numeric(df, dv), "g": ctx.categorical(df, factor).cat.remove_unused_categories()})
    for c in covs:
        data[_safe(c)] = ctx.numeric(df, c)
        if data[_safe(c)].std() == 0:
            raise AnalysisError(f"Covariate '{ctx.label(c)}' is constant.")
    if len(data["g"].cat.categories) < 2:
        raise AnalysisError(f"'{ctx.label(factor)}' needs at least two groups with data.")
    res.n = len(data)
    cov_terms = " + ".join(_safe(c) for c in covs)
    model = smf.ols(f"y ~ C(g, Sum) + {cov_terms}", data=data).fit()
    table = anova_lm(model, typ=3)
    ss_res = float(table.loc["Residual", "sum_sq"])
    names = {"C(g, Sum)": ctx.label(factor), **{_safe(c): ctx.label(c) for c in covs}}
    rows = []
    for src, r in table.iterrows():
        if src == "Intercept":
            continue
        ss, dfv = float(r["sum_sq"]), float(r["df"])
        row = {"source": names.get(src, "Residuals"), "ss": ss, "df": dfv, "ms": ss / dfv}
        if src != "Residual":
            row.update(F=float(r["F"]), p=float(r["PR(>F)"]), partial_eta2=ss / (ss + ss_res))
        rows.append(row)
    res.table("main", "main", f"ANCOVA: {ctx.label(dv)}", ANOVA_COLS + [col("partial_eta2", "Partial η²", "num", "effect")],
              rows, ["Type III sums of squares with sum-to-zero contrasts."])
    # Adjusted (estimated marginal) means at the covariate means.
    adj_rows = []
    for lv in data["g"].cat.categories:
        newx = pd.DataFrame({"g": pd.Categorical([lv], categories=data["g"].cat.categories),
                             **{_safe(c): [data[_safe(c)].mean()] for c in covs}})
        pred = model.get_prediction(newx).summary_frame(alpha=1 - float(o["ci_level"]))
        adj_rows.append({"group": str(lv), "n": int((data["g"] == lv).sum()),
                         "mean": float(data.loc[data["g"] == lv, "y"].mean()), "adj_mean": float(pred["mean"].iloc[0]),
                         "se": float(pred["mean_se"].iloc[0]), "ci_lower": float(pred["mean_ci_lower"].iloc[0]),
                         "ci_upper": float(pred["mean_ci_upper"].iloc[0])})
    res.table("desc", "descriptives", "Observed and Adjusted Means",
              [col("group", ctx.label(factor), "text"), col("n", "N", "int", "n"), col("mean", "Observed mean", "num", "mean"),
               col("adj_mean", "Adjusted mean", "num", "mean"), col("se", "SE", "num", "se"),
               col("ci_lower", "CI lower", "num", "ci"), col("ci_upper", "CI upper", "num", "ci")], adj_rows,
              ["Adjusted means are evaluated at the mean of each covariate."])
    # Homogeneity of regression slopes
    inter = smf.ols(f"y ~ C(g, Sum) * ({cov_terms})", data=data).fit()
    t2 = anova_lm(inter, typ=3)
    slope_rows = [r for s, r in t2.iterrows() if ":" in str(s)]
    if slope_rows:
        p_min = min(float(r["PR(>F)"]) for r in slope_rows)
        ok = p_min >= ctx.alpha
        res.assumption("Homogeneity of regression slopes", "ok" if ok else "violated",
                       f"Factor × covariate interaction {fmt_p(p_min, ctx.p_style)}. "
                       + ("The covariate relates to the outcome similarly in every group." if ok else
                          "The covariate's slope differs between groups, so ANCOVA's adjusted means can be misleading."),
                       p=p_min)
    levene(res, [data.loc[data["g"] == lv, "y"].to_numpy(float) - model.fittedvalues[data["g"] == lv].to_numpy(float)
                 for lv in data["g"].cat.categories])
    normality_assessment(res, model.resid.to_numpy(float), ctx.label(dv), what="residuals")
    res.assumption("Covariate measured independently of the factor", "info",
                   "Covariates should be measured before treatment or be unaffected by group membership.")
    res.chart("adjusted", "meanci", f"Adjusted means of {ctx.label(dv)}",
              {"groups": [{"name": r["group"], "mean": r["adj_mean"], "lower": r["ci_lower"], "upper": r["ci_upper"],
                           "n": r["n"]} for r in adj_rows]}, ctx.label(factor), f"Adjusted {ctx.label(dv)}",
              "Estimated marginal means with confidence intervals, adjusted for the covariate(s).")
    main = rows[0]
    sig, phrase = sig_phrase(main["p"], ctx.alpha)
    res.summary = {"statistic": main["F"], "df": [main["df"], model.df_resid], "p": main["p"],
                   "effect": main["partial_eta2"], "effect_name": "partial η²", "significant": sig}
    covtxt = ", ".join(ctx.label(c) for c in covs)
    res.interpretation = {
        "plain": (f"After adjusting for {covtxt}, the average {ctx.label(dv)} "
                  + ("differed significantly" if sig else "did not differ significantly")
                  + f" between {ctx.label(factor)} groups."),
        "technical": (f"An ANCOVA on {ctx.label(dv)} with {ctx.label(factor)} as the factor and {covtxt} as "
                      f"covariate(s): F({main['df']:.0f}, {model.df_resid:.0f}) = {main['F']:.2f}, "
                      f"{fmt_p(main['p'], ctx.p_style)}, partial η² = {main['partial_eta2']:.3f}; {phrase}."),
    }
    return res


def code_ancova(config, v):
    dv, factor, covs = assigned(config, "dependent")[0], assigned(config, "factor")[0], assigned(config, "covariates")
    return (codegen.prelude(v, [dv, factor, *covs], ["import statsmodels.formula.api as smf",
                                                      "from statsmodels.stats.anova import anova_lm"])
            + f"model = smf.ols(\"Q({dv!r}) ~ C(Q({factor!r}), Sum) + "
            + " + ".join(f"Q({c!r})" for c in covs) + "\", data=df).fit()\nprint(anova_lm(model, typ=3))\n")


CI = Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)
ALWAYS = Option("posthoc_always", "Run post hoc tests even if the overall test is not significant", "bool", False,
                advanced=True)
DV = Role("dependent", "Dependent variable", "The numeric outcome.", SCALE_LEVELS, plain="What are you comparing?")

ONEWAY = register(AnalysisSpec(
    id="one_way_anova", name="One-Way ANOVA", plain_name="Compare the average scores of three or more groups",
    category="anova",
    description="Tests whether the mean of a numeric outcome differs across the groups of one factor.",
    when_to_use="One numeric outcome and one grouping variable with two or more independent groups.",
    roles=[DV, Role("factor", "Factor", "The grouping variable.", CATEGORICAL_LEVELS, plain="Which groups?")],
    options=[Option("posthoc", "Post hoc test", "select", "auto",
                    [{"value": "auto", "label": "Automatic (Tukey, or Games–Howell if variances differ)"},
                     *POSTHOC_CHOICES]), ALWAYS, CI],
    run=run_oneway, code=code_oneway,
    assumptions=["Independent observations.", "Residuals approximately normal.", "Equal variances across groups."],
    method="Classical F = MS between / MS within. Effect sizes η² and ω². Tukey HSD via scipy.stats.tukey_hsd "
           "(Tukey–Kramer for unequal n); Games–Howell via pingouin.",
    references=["Fisher, R. A. (1925). Statistical Methods for Research Workers.",
                "Games, P. A., & Howell, J. F. (1976). J. Educational Statistics, 1, 113–125."],
    limitations=["A significant F shows that at least one mean differs, not which ones; see the post hoc table."],
))
WELCH = register(AnalysisSpec(
    id="welch_anova", name="Welch's ANOVA", plain_name="Compare group averages when spreads differ",
    category="anova",
    description="One-way comparison of means that does not assume equal variances.",
    when_to_use="Like one-way ANOVA, when group variances or sizes differ noticeably.",
    roles=[DV, Role("factor", "Factor", "The grouping variable.", CATEGORICAL_LEVELS, plain="Which groups?")],
    options=[Option("posthoc", "Post hoc test", "select", "games_howell", POSTHOC_CHOICES), ALWAYS, CI],
    run=run_welch, code=code_welch,
    assumptions=["Independent observations.", "Approximately normal outcome within groups."],
    method="Welch (1951) F test with adjusted denominator df (pingouin.welch_anova); Games–Howell post hoc.",
    references=["Welch, B. L. (1951). Biometrika, 38, 330–336."],
))
FACT = register(AnalysisSpec(
    id="factorial_anova", name="Factorial (Two-Way) ANOVA",
    plain_name="Compare averages across two grouping factors",
    category="anova",
    description="Tests main effects of two or more factors and their interaction on a numeric outcome.",
    when_to_use="One numeric outcome and two (or three) independent categorical factors.",
    roles=[DV, Role("factors", "Factors", "Two or three categorical factors (between-subjects).", CATEGORICAL_LEVELS,
                    2, 3, plain="Which grouping variables?")],
    options=[Option("interaction", "Include interaction", "bool", True),
             Option("ss_type", "Sums of squares", "select", "3",
                    [{"value": "3", "label": "Type III (SPSS default)"}, {"value": "2", "label": "Type II"}],
                    advanced=True), CI],
    run=run_factorial, code=code_factorial,
    assumptions=["Independent observations.", "Residuals approximately normal.", "Equal variances across cells."],
    method="OLS linear model with sum-to-zero (effect) coding; ANOVA table via statsmodels anova_lm.",
    limitations=["Main effects are hard to interpret when the interaction is significant."],
))
RM = register(AnalysisSpec(
    id="rm_anova", name="Repeated-Measures ANOVA", plain_name="Compare three or more measurements of the same people",
    category="anova",
    description="Tests whether means differ across conditions measured on the same cases, accounting for "
                "within-subject dependence.",
    when_to_use="Each row is one participant with a column for each time point or condition.",
    roles=[Role("within", "Repeated measurements", "Two or more columns measured on the same cases (wide format).",
                SCALE_LEVELS, 2, None, plain="Which measurements?")],
    options=[Option("posthoc", "Pairwise comparisons", "select", "holm",
                    [{"value": "holm", "label": "Holm"}, {"value": "bonferroni", "label": "Bonferroni"},
                     {"value": "none", "label": "None"}]), ALWAYS, CI],
    run=run_rm, code=code_rm,
    assumptions=["Sphericity (equal variances of all pairwise differences), tested with Mauchly's test.",
                 "Approximately normal residuals."],
    method="Univariate repeated-measures ANOVA (pingouin.rm_anova) with Greenhouse–Geisser and Huynh–Feldt "
           "corrections; Mauchly's test of sphericity.",
    missing_data="Only cases with all repeated measurements are used.",
    references=["Greenhouse, S. W., & Geisser, S. (1959). Psychometrika, 24, 95–112."],
))
MIXED = register(AnalysisSpec(
    id="mixed_anova", name="Mixed-Design ANOVA", plain_name="Compare changes over time between groups",
    category="anova",
    description="One within-subjects factor (repeated measurements) and one between-subjects factor.",
    when_to_use="Pre/post (or more) measurements for participants who belong to different groups.",
    roles=[Role("within", "Repeated measurements", "Columns measured on the same cases.", SCALE_LEVELS, 2, None),
           Role("between", "Between-subjects factor", "Group membership.", CATEGORICAL_LEVELS)],
    options=[CI],
    run=run_mixed, code=code_mixed,
    assumptions=["Sphericity for the within factor.", "Equal variances across groups.", "Normal residuals."],
    method="pingouin.mixed_anova (one within, one between factor) with Greenhouse–Geisser correction.",
    missing_data="Only cases with all repeated measurements and a group are used.",
))
ANCOVA = register(AnalysisSpec(
    id="ancova", name="ANCOVA", plain_name="Compare group averages while adjusting for another variable",
    category="anova",
    description="Compares group means on an outcome after statistically controlling for one or more covariates.",
    when_to_use="E.g. compare post-test scores between groups while adjusting for pre-test scores.",
    roles=[DV, Role("factor", "Factor", "The grouping variable.", CATEGORICAL_LEVELS),
           Role("covariates", "Covariates", "Numeric variables to adjust for.", NUMERIC_LEVELS | {"ordinal"}, 1, 5)],
    options=[CI],
    run=run_ancova, code=code_ancova,
    assumptions=["Linear covariate–outcome relationship.", "Homogeneity of regression slopes.",
                 "Equal residual variances.", "Normal residuals.", "Covariate not affected by the factor."],
    method="OLS with sum-to-zero coding and Type III SS; adjusted means at covariate means; slopes homogeneity "
           "tested via factor × covariate interaction.",
))
