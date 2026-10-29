"""Group comparisons across one or more measures, with automatic, explained test selection.

``compare_two_groups``: two independent groups (e.g. Formulation 1 vs Formulation 2) on several measures,
one row per measure. ``compare_groups``: three or more independent groups, one omnibus test per measure
plus corrected post hoc comparisons, never uncorrected pairwise tests.

Automatic choice (per measure, always reported with its reason):
- ordinal measure                                   -> rank-based test
- smallest group < 30 and a group clearly non-normal -> rank-based test
- otherwise                                          -> Welch's t (two groups) / one-way or Welch ANOVA (3+)
The user may override the test.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
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
    register,
)
from .common import box_stats, cohen_label, eta_label, mean_ci, p_adjust, r_label


def _opts(spec, config):
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def _non_normal(x: np.ndarray, alpha: float, max_n: int) -> bool:
    if len(x) < 3 or np.ptp(x) == 0 or len(x) > max_n:
        return False
    return bool(stats.shapiro(x).pvalue < alpha)


def _choose(ctx: Context, measure: str, arrays: list[np.ndarray], requested: str, two: bool) -> tuple[str, str]:
    if requested != "auto":
        return requested, "selected by the user"
    if ctx.meta(measure).level == "ordinal":
        return ("mann_whitney" if two else "kruskal"), "the measure is an ordinal rating"
    small = min(len(a) for a in arrays) < 30
    if small and any(_non_normal(a, ctx.alpha, ctx.shapiro_max_n) for a in arrays):
        return ("mann_whitney" if two else "kruskal"), "a group departs from normality and groups are small"
    if two:
        return "welch", "numeric measure; Welch's t-test does not assume equal variances"
    groups = [a for a in arrays if len(a) > 1]
    if len(groups) >= 2 and stats.levene(*groups, center="median").pvalue < ctx.alpha:
        return "welch_anova", "group variances differ (Levene's test)"
    return "anova", "numeric measure with similar group variances"


TEST_NAMES = {"welch": "Welch's t-test", "student": "Student's t-test", "mann_whitney": "Mann–Whitney U",
              "anova": "One-way ANOVA", "welch_anova": "Welch's ANOVA", "kruskal": "Kruskal–Wallis"}


def _groups(ctx: Context, df: pd.DataFrame, group: str, wanted: list[str] | None) -> tuple[pd.Series, list[str]]:
    g = ctx.categorical(df, group)
    levels = [str(c) for c in g.cat.categories if (g == c).any()]
    if wanted:
        missing = [w for w in wanted if w not in levels]
        if missing:
            raise AnalysisError(f"Group(s) {', '.join(missing)} not found in '{ctx.label(group)}'.")
        levels = [lv for lv in levels if lv in wanted]
        levels.sort(key=lambda v: wanted.index(v))
    return g.astype("object").where(g.notna(), None), levels


# --------------------------------------------------------------------------- two groups


def run_two(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(TWO, config, ctx)
    o = _opts(TWO, config)
    group = assigned(config, "group")[0]
    measures = assigned(config, "measures")
    level = float(o["ci_level"])
    df = ctx.frame([group, *measures])
    g, levels = _groups(ctx, df, group, [x for x in (o.get("group_a"), o.get("group_b")) if x] or None)
    if len(levels) < 2:
        raise AnalysisError(f"'{ctx.label(group)}' needs two groups with data.")
    if len(levels) > 2 and not (o.get("group_a") and o.get("group_b")):
        raise AnalysisError(f"'{ctx.label(group)}' has {len(levels)} groups. Choose the two to compare, or compare all "
                            "groups together.", suggestion="Use 'Compare several groups' for three or more groups.")
    a, b = levels[0], levels[1]
    desc_rows, rows, raw_p = [], [], []
    boxes = []
    means_series = {a: {"values": [], "lower": [], "upper": []}, b: {"values": [], "lower": [], "upper": []}}
    excluded_total = 0
    for m in measures:
        y = ctx.numeric(df, m)
        x1 = y[(g == a).to_numpy() & y.notna().to_numpy()].to_numpy(float)
        x2 = y[(g == b).to_numpy() & y.notna().to_numpy()].to_numpy(float)
        excluded_total += int(((g == a) | (g == b)).sum() - len(x1) - len(x2))
        if len(x1) < 2 or len(x2) < 2:
            rows.append({"measure": ctx.label(m), "test": "Not computed", "note": "fewer than 2 values in a group"})
            raw_p.append(math.nan)
            continue
        test, reason = _choose(ctx, m, [x1, x2], o["test"], True)
        n1, n2 = len(x1), len(x2)
        m1, m2 = x1.mean(), x2.mean()
        s1, s2 = x1.std(ddof=1), x2.std(ddof=1)
        row: dict[str, Any] = {"measure": ctx.label(m), "n_a": n1, "mean_a": m1, "sd_a": s1, "n_b": n2, "mean_b": m2,
                               "sd_b": s2, "diff": m1 - m2, "test": TEST_NAMES[test], "reason": reason}
        if np.ptp(np.concatenate([x1, x2])) == 0:
            row.update(test="Not computed", note="no variation")
            rows.append(row)
            raw_p.append(math.nan)
            continue
        if test in ("welch", "student"):
            r = stats.ttest_ind(x1, x2, equal_var=test == "student", alternative=o["alternative"])
            v1, v2 = s1**2 / n1, s2**2 / n2
            if test == "welch":
                se = math.sqrt(v1 + v2)
                dof = (v1 + v2) ** 2 / (v1**2 / (n1 - 1) + v2**2 / (n2 - 1))
            else:
                sp2 = ((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2)
                se, dof = math.sqrt(sp2 * (1 / n1 + 1 / n2)), n1 + n2 - 2
            t = stats.t.ppf(0.5 + level / 2, dof)
            sp = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
            d = (m1 - m2) / sp if sp > 0 else math.nan
            row.update(statistic=r.statistic, stat_name="t", df=dof, p=r.pvalue, ci_lower=m1 - m2 - t * se,
                       ci_upper=m1 - m2 + t * se, effect=d, effect_name="d", effect_label=cohen_label(d))
        else:
            r = stats.mannwhitneyu(x1, x2, alternative=o["alternative"], method="auto")
            rbc = 2 * r.statistic / (n1 * n2) - 1
            row.update(statistic=r.statistic, stat_name="U", p=r.pvalue, effect=rbc, effect_name="r (rank-biserial)",
                       effect_label=r_label(rbc), median_a=float(np.median(x1)), median_b=float(np.median(x2)))
        rows.append(row)
        raw_p.append(row["p"])
        for name, x in ((a, x1), (b, x2)):
            d_ = {"group": name, "measure": ctx.label(m), "n": len(x), "mean": x.mean(), "sd": x.std(ddof=1),
                  "median": float(np.median(x)), "min": float(x.min()), "max": float(x.max())}
            desc_rows.append(d_)
            ci = mean_ci(name, x, level)
            means_series[name]["values"].append(ci["mean"])
            means_series[name]["lower"].append(ci["lower"])
            means_series[name]["upper"].append(ci["upper"])
        if len(boxes) < 6:
            boxes.append((m, [box_stats(a, x1), box_stats(b, x2)]))
    if o["p_adjust"] != "none" and len(measures) > 1:
        adj = p_adjust(raw_p, o["p_adjust"])
        for row, p in zip(rows, adj, strict=True):
            if "p" in row:
                row["p_unadjusted"], row["p"] = row["p"], p
    res.n = int(((g == a) | (g == b)).sum())
    res.missing = {"total_rows": len(df), "used": res.n, "excluded": excluded_total, "method": "per measure"}
    if excluded_total:
        res.notes.append(f"Missing values were excluded separately for each measure ({excluded_total:,} values in total).")

    res.table("desc", "descriptives", f"Descriptive Statistics by {ctx.label(group)}",
              [col("measure", "Measure", "text"), col("group", ctx.label(group), "text"), col("n", "N", "int", "n"),
               col("mean", "Mean", "num", "mean"), col("sd", "SD", "num", "sd"), col("median", "Median", "num", "median"),
               col("min", "Min", "num", "min"), col("max", "Max", "num", "max")], desc_rows)
    cols = [col("measure", "Measure", "text"), col("mean_a", f"Mean ({a})", "num", "mean"),
            col("sd_a", f"SD ({a})", "num", "sd"), col("mean_b", f"Mean ({b})", "num", "mean"),
            col("sd_b", f"SD ({b})", "num", "sd"), col("diff", "Mean difference", "num", "mean"),
            col("test", "Test", "text"), col("statistic", "Statistic", "stat", "statistic"),
            col("df", "df", "num", "df"), col("p", "p", "p", "p")]
    if any("p_unadjusted" in r for r in rows):
        cols.insert(-1, col("p_unadjusted", "p (unadjusted)", "p", "p"))
    cols += [col("ci_lower", f"{level:.0%} CI lower", "num", "ci"), col("ci_upper", f"{level:.0%} CI upper", "num", "ci"),
             col("effect", "Effect size", "num", "effect"), col("effect_label", "Magnitude", "text", "effect")]
    notes = [f"Mean difference = {a} − {b}. Effect size: Cohen's d for t-tests, rank-biserial r for Mann–Whitney U."]
    reasons = sorted({f"{r['test']}: {r['reason']}" for r in rows if r.get("reason")})
    notes.append("Test selection — " + "; ".join(reasons) + ".")
    if o["p_adjust"] != "none" and len(measures) > 1:
        notes.append(f"p-values adjusted for {len(measures)} measures ({o['p_adjust'].title()}).")
    elif len(measures) > 1:
        notes.append(f"p-values are not adjusted for testing {len(measures)} measures; consider the Holm option.")
    res.table("main", "main", f"Comparison of {a} and {b}", cols, rows, notes)

    res.assumption("Independent groups", "info", f"Each case should belong to only one {ctx.label(group)} group. If the "
                   "same participants evaluated both, use a paired comparison instead.")
    nonnormal = [r["measure"] for r in rows if r.get("reason", "").startswith("a group departs")]
    if nonnormal:
        res.assumption("Normality", "warning", "Rank-based tests were used for " + ", ".join(nonnormal) + " because a "
                       "group departs from normality in a small sample.")
    else:
        res.assumption("Normality", "ok", "No measure showed a consequential departure from normality for its test.")

    res.chart("means", "means", f"Mean scores by {ctx.label(group)}",
              {"categories": [r["measure"] for r in rows if "p" in r],
               "series": [{"name": k, **v} for k, v in means_series.items()]},
              "Measure", "Mean", f"Means with {level:.0%} confidence intervals for each {ctx.label(group)}.")
    for m, bx in boxes:
        res.chart(f"box_{m}", "box", f"{ctx.label(m)} by {ctx.label(group)}", {"groups": bx}, ctx.label(group),
                  ctx.label(m), "Box plots: median, quartiles and range; points are outliers.")

    done = [r for r in rows if "p" in r]
    sig = [r for r in done if r["p"] < ctx.alpha]
    d = ctx.decimals

    def higher(r):
        return a if r["diff"] > 0 else b

    plain = (f"{len(sig)} of {len(done)} measure(s) differed significantly between {a} and {b}"
             + (": " + "; ".join(f"{higher(r)} scored higher on {r['measure']}" for r in sig) if sig else "")
             + ".")
    tech = " ".join(
        f"{r['measure']}: {a} M = {fmt_num(r['mean_a'], d)} (SD = {fmt_num(r['sd_a'], d)}), {b} M = "
        f"{fmt_num(r['mean_b'], d)} (SD = {fmt_num(r['sd_b'], d)}); {r['test']}, "
        + (f"t({r['df']:.1f}) = {r['statistic']:.2f}" if r["stat_name"] == "t" else f"U = {r['statistic']:.1f}")
        + f", {fmt_p(r['p'], ctx.p_style)}, {r['effect_name'].split(' ')[0]} = {r['effect']:.2f}." for r in done)
    res.summary = {"significant": bool(sig), "p": done[0]["p"] if len(done) == 1 else None,
                   "effect": done[0]["effect"] if len(done) == 1 else None,
                   "effect_name": done[0]["effect_name"] if len(done) == 1 else None,
                   "significant_measures": len(sig), "measures": len(done)}
    res.interpretation = {"plain": plain, "technical": tech}
    res.plain_title = f"Compare {a} and {b}"
    return res


def code_two(config, v):
    o = _opts(TWO, config)
    group, measures = assigned(config, "group")[0], assigned(config, "measures")
    a, b = o.get("group_a") or "<group A>", o.get("group_b") or "<group B>"
    return (codegen.prelude(v, [group, *measures], ["from scipy import stats"], listwise=False)
            + codegen.numeric_ordinal_note(v, measures)
            + f"g = df[{group!r}].astype(str)\n"
            f"for m in {measures!r}:\n"
            f"    x1 = df.loc[g == {a!r}, m].dropna().astype(float)\n"
            f"    x2 = df.loc[g == {b!r}, m].dropna().astype(float)\n"
            "    print(m, 'Welch t:', stats.ttest_ind(x1, x2, equal_var=False))\n"
            "    print(m, 'Mann-Whitney:', stats.mannwhitneyu(x1, x2))\n")


# --------------------------------------------------------------------------- several groups


def _dunn(arrays, names):
    from .nonparametric import dunn

    return dunn(arrays, names, "holm")


def run_multi(ctx: Context, config: dict[str, Any]) -> Result:
    import pingouin as pg

    res = Result(MULTI, config, ctx)
    o = _opts(MULTI, config)
    group = assigned(config, "group")[0]
    measures = assigned(config, "measures")
    level = float(o["ci_level"])
    df = ctx.frame([group, *measures])
    g, levels = _groups(ctx, df, group, o.get("groups") or None)
    if len(levels) < 3:
        raise AnalysisError(f"'{ctx.label(group)}' has {len(levels)} groups with data; this comparison needs three or more.",
                            suggestion="Use 'Compare two groups' instead.")
    rows, desc_rows, ph_rows = [], [], []
    series = {lv: {"values": [], "lower": [], "upper": []} for lv in levels}
    for m in measures:
        y = ctx.numeric(df, m)
        arrays = [y[(g == lv).to_numpy() & y.notna().to_numpy()].to_numpy(float) for lv in levels]
        if any(len(a) < 2 for a in arrays):
            rows.append({"measure": ctx.label(m), "test": "Not computed", "note": "a group has fewer than 2 values"})
            continue
        for lv, arr in zip(levels, arrays, strict=True):
            desc_rows.append({"measure": ctx.label(m), "group": lv, "n": len(arr), "mean": arr.mean(),
                              "sd": arr.std(ddof=1), "median": float(np.median(arr))})
            ci = mean_ci(lv, arr, level)
            series[lv]["values"].append(ci["mean"])
            series[lv]["lower"].append(ci["lower"])
            series[lv]["upper"].append(ci["upper"])
        test, reason = _choose(ctx, m, arrays, o["test"], False)
        n, k = sum(len(a) for a in arrays), len(arrays)
        row: dict[str, Any] = {"measure": ctx.label(m), "k": k, "n": n, "test": TEST_NAMES[test], "reason": reason}
        if test == "kruskal":
            H, p = stats.kruskal(*arrays)
            row.update(statistic=H, df1=k - 1, p=p, effect=H / ((n**2 - 1) / (n + 1)), effect_name="ε²")
        elif test == "welch_anova":
            long = pd.DataFrame({"y": np.concatenate(arrays), "g": np.repeat(levels, [len(a) for a in arrays])})
            w = pg.welch_anova(long, dv="y", between="g").iloc[0]
            grand = long["y"].mean()
            eta = sum(len(a) * (a.mean() - grand) ** 2 for a in arrays) / ((long["y"] - grand) ** 2).sum()
            row.update(statistic=float(w["F"]), df1=float(w["ddof1"]), df2=float(w["ddof2"]), p=float(w["p_unc"]),
                       effect=eta, effect_name="η²")
        else:
            F, p = stats.f_oneway(*arrays)
            grand = np.concatenate(arrays).mean()
            ssb = sum(len(a) * (a.mean() - grand) ** 2 for a in arrays)
            sst = sum(((a - grand) ** 2).sum() for a in arrays)
            row.update(statistic=F, df1=k - 1, df2=n - k, p=p, effect=ssb / sst, effect_name="η²")
        row["effect_label"] = eta_label(row["effect"])
        rows.append(row)
        if row["p"] < ctx.alpha:
            if test == "anova":
                r = stats.tukey_hsd(*arrays)
                for i, j in combinations(range(k), 2):
                    ph_rows.append({"measure": ctx.label(m), "a": levels[i], "b": levels[j],
                                    "diff": arrays[i].mean() - arrays[j].mean(), "p": float(r.pvalue[i, j]),
                                    "method": "Tukey HSD"})
            elif test == "welch_anova":
                long = pd.DataFrame({"y": np.concatenate(arrays), "g": np.repeat(levels, [len(a) for a in arrays])})
                for _, x in pg.pairwise_gameshowell(long, dv="y", between="g").iterrows():
                    ph_rows.append({"measure": ctx.label(m), "a": str(x["A"]), "b": str(x["B"]), "diff": float(x["diff"]),
                                    "p": float(x["pval"]), "method": "Games–Howell"})
            else:
                for x in _dunn(arrays, levels):
                    ph_rows.append({"measure": ctx.label(m), "a": x["a"], "b": x["b"], "diff": None, "p": x["p"],
                                    "method": "Dunn (Holm)"})
    res.n = int(g.isin(levels).sum())
    res.table("desc", "descriptives", f"Descriptive Statistics by {ctx.label(group)}",
              [col("measure", "Measure", "text"), col("group", ctx.label(group), "text"), col("n", "N", "int", "n"),
               col("mean", "Mean", "num", "mean"), col("sd", "SD", "num", "sd"), col("median", "Median", "num", "median")],
              desc_rows)
    res.table("main", "main", f"Comparison across {ctx.label(group)} groups",
              [col("measure", "Measure", "text"), col("test", "Test", "text"), col("statistic", "Statistic", "stat", "statistic"),
               col("df1", "df1", "num", "df"), col("df2", "df2", "num", "df"), col("p", "p", "p", "p"),
               col("effect", "Effect size", "num", "effect"), col("effect_label", "Magnitude", "text", "effect")], rows,
              ["Test selection — " + "; ".join(sorted({f"{r['test']}: {r['reason']}" for r in rows if r.get("reason")})) + ".",
               "Effect size: η² for ANOVA, ε² for Kruskal–Wallis."])
    if ph_rows:
        res.table("posthoc", "posthoc", "Post Hoc Comparisons",
                  [col("measure", "Measure", "text"), col("a", "Group A", "text"), col("b", "Group B", "text"),
                   col("diff", "Mean difference (A − B)", "num"), col("method", "Method", "text"), col("p", "p (adjusted)", "p", "p")],
                  ph_rows, ["Shown only for measures with a significant overall test; p-values are corrected for multiple "
                            "comparisons."])
    res.assumption("Independent groups", "info", "Each case should belong to only one group.")
    res.chart("means", "means", f"Mean scores by {ctx.label(group)}",
              {"categories": [r["measure"] for r in rows if "p" in r], "series": [{"name": k, **v} for k, v in series.items()]},
              "Measure", "Mean", f"Means with {level:.0%} confidence intervals.")
    done = [r for r in rows if "p" in r]
    sig = [r for r in done if r["p"] < ctx.alpha]
    res.summary = {"significant": bool(sig), "significant_measures": len(sig), "measures": len(done),
                   "p": done[0]["p"] if len(done) == 1 else None}
    res.interpretation = {
        "plain": (f"{len(sig)} of {len(done)} measure(s) differed significantly across the {ctx.label(group)} groups."
                  + (" The post hoc table shows which groups differ." if sig else "")),
        "technical": " ".join(f"{r['measure']}: {r['test']}, statistic = {r['statistic']:.2f}, "
                              f"{fmt_p(r['p'], ctx.p_style)}, {r['effect_name']} = {r['effect']:.3f}." for r in done),
    }
    res.plain_title = f"Compare {len(levels)} {ctx.label(group)} groups"
    return res


def code_multi(config, v):
    group, measures = assigned(config, "group")[0], assigned(config, "measures")
    return (codegen.prelude(v, [group, *measures], ["from scipy import stats"], listwise=False)
            + f"for m in {measures!r}:\n"
            f"    groups = [x[m].dropna().astype(float) for _, x in df.groupby({group!r}, observed=True)]\n"
            "    print(m, stats.f_oneway(*groups), stats.kruskal(*groups))\n")


TEST_OPT = [{"value": "auto", "label": "Automatic (recommended)"}]
TWO = register(AnalysisSpec(
    id="compare_two_groups", name="Two-Group Comparison", plain_name="Compare two groups",
    category="compare",
    description="Compares two independent groups (e.g. Formulation 1 and Formulation 2) on one or more measures.",
    when_to_use="A grouping column (formulation, product, treatment) and one or more numeric or rating measures.",
    roles=[Role("group", "Groups", "The column that identifies the groups.", CATEGORICAL_LEVELS, plain="Which groups?"),
           Role("measures", "Measures", "Scores or measurements to compare.", SCALE_LEVELS, 1, 40,
                plain="What do you want to compare?")],
    options=[Option("group_a", "First group", "level", None, depends_on="group"),
             Option("group_b", "Second group", "level", None, depends_on="group"),
             Option("test", "Test", "select", "auto",
                    TEST_OPT + [{"value": "welch", "label": "Welch's t-test"}, {"value": "student", "label": "Student's t-test"},
                                {"value": "mann_whitney", "label": "Mann–Whitney U"}], advanced=True),
             Option("p_adjust", "Adjust p-values across measures", "select", "none",
                    [{"value": "none", "label": "No adjustment"}, {"value": "holm", "label": "Holm"},
                     {"value": "bonferroni", "label": "Bonferroni"}], advanced=True),
             Option("alternative", "Alternative hypothesis", "select", "two-sided",
                    [{"value": "two-sided", "label": "Two-sided"}, {"value": "greater", "label": "First > second"},
                     {"value": "less", "label": "First < second"}], advanced=True),
             Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)],
    run=run_two, code=code_two,
    assumptions=["Independent groups (different participants in each group).",
                 "t-tests: approximately normal scores within groups, or groups of about 30 or more."],
    method="Per measure: Welch's t (scipy.stats.ttest_ind, equal_var=False) by default, or Mann–Whitney U when the "
           "measure is ordinal or a small group is clearly non-normal (Shapiro–Wilk). Cohen's d uses the pooled SD.",
    missing_data="Missing values are excluded separately for each measure.",
))
MULTI = register(AnalysisSpec(
    id="compare_groups", name="Multi-Group Comparison", plain_name="Compare three or more groups",
    category="compare",
    description="Compares three or more independent groups on one or more measures, with corrected post hoc tests.",
    roles=[Role("group", "Groups", "The column that identifies the groups.", CATEGORICAL_LEVELS),
           Role("measures", "Measures", "Scores or measurements to compare.", SCALE_LEVELS, 1, 40)],
    options=[Option("groups", "Groups to include", "levels", [], depends_on="group", advanced=True),
             Option("test", "Test", "select", "auto",
                    TEST_OPT + [{"value": "anova", "label": "One-way ANOVA"}, {"value": "welch_anova", "label": "Welch's ANOVA"},
                                {"value": "kruskal", "label": "Kruskal–Wallis"}], advanced=True),
             Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)],
    run=run_multi, code=code_multi,
    assumptions=["Independent groups.", "ANOVA: approximately normal scores; Welch's ANOVA when variances differ."],
    method="Per measure: one-way ANOVA (Tukey HSD), Welch's ANOVA (Games–Howell) when Levene's test is significant, or "
           "Kruskal–Wallis (Dunn with Holm correction) for ordinal or non-normal small-sample data.",
    missing_data="Missing values are excluded separately for each measure.",
))


# --------------------------------------------------------------------------- ranking ("which is the most acceptable?")


def run_rank(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(RANK, config, ctx)
    o = _opts(RANK, config)
    group = assigned(config, "group")[0]
    measures = assigned(config, "measures")
    df = ctx.frame([group, *measures])
    g, levels = _groups(ctx, df, group, None)
    if len(levels) < 2:
        raise AnalysisError(f"'{ctx.label(group)}' needs at least two groups to rank.")
    means: dict[str, dict[str, float]] = {lv: {} for lv in levels}
    rows = []
    for m in measures:
        y = ctx.numeric(df, m)
        row: dict[str, Any] = {"measure": ctx.label(m)}
        best, best_mean = None, -np.inf
        for j, lv in enumerate(levels):
            x = y[(g == lv).to_numpy() & y.notna().to_numpy()].to_numpy(float)
            mean = float(x.mean()) if len(x) else np.nan
            means[lv][m] = mean
            row[f"m{j}"], row[f"s{j}"] = mean, (float(x.std(ddof=1)) if len(x) > 1 else None)
            if np.isfinite(mean) and mean > best_mean:
                best, best_mean = lv, mean
        row["highest"] = best
        rows.append(row)
    decide = o.get("decide_by") or "average"
    decide = decide if decide in measures else "average"
    scores = {lv: (means[lv][decide] if decide != "average" else float(np.nanmean(list(means[lv].values()))))
              for lv in levels}
    order = sorted(levels, key=lambda lv: -scores[lv] if np.isfinite(scores[lv]) else np.inf)
    cols = [col("measure", "Measure", "text")]
    for j, lv in enumerate(levels):
        cols += [col(f"m{j}", f"Mean ({lv})", "num", "mean"), col(f"s{j}", f"SD ({lv})", "num", "sd")]
    cols.append(col("highest", "Highest mean", "text"))
    basis = ctx.label(decide) if decide != "average" else "the average of all measures"
    res.table("desc", "descriptives", f"Mean scores by {ctx.label(group)}", cols, rows)
    res.table("main", "main", f"Ranking of {ctx.label(group)} groups",
              [col("rank", "Rank", "int"), col("group", ctx.label(group), "text"), col("score", "Mean score", "num", "mean")],
              [{"rank": i + 1, "group": lv, "score": scores[lv]} for i, lv in enumerate(order)],
              [f"Ranked by {basis}. A higher mean means more acceptable. Ranking describes the sample; whether the "
               "difference is statistically significant is answered by the group comparison."])
    res.chart("means", "means", f"Mean scores by {ctx.label(group)}",
              {"categories": [ctx.label(m) for m in measures],
               "series": [{"name": lv, "values": [means[lv][m] for m in measures]} for lv in levels]},
              "Measure", "Mean", f"Mean scores of each {ctx.label(group)}.")
    res.n = int(g.isin(levels).sum())
    top, second = order[0], order[1]
    d = ctx.decimals
    res.summary = {"top": top}
    res.interpretation = {
        "plain": (f"{top} was the most acceptable, with the highest mean on {basis} "
                  f"({fmt_num(scores[top], d)} vs {fmt_num(scores[second], d)} for {second})."),
        "technical": (f"Ranked by {basis}, {top} obtained the highest mean (M = {fmt_num(scores[top], d)}), followed by "
                      + ", ".join(f"{lv} (M = {fmt_num(scores[lv], d)})" for lv in order[1:])
                      + ". This ranking is descriptive; see the group comparison for statistical significance."),
    }
    res.plain_title = f"Most acceptable {ctx.label(group).lower()}"
    return res


def code_rank(config, v):
    group, measures = assigned(config, "group")[0], assigned(config, "measures")
    return (codegen.prelude(v, [group, *measures], [], listwise=False)
            + f"print(df.groupby({group!r})[{measures!r}].mean().round(2))\n")


RANK = register(AnalysisSpec(
    id="rank_groups", name="Group Ranking", plain_name="Find the most acceptable group",
    category="compare",
    description="Ranks groups (e.g. formulations) by their mean scores to show which is most acceptable.",
    when_to_use="Objectives such as 'Which group rated the module highest?'.",
    roles=[Role("group", "Groups", "The column that identifies the groups.", CATEGORICAL_LEVELS),
           Role("measures", "Measures", "Scores used for ranking.", SCALE_LEVELS, 1, 40)],
    options=[Option("decide_by", "Rank by", "text", "average",
                    help="A measure name (e.g. Overall Acceptability) or 'average' of all measures.")],
    run=run_rank, code=code_rank,
    assumptions=["Ranking is descriptive; it does not test significance."],
    method="Group means per measure; groups ordered by the chosen measure (or the average of all measures).",
    missing_data="Missing values are excluded separately for each measure.",
))
