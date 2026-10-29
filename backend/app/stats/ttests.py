"""t-tests: one-sample, independent samples (Student and Welch) and paired samples."""

from __future__ import annotations

import math
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
    fmt_ci,
    fmt_num,
    fmt_p,
    listwise,
    register,
    require_n,
    sig_phrase,
)
from .common import box_stats, cohen_label, describe, levene, mean_ci, normality_assessment, qq_data

ALTERNATIVES = [{"value": "two-sided", "label": "Two-sided (groups differ)"},
                {"value": "greater", "label": "One-sided: first > second"},
                {"value": "less", "label": "One-sided: first < second"}]
CI_OPT = Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)
ALT_OPT = Option("alternative", "Alternative hypothesis", "select", "two-sided", ALTERNATIVES, advanced=True)


def _opts(spec: AnalysisSpec, config: dict[str, Any]) -> dict[str, Any]:
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def _t_ci(diff: float, se: float, df: float, level: float, alternative: str) -> tuple[float, float]:
    if alternative == "two-sided":
        t = stats.t.ppf(0.5 + level / 2, df)
        return diff - t * se, diff + t * se
    t = stats.t.ppf(level, df)
    return (diff - t * se, math.inf) if alternative == "greater" else (-math.inf, diff + t * se)


def _d_ci(d: float, n1: int, n2: int | None, level: float) -> tuple[float, float]:
    """Approximate (normal-theory) CI for Cohen's d (Hedges & Olkin, 1985)."""
    z = stats.norm.ppf(0.5 + level / 2)
    if n2 is None:
        se = math.sqrt(1 / n1 + d * d / (2 * n1))
    else:
        se = math.sqrt((n1 + n2) / (n1 * n2) + d * d / (2 * (n1 + n2)))
    return d - z * se, d + z * se


def _alt_text(alt: str, a: str, b: str) -> str:
    return {"two-sided": "", "greater": f" (one-sided: {a} > {b})", "less": f" (one-sided: {a} < {b})"}[alt]


# --------------------------------------------------------------------------- one-sample


def run_one_sample(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(ONE, config, ctx)
    o = _opts(ONE, config)
    var = assigned(config, "variable")[0]
    mu = float(o["test_value"])
    df = listwise(ctx.frame([var]), [var], res)
    x = ctx.numeric(df, var).to_numpy(float)
    n = len(x)
    require_n(n, 2, ctx.label(var))
    if np.ptp(x) == 0:
        raise AnalysisError(f"'{ctx.label(var)}' has the same value for every case, so a t-test is not possible.")
    res.n = n
    level = float(o["ci_level"])
    d = describe(x, level)
    t, p = stats.ttest_1samp(x, mu, alternative=o["alternative"])
    dof = n - 1
    diff = d["mean"] - mu
    lo, hi = _t_ci(diff, d["se"], dof, level, o["alternative"])
    cohen = diff / d["sd"]
    dlo, dhi = _d_ci(cohen, n, None, level)
    res.table("desc", "descriptives", "Descriptive Statistics",
              [col("variable", "Variable", "text"), col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"),
               col("sd", "SD", "num", "sd"), col("se", "SE", "num", "se")],
              [{"variable": ctx.label(var), **d}])
    res.table("main", "main", "One-Sample t-Test",
              [col("variable", "Variable", "text"), col("test_value", "Test value", "num"),
               col("t", "t", "stat", "statistic"), col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("mean_diff", "Mean difference", "num", "ci"), col("ci_lower", f"{level:.0%} CI lower", "num", "ci"),
               col("ci_upper", f"{level:.0%} CI upper", "num", "ci"), col("d", "Cohen's d", "num", "effect"),
               col("d_lower", "d CI lower", "num", "effect"), col("d_upper", "d CI upper", "num", "effect")],
              [{"variable": ctx.label(var), "test_value": mu, "t": t, "df": dof, "p": p, "mean_diff": diff,
                "ci_lower": lo, "ci_upper": hi, "d": cohen, "d_lower": dlo, "d_upper": dhi}],
              [f"Alternative hypothesis: {o['alternative']}. Cohen's d CI uses a normal approximation."])
    normality_assessment(res, x, ctx.label(var))
    res.chart("qq", "qq", f"Normal Q–Q plot of {ctx.label(var)}", qq_data(x), "Theoretical quantiles",
              "Observed values", "Points close to the line indicate approximately normal data.")
    sig, phrase = sig_phrase(p, ctx.alpha)
    dd = ctx.decimals
    res.summary = {"statistic": t, "df": dof, "p": p, "effect": cohen, "effect_name": "d", "significant": sig}
    res.interpretation = {
        "plain": (f"The average {ctx.label(var)} ({fmt_num(d['mean'], dd)}) was "
                  + ("" if sig else "not ")
                  + f"significantly {'different from' if o['alternative'] == 'two-sided' else ('higher than' if o['alternative'] == 'greater' else 'lower than')} "
                  f"{fmt_num(mu, dd)}. The difference of {fmt_num(diff, dd)} is a {cohen_label(cohen)} effect."),
        "technical": (f"A one-sample t-test compared {ctx.label(var)} (M = {fmt_num(d['mean'], dd)}, "
                      f"SD = {fmt_num(d['sd'], dd)}) with {fmt_num(mu, dd)}: t({dof}) = {t:.2f}, "
                      f"{fmt_p(p, ctx.p_style)}, mean difference = {fmt_num(diff, dd)}, {level:.0%} CI "
                      f"{fmt_ci(lo, hi, dd)}, d = {cohen:.2f}. The result is {phrase} at α = {ctx.alpha:g}."),
    }
    return res


def code_one_sample(config: dict[str, Any], v: dict) -> str:
    o = _opts(ONE, config)
    var = assigned(config, "variable")[0]
    return (codegen.prelude(v, [var], ["from scipy import stats"]) + codegen.numeric_ordinal_note(v, [var])
            + f"x = df[{var!r}].astype(float)\n"
            f"res = stats.ttest_1samp(x, {float(o['test_value'])!r}, alternative={o['alternative']!r})\n"
            f"d = (x.mean() - {float(o['test_value'])!r}) / x.std(ddof=1)  # Cohen's d\n"
            "print(res, 'df =', len(x) - 1, 'd =', d)\n")


# --------------------------------------------------------------------------- independent


def two_groups(ctx: Context, df, group: str, o: dict[str, Any]):
    g = ctx.categorical(df, group)
    levels = [str(c) for c in g.cat.categories if (g == c).any()]
    a, b = o.get("group_a"), o.get("group_b")
    if a or b:
        if a not in levels or b not in levels or a == b:
            raise AnalysisError(f"Choose two different groups of '{ctx.label(group)}' to compare.")
    else:
        if len(levels) != 2:
            raise AnalysisError(
                f"'{ctx.label(group)}' has {len(levels)} groups ({', '.join(levels[:6])}). A t-test compares exactly "
                "two groups.", suggestion="Choose the two groups to compare, or use one-way ANOVA for three or more groups.")
        a, b = levels
    return g, a, b


def run_independent(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(IND, config, ctx)
    o = _opts(IND, config)
    dv = assigned(config, "dependent")[0]
    group = assigned(config, "group")[0]
    df = listwise(ctx.frame([dv, group]), [dv, group], res)
    g, a, b = two_groups(ctx, df, group, o)
    y = ctx.numeric(df, dv)
    x1 = y[g == a].to_numpy(float)
    x2 = y[g == b].to_numpy(float)
    if o.get("group_a"):
        dropped = len(df) - len(x1) - len(x2)
        if dropped:
            res.notes.append(f"{dropped:,} cases in other groups of {ctx.label(group)} were not included.")
    require_n(len(x1), 2, f"Group '{a}'", "Each group needs at least two observations.")
    require_n(len(x2), 2, f"Group '{b}'", "Each group needs at least two observations.")
    if np.ptp(np.concatenate([x1, x2])) == 0:
        raise AnalysisError(f"'{ctx.label(dv)}' has the same value for every case; there is nothing to compare.")
    n1, n2 = len(x1), len(x2)
    res.n = n1 + n2
    level = float(o["ci_level"])
    alt = o["alternative"]
    d1, d2 = describe(x1, level), describe(x2, level)
    res.table("desc", "descriptives", "Group Descriptives",
              [col("group", ctx.label(group), "text"), col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"),
               col("sd", "SD", "num", "sd"), col("se", "SE", "num", "se"), col("median", "Median", "num", "median")],
              [{"group": a, **d1}, {"group": b, **d2}])

    sp = math.sqrt(((n1 - 1) * d1["sd"] ** 2 + (n2 - 1) * d2["sd"] ** 2) / (n1 + n2 - 2))
    diff = d1["mean"] - d2["mean"]
    cohen = diff / sp if sp > 0 else math.nan
    hedges = cohen * (1 - 3 / (4 * (n1 + n2) - 9))
    dlo, dhi = _d_ci(cohen, n1, n2, level)
    rows = []
    tests = {"student": ["student"], "welch": ["welch"], "both": ["student", "welch"]}[o["test"]]
    for kind in tests:
        welch = kind == "welch"
        r = stats.ttest_ind(x1, x2, equal_var=not welch, alternative=alt)
        if welch:
            v1, v2 = d1["sd"] ** 2 / n1, d2["sd"] ** 2 / n2
            se = math.sqrt(v1 + v2)
            dof = (v1 + v2) ** 2 / (v1**2 / (n1 - 1) + v2**2 / (n2 - 1))
        else:
            se = sp * math.sqrt(1 / n1 + 1 / n2)
            dof = n1 + n2 - 2
        lo, hi = _t_ci(diff, se, dof, level, alt)
        rows.append({"test": "Welch's t-test" if welch else "Student's t-test", "t": r.statistic, "df": dof,
                     "p": r.pvalue, "mean_diff": diff, "se_diff": se, "ci_lower": lo, "ci_upper": hi,
                     "d": cohen, "hedges_g": hedges, "d_lower": dlo, "d_upper": dhi})
    res.table("main", "main", "Independent-Samples t-Test",
              [col("test", "Test", "text"), col("t", "t", "stat", "statistic"), col("df", "df", "num", "df"),
               col("p", "p", "p", "p"), col("mean_diff", "Mean difference", "num", "ci"),
               col("se_diff", "SE difference", "num", "ci"), col("ci_lower", f"{level:.0%} CI lower", "num", "ci"),
               col("ci_upper", f"{level:.0%} CI upper", "num", "ci"), col("d", "Cohen's d", "num", "effect"),
               col("hedges_g", "Hedges' g", "num", "effect"), col("d_lower", "d CI lower", "num", "effect"),
               col("d_upper", "d CI upper", "num", "effect")],
              rows,
              [f"Mean difference = {a} − {b}.{_alt_text(alt, a, b)}",
               "Welch's test does not assume equal variances; Student's test does. Cohen's d uses the pooled SD; its "
               "CI is a normal approximation."])

    lev = levene(res, [x1, x2])
    for name, arr in ((a, x1), (b, x2)):
        normality_assessment(res, arr, f"{ctx.label(dv)}, {name}")
    res.assumption("Independence", "info", "Each case must belong to only one group and cases must not influence "
                   "each other. This is a design question that the data cannot verify.")
    if lev and not lev["equal"] and o["test"] == "student":
        res.warn("Levene's test indicates unequal variances. Welch's t-test is more appropriate than Student's; "
                 "it is not substituted automatically.")
    if any(x["status"] == "violated" and x["name"].startswith("Normality") for x in res.assumptions) and min(n1, n2) < 30:
        res.warn("Normality may be violated in small groups. Consider the Mann–Whitney U test as a check.")

    res.chart("box", "box", f"{ctx.label(dv)} by {ctx.label(group)}",
              {"groups": [box_stats(a, x1), box_stats(b, x2)]}, ctx.label(group), ctx.label(dv),
              "Box plots: median, quartiles, whiskers to 1.5 × IQR, outliers as points.")
    res.chart("means", "meanci", f"Mean {ctx.label(dv)} by {ctx.label(group)}",
              {"groups": [mean_ci(a, x1, level), mean_ci(b, x2, level)]}, ctx.label(group), ctx.label(dv),
              f"Group means with {level:.0%} confidence intervals.")

    main = rows[-1] if o["test"] != "student" else rows[0]
    sig, phrase = sig_phrase(main["p"], ctx.alpha)
    dd = ctx.decimals
    higher = a if diff > 0 else b
    res.summary = {"statistic": main["t"], "df": main["df"], "p": main["p"], "effect": cohen, "effect_name": "d",
                   "significant": sig, "test": main["test"]}
    plain = (f"{higher} had a {'higher' if diff != 0 else 'similar'} average {ctx.label(dv)} "
             f"({fmt_num(max(d1['mean'], d2['mean']), dd)} vs {fmt_num(min(d1['mean'], d2['mean']), dd)}). ")
    plain += (f"This difference is statistically significant, and its size is {cohen_label(cohen)} (d = {cohen:.2f})."
              if sig else f"This difference is not statistically significant, so the data do not show a reliable "
                          f"difference between the groups (d = {cohen:.2f}).")
    res.interpretation = {
        "plain": plain,
        "technical": (f"An independent-samples {main['test']} compared {ctx.label(dv)} between {a} (M = "
                      f"{fmt_num(d1['mean'], dd)}, SD = {fmt_num(d1['sd'], dd)}, n = {n1}) and {b} (M = "
                      f"{fmt_num(d2['mean'], dd)}, SD = {fmt_num(d2['sd'], dd)}, n = {n2}): t({main['df']:.2f}) = "
                      f"{main['t']:.2f}, {fmt_p(main['p'], ctx.p_style)}, mean difference = {fmt_num(diff, dd)}, "
                      f"{level:.0%} CI {fmt_ci(main['ci_lower'], main['ci_upper'], dd)}, d = {cohen:.2f}. "
                      f"The difference is {phrase} at α = {ctx.alpha:g}."),
    }
    return res


def code_independent(config: dict[str, Any], v: dict) -> str:
    o = _opts(IND, config)
    dv, group = assigned(config, "dependent")[0], assigned(config, "group")[0]
    a, b = o.get("group_a") or "<group A>", o.get("group_b") or "<group B>"
    equal = {"student": "True", "welch": "False", "both": "False  # also run with True for Student's test"}[o["test"]]
    return (codegen.prelude(v, [dv, group], ["from scipy import stats"]) + codegen.numeric_ordinal_note(v, [dv])
            + f"x1 = df.loc[df[{group!r}].astype(str) == {a!r}, {dv!r}].astype(float)\n"
            f"x2 = df.loc[df[{group!r}].astype(str) == {b!r}, {dv!r}].astype(float)\n"
            f"print(stats.ttest_ind(x1, x2, equal_var={equal}, alternative={o['alternative']!r}))\n"
            "print(stats.levene(x1, x2, center='median'))\n"
            "sp = np.sqrt(((len(x1)-1)*x1.var(ddof=1) + (len(x2)-1)*x2.var(ddof=1)) / (len(x1)+len(x2)-2))\n"
            "print('Cohen d =', (x1.mean() - x2.mean()) / sp)\n")


# --------------------------------------------------------------------------- paired


def run_paired(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(PAIRED, config, ctx)
    o = _opts(PAIRED, config)
    v1, v2 = assigned(config, "first")[0], assigned(config, "second")[0]
    df = listwise(ctx.frame([v1, v2]), [v1, v2], res)
    x1 = ctx.numeric(df, v1).to_numpy(float)
    x2 = ctx.numeric(df, v2).to_numpy(float)
    n = len(x1)
    require_n(n, 2, "The paired data", "Each row must contain both measurements.")
    diff = x1 - x2
    if np.ptp(diff) == 0:
        raise AnalysisError("Every paired difference is identical, so the t statistic is undefined.",
                            suggestion="Check that the two variables are not copies of each other.")
    res.n = n
    level = float(o["ci_level"])
    alt = o["alternative"]
    d1, d2, dd_ = describe(x1, level), describe(x2, level), describe(diff, level)
    r = stats.ttest_rel(x1, x2, alternative=alt)
    lo, hi = _t_ci(dd_["mean"], dd_["se"], n - 1, level, alt)
    dz = dd_["mean"] / dd_["sd"]
    dlo, dhi = _d_ci(dz, n, None, level)
    corr = float(np.corrcoef(x1, x2)[0, 1]) if np.ptp(x1) > 0 and np.ptp(x2) > 0 else math.nan
    res.table("desc", "descriptives", "Paired Descriptives",
              [col("variable", "Measurement", "text"), col("n", "N", "int", "n"), col("mean", "Mean", "num", "mean"),
               col("sd", "SD", "num", "sd"), col("se", "SE", "num", "se")],
              [{"variable": ctx.label(v1), **d1}, {"variable": ctx.label(v2), **d2}],
              [f"Correlation between the measurements: r = {corr:.2f}."])
    res.table("main", "main", "Paired-Samples t-Test",
              [col("pair", "Pair", "text"), col("mean_diff", "Mean difference", "num", "ci"),
               col("sd_diff", "SD difference", "num", "ci"), col("t", "t", "stat", "statistic"),
               col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("ci_lower", f"{level:.0%} CI lower", "num", "ci"), col("ci_upper", f"{level:.0%} CI upper", "num", "ci"),
               col("dz", "Cohen's dz", "num", "effect"), col("d_lower", "dz CI lower", "num", "effect"),
               col("d_upper", "dz CI upper", "num", "effect")],
              [{"pair": f"{ctx.label(v1)} − {ctx.label(v2)}", "mean_diff": dd_["mean"], "sd_diff": dd_["sd"],
                "t": r.statistic, "df": n - 1, "p": r.pvalue, "ci_lower": lo, "ci_upper": hi, "dz": dz,
                "d_lower": dlo, "d_upper": dhi}],
              ["Cohen's dz = mean difference / SD of differences; CI is a normal approximation."])
    normality_assessment(res, diff, f"{ctx.label(v1)} − {ctx.label(v2)}", what="differences")
    res.assumption("Paired design", "info", "Each row must hold two measurements of the same participant or unit. "
                   "The data cannot confirm this; it depends on how the study was designed.")
    if any(x["status"] == "violated" for x in res.assumptions) and n < 30:
        res.warn("The differences may not be normal in this small sample. Consider the Wilcoxon signed-rank test.")
    res.chart("means", "meanci", "Means of the paired measurements",
              {"groups": [mean_ci(ctx.label(v1), x1, level), mean_ci(ctx.label(v2), x2, level)]}, "Measurement",
              "Mean", f"Means with {level:.0%} confidence intervals. Intervals of paired means do not test the "
                      "difference directly.")
    res.chart("qq", "qq", "Normal Q–Q plot of differences", qq_data(diff), "Theoretical quantiles",
              "Observed differences", "Checks the normality of the paired differences.")
    sig, phrase = sig_phrase(r.pvalue, ctx.alpha)
    dd = ctx.decimals
    res.summary = {"statistic": r.statistic, "df": n - 1, "p": r.pvalue, "effect": dz, "effect_name": "dz",
                   "significant": sig}
    direction = "higher" if dd_["mean"] > 0 else "lower"
    res.interpretation = {
        "plain": (f"On average, {ctx.label(v1)} was {fmt_num(abs(dd_['mean']), dd)} points {direction} than "
                  f"{ctx.label(v2)}. " + ("This change is statistically significant" if sig else
                                          "This change is not statistically significant")
                  + f" (effect size: {cohen_label(dz)})."),
        "technical": (f"A paired-samples t-test compared {ctx.label(v1)} (M = {fmt_num(d1['mean'], dd)}, SD = "
                      f"{fmt_num(d1['sd'], dd)}) and {ctx.label(v2)} (M = {fmt_num(d2['mean'], dd)}, SD = "
                      f"{fmt_num(d2['sd'], dd)}) for n = {n} pairs: t({n - 1}) = {r.statistic:.2f}, "
                      f"{fmt_p(r.pvalue, ctx.p_style)}, mean difference = {fmt_num(dd_['mean'], dd)}, {level:.0%} CI "
                      f"{fmt_ci(lo, hi, dd)}, dz = {dz:.2f}. The difference is {phrase} at α = {ctx.alpha:g}."),
    }
    return res


def code_paired(config: dict[str, Any], v: dict) -> str:
    o = _opts(PAIRED, config)
    v1, v2 = assigned(config, "first")[0], assigned(config, "second")[0]
    return (codegen.prelude(v, [v1, v2], ["from scipy import stats"]) + codegen.numeric_ordinal_note(v, [v1, v2])
            + f"res = stats.ttest_rel(df[{v1!r}], df[{v2!r}], alternative={o['alternative']!r})\n"
            f"diff = df[{v1!r}] - df[{v2!r}]\nprint(res, 'dz =', diff.mean() / diff.std(ddof=1))\n")


ONE = register(AnalysisSpec(
    id="one_sample_t", name="One-Sample t-Test", plain_name="Compare an average with a fixed value",
    category="compare",
    description="Tests whether the mean of one variable differs from a reference value (e.g. a scale midpoint).",
    when_to_use="One numeric variable and a meaningful reference value such as a norm or the neutral point 3.",
    roles=[Role("variable", "Test variable", "The numeric variable whose mean is tested.", SCALE_LEVELS)],
    options=[Option("test_value", "Test value", "number", 0.0, help="The value the mean is compared with."),
             ALT_OPT, CI_OPT],
    run=run_one_sample, code=code_one_sample,
    assumptions=["Observations are independent.", "The variable is approximately normal, or the sample is large."],
    method="t = (M − μ0) / (SD/√n) with n − 1 degrees of freedom (scipy.stats.ttest_1samp).",
    references=["Student (1908). The probable error of a mean. Biometrika, 6, 1–25."],
))

IND = register(AnalysisSpec(
    id="independent_t", name="Independent-Samples t-Test", plain_name="Compare the average scores of two groups",
    category="compare",
    description="Tests whether two independent groups have different means on a numeric outcome.",
    when_to_use="One numeric outcome and a grouping variable with two groups; each case is in only one group.",
    roles=[Role("dependent", "Test variable", "The numeric outcome being compared.", SCALE_LEVELS,
                plain="What are you comparing?"),
           Role("group", "Grouping variable", "Defines the two independent groups.", CATEGORICAL_LEVELS,
                plain="Which groups?")],
    options=[Option("test", "Test", "select", "welch",
                    [{"value": "welch", "label": "Welch's t-test (does not assume equal variances)"},
                     {"value": "student", "label": "Student's t-test (assumes equal variances)"},
                     {"value": "both", "label": "Report both"}],
                    help="Welch's test is recommended by default because it stays accurate when variances differ."),
             Option("group_a", "First group", "level", None, depends_on="group", advanced=True),
             Option("group_b", "Second group", "level", None, depends_on="group", advanced=True),
             ALT_OPT, CI_OPT],
    run=run_independent, code=code_independent,
    assumptions=["Independent observations; each case belongs to one group.",
                 "The outcome is approximately normal within each group, or groups are reasonably large.",
                 "Student's test additionally assumes equal variances (checked with Levene's test)."],
    method="Student's t uses the pooled variance with n1 + n2 − 2 df; Welch's t uses separate variances with "
           "Welch–Satterthwaite df (scipy.stats.ttest_ind). Levene's test is median-centred (Brown–Forsythe).",
    references=["Welch, B. L. (1947). Biometrika, 34, 28–35.", "Delacre, M., Lakens, D., & Leys, C. (2017). Why "
                "psychologists should by default use Welch's t-test. IRSP, 30(1), 92–101."],
))

PAIRED = register(AnalysisSpec(
    id="paired_t", name="Paired-Samples t-Test", plain_name="Compare two measurements of the same people",
    category="compare",
    description="Tests whether the average change between two related measurements (e.g. pre and post) is zero.",
    when_to_use="Two numeric columns measured on the same participants, e.g. before and after an intervention.",
    roles=[Role("first", "Measurement 1", "First measurement (e.g. pre-test).", SCALE_LEVELS, plain="First measurement"),
           Role("second", "Measurement 2", "Second measurement of the same cases (e.g. post-test).", SCALE_LEVELS,
                plain="Second measurement")],
    options=[ALT_OPT, CI_OPT],
    run=run_paired, code=code_paired,
    assumptions=["Each row holds both measurements of the same unit.",
                 "The paired differences are approximately normal, or the number of pairs is large."],
    method="t = mean difference / (SD of differences / √n), n − 1 df (scipy.stats.ttest_rel).",
    missing_data="Only rows with both measurements are used (complete pairs).",
))
