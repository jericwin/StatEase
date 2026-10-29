from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..errors import AnalysisError
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
    register,
)
from .common import box_stats, describe, histogram_data, mean_ci

STAT_CHOICES = [
    ("n", "Valid N", "int"), ("missing", "Missing N", "int"), ("mean", "Mean", "num"), ("median", "Median", "num"),
    ("mode", "Mode", "num"), ("sd", "Std. deviation", "num"), ("variance", "Variance", "num"),
    ("min", "Minimum", "num"), ("max", "Maximum", "num"), ("range", "Range", "num"), ("sum", "Sum", "num"),
    ("q1", "25th percentile (Q1)", "num"), ("q3", "75th percentile (Q3)", "num"), ("iqr", "IQR", "num"),
    ("se", "Std. error of mean", "num"), ("ci", "CI for the mean", "ci"),
    ("skewness", "Skewness", "num"), ("se_skewness", "SE skewness", "num"),
    ("kurtosis", "Kurtosis (excess)", "num"), ("se_kurtosis", "SE kurtosis", "num"),
]
STAT_LABEL = {k: lbl for k, lbl, _ in STAT_CHOICES}
STAT_FMT = {k: f for k, _, f in STAT_CHOICES}

PRESETS = {
    "basic": ["n", "missing", "mean", "sd", "min", "max"],
    "thesis": ["n", "mean", "sd", "min", "max", "skewness", "kurtosis"],
    "complete": [k for k, _, _ in STAT_CHOICES],
    "frequency": ["n", "missing"],
}


def _parse_percentiles(text: str | None) -> list[float]:
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = float(part)
        except ValueError as exc:
            raise AnalysisError(f"'{part}' is not a valid percentile. Use numbers between 0 and 100.") from exc
        if not 0 < v < 100:
            raise AnalysisError(f"Percentile {v:g} must be between 0 and 100.")
        out.append(v)
    return sorted(set(out))


def run_descriptives(ctx: Context, config: dict[str, Any]) -> Result:
    spec = REG_DESC
    res = Result(spec, config, ctx)
    opts = {**spec.defaults(), **(config.get("options") or {})}
    names = assigned(config, "variables")
    split = (assigned(config, "split_by") or [None])[0]
    selected = [s for s in (opts.get("statistics") or PRESETS["thesis"]) if s in STAT_LABEL]
    percentiles = _parse_percentiles(opts.get("percentiles"))
    ci_level = float(opts.get("ci_level") or ctx.ci_level)

    as_numeric = {"numeric", "ordinal"} if opts.get("ordinal_as_numeric", True) else {"numeric"}
    numeric = [n for n in names if ctx.meta(n).level in as_numeric]
    categorical = [n for n in names if n not in numeric and ctx.meta(n).level in CATEGORICAL_LEVELS]
    skipped = [n for n in names if n not in numeric and n not in categorical]
    for n in skipped:
        res.warn(f"'{ctx.label(n)}' is a {ctx.meta(n).level} variable; descriptive statistics are not computed for it.")
    if not numeric and not categorical:
        raise AnalysisError("Select at least one numeric or categorical variable.")

    df = ctx.frame(names + ([split] if split else []))
    res.n = len(df)
    res.missing = {"total_rows": len(df), "method": "available cases per variable"}

    groups: list[tuple[str | None, pd.Series]] = [(None, pd.Series(True, index=df.index))]
    if split:
        g = ctx.categorical(df, split)
        if len(g.cat.categories) > 30:
            raise AnalysisError(f"'{ctx.label(split)}' has {len(g.cat.categories)} groups; choose a split variable "
                                "with 30 or fewer groups.")
        groups = [(str(c), g == c) for c in g.cat.categories]
        n_missing_split = int(g.isna().sum())
        if n_missing_split:
            res.notes.append(f"{n_missing_split:,} rows with a missing value on {ctx.label(split)} are not shown in "
                             "the grouped table.")

    if numeric:
        columns = [col("variable", "Variable", "text")]
        if split:
            columns.append(col("group", ctx.label(split), "text"))
        for s in selected:
            if s == "ci":
                columns += [col("ci_lower", f"{ci_level:.0%} CI lower", "num", "ci"),
                            col("ci_upper", f"{ci_level:.0%} CI upper", "num", "ci")]
            else:
                columns.append(col(s, STAT_LABEL[s], STAT_FMT[s], s))
        for p in percentiles:
            columns.append(col(f"p{p:g}", f"{p:g}th percentile", "num", "percentiles"))
        rows = []
        multi_mode = []
        for n in numeric:
            series = ctx.numeric(df, n)
            for gname, mask in groups:
                vals = series[mask]
                x = vals.dropna().to_numpy(dtype=float)
                d = describe(x, ci_level)
                d["missing"] = int(vals.isna().sum())
                for p in percentiles:
                    d[f"p{p:g}"] = float(np.percentile(x, p)) if len(x) else None
                if d.get("mode_count", 0) > 1:
                    multi_mode.append(ctx.label(n))
                row = {"variable": ctx.label(n), "group": gname, **{k: d.get(k) for k in d}}
                rows.append(row)
        notes = ["Skewness and kurtosis are bias-corrected sample estimates; kurtosis is excess kurtosis (normal = 0)."]
        if "mode" in selected:
            notes.append("Mode is blank when no value occurs more than once.")
            if multi_mode:
                notes.append("Multiple modes exist for " + ", ".join(sorted(set(multi_mode)))
                             + "; the smallest is shown.")
        if any(ctx.meta(n).level == "ordinal" for n in numeric):
            notes.append("Ordinal (rating) variables are summarised numerically; the median is often the more "
                         "appropriate centre for ordinal data.")
        res.table("descriptives", "descriptives", "Descriptive Statistics" + (f" by {ctx.label(split)}" if split else ""),
                  columns, rows, notes)

        if opts.get("charts", True) and len(numeric) >= 2:
            # Mean of every variable (per group when split) with confidence intervals: the usual summary figure.
            series = []
            for gname, mask in groups:
                vals, lows, highs = [], [], []
                for n in numeric:
                    m = mean_ci("", ctx.numeric(df, n)[mask].dropna().to_numpy(float), ci_level)
                    vals.append(m.get("mean"))
                    lows.append(m.get("lower"))
                    highs.append(m.get("upper"))
                series.append({"name": gname or "Mean", "values": vals, "lower": lows, "upper": highs})
            res.chart("means", "means", "Mean scores" + (f" by {ctx.label(split)}" if split else ""),
                      {"categories": [ctx.label(n) for n in numeric], "series": series}, "Variable", "Mean",
                      f"Means with {ci_level:.0%} confidence intervals.")
        if opts.get("charts", True):
            for n in numeric[:12]:
                series = ctx.numeric(df, n)
                unit = ctx.meta(n).unit
                axis = ctx.label(n) + (f" ({unit})" if unit else "")
                if split:
                    boxes = [box_stats(gname or "", series[mask].dropna().to_numpy(float)) for gname, mask in groups]
                    res.chart(f"box_{n}", "box", f"{ctx.label(n)} by {ctx.label(split)}", {"groups": boxes},
                              ctx.label(split), axis, f"Distribution of {ctx.label(n)} for each {ctx.label(split)} group.")
                else:
                    x = series.dropna().to_numpy(float)
                    res.chart(f"hist_{n}", "histogram", f"Distribution of {ctx.label(n)}", histogram_data(x),
                              axis, "Frequency", f"Histogram of {ctx.label(n)} (n = {len(x):,}) with a fitted normal "
                                                 "curve for reference.")

    for n in categorical:
        _frequency_table(ctx, res, df, n, opts.get("charts", True))

    # Summary + interpretation
    parts = []
    tech = []
    if numeric:
        rows = [r for r in res.tables[0]["rows"] if r.get("group") is None] if not split else []
        for r in rows[:6]:
            if r.get("mean") is not None and r.get("sd") is not None:
                parts.append(f"{r['variable']} averaged {fmt_num(r['mean'], ctx.decimals)} "
                             f"(SD = {fmt_num(r['sd'], ctx.decimals)}, n = {r['n']:,})")
                tech.append(f"{r['variable']}: M = {fmt_num(r['mean'], ctx.decimals)}, "
                            f"SD = {fmt_num(r['sd'], ctx.decimals)}, Mdn = {fmt_num(r['median'], ctx.decimals)}, "
                            f"range {fmt_num(r['min'], ctx.decimals)}–{fmt_num(r['max'], ctx.decimals)}, n = {r['n']:,}")
                sk = r.get("skewness")
                if sk is not None and abs(sk) > 1:
                    tech[-1] += f", noticeably {'right' if sk > 0 else 'left'}-skewed (skewness = {sk:.2f})"
    plain = ("; ".join(parts) + ".") if parts else ""
    if split and numeric:
        plain = f"Descriptive statistics are reported separately for each {ctx.label(split)} group."
    if categorical:
        plain += (" " if plain else "") + "Frequency tables show how responses are distributed across categories."
    res.interpretation = {"plain": plain.strip(), "technical": ("; ".join(tech) + ".") if tech else plain.strip()}
    res.summary = {"variables": len(numeric) + len(categorical)}
    return res


def _frequency_table(ctx: Context, res: Result, df: pd.DataFrame, name: str, charts: bool) -> None:
    cat = ctx.categorical(df, name)
    total = len(cat)
    valid = int(cat.notna().sum())
    missing = total - valid
    counts = cat.value_counts(sort=False)
    meta = ctx.meta(name)
    show_cum = meta.level in {"ordinal", "binary"}
    columns = [col("category", ctx.label(name), "text"), col("frequency", "Frequency", "int", "frequency"),
               col("percent", "Percent", "pct", "percent"), col("valid_percent", "Valid percent", "pct", "valid_percent")]
    if show_cum:
        columns.append(col("cumulative_percent", "Cumulative percent", "pct", "cumulative_percent"))
    rows = []
    cum = 0.0
    for level, n in counts.items():
        vp = n / valid * 100 if valid else None
        cum += vp or 0
        rows.append({"category": str(level), "frequency": int(n), "percent": n / total * 100 if total else None,
                     "valid_percent": vp, "cumulative_percent": cum if show_cum else None})
    if missing:
        rows.append({"category": "Missing", "frequency": missing, "percent": missing / total * 100,
                     "valid_percent": None, "cumulative_percent": None, "_style": "muted"})
    rows.append({"category": "Total", "frequency": total, "percent": 100.0 if total else None,
                 "valid_percent": 100.0 if valid else None, "cumulative_percent": None, "_style": "total"})
    notes = []
    if not show_cum:
        notes.append("Cumulative percentages are omitted because the categories have no natural order.")
    modes = counts[counts == counts.max()].index.tolist() if valid else []
    notes.append(f"{len(counts)} distinct categories; mode: {', '.join(map(str, modes))}." if modes else "No valid values.")
    res.table(f"freq_{name}", "frequencies", f"Frequencies of {ctx.label(name)}", columns, rows, notes)
    if charts and 0 < len(counts) <= 30:
        res.chart(f"bar_{name}", "bar", f"Frequencies of {ctx.label(name)}",
                  {"categories": [str(c) for c in counts.index], "series": [{"name": "Frequency",
                                                                             "values": counts.tolist()}]},
                  ctx.label(name), "Frequency", f"Number of cases in each {ctx.label(name)} category (n = {valid:,}).")


def run_frequencies(ctx: Context, config: dict[str, Any]) -> Result:
    res = Result(REG_FREQ, config, ctx)
    opts = {**REG_FREQ.defaults(), **(config.get("options") or {})}
    names = assigned(config, "variables")
    df = ctx.frame(names)
    res.n = len(df)
    res.missing = {"total_rows": len(df), "method": "missing values are reported as their own row"}
    for n in names:
        _frequency_table(ctx, res, df, n, opts.get("charts", True))
    sentences = []
    for t in res.tables:
        valid_rows = [r for r in t["rows"] if r.get("_style") is None]
        if valid_rows:
            top = max(valid_rows, key=lambda r: r["frequency"])
            sentences.append(f"the most common {t['title'].removeprefix('Frequencies of ')} category was "
                             f"'{top['category']}' ({top['frequency']:,} cases, {top['valid_percent']:.1f}% of valid "
                             "responses)")
    text = ("Across the selected variables, " + "; ".join(sentences) + ".") if sentences else ""
    res.interpretation = {"plain": text, "technical": text}
    return res


REG_DESC = register(AnalysisSpec(
    id="descriptives",
    name="Descriptive Statistics",
    plain_name="Summarise numeric variables",
    category="descriptives",
    description="Averages, spread and shape of each selected variable; categorical variables get frequency tables.",
    when_to_use="Always report descriptive statistics before any inferential test.",
    roles=[
        Role("variables", "Variables", "The variables to summarise.", SCALE_LEVELS | CATEGORICAL_LEVELS, 1, None,
             "What do you want to summarise?"),
        Role("split_by", "Split by (optional)", "Report the statistics separately for each group of this variable.",
             CATEGORICAL_LEVELS, 0, 1, "Show results separately for each group?"),
    ],
    options=[
        Option("statistics", "Statistics", "multiselect", PRESETS["thesis"],
               [{"value": k, "label": lbl} for k, lbl, _ in STAT_CHOICES]),
        Option("percentiles", "Additional percentiles", "text", "", help="Comma-separated, e.g. 10, 90",
               advanced=True),
        Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True),
        Option("ordinal_as_numeric", "Summarise ordinal ratings numerically", "bool", True,
               help="Likert items are summarised with means. Turn off to show frequency tables instead.",
               advanced=True),
        Option("charts", "Charts", "bool", True),
    ],
    run=run_descriptives,
    method="Mean, median, standard deviation (n − 1 denominator), quartiles (linear interpolation), standard error "
           "and a t-based confidence interval for the mean. Skewness (G1) and excess kurtosis (G2) are the "
           "bias-corrected estimators used by SPSS and JASP.",
    missing_data="Each variable uses all of its available (non-missing) values; the number missing is reported.",
))

REG_FREQ = register(AnalysisSpec(
    id="frequencies",
    name="Frequency Tables",
    plain_name="Count responses in each category",
    category="descriptives",
    description="How many cases fall into each category, with percentages.",
    when_to_use="For categorical variables such as gender, year level or yes/no answers.",
    roles=[Role("variables", "Variables", "Categorical variables to tabulate.", CATEGORICAL_LEVELS, 1, None,
                "Which categories do you want to count?")],
    options=[Option("charts", "Bar charts", "bool", True)],
    run=run_frequencies,
    method="Counts with percent of all rows, valid percent (excluding missing) and cumulative percent for "
           "ordered categories.",
    missing_data="Missing values are counted and shown in their own row; valid percentages exclude them.",
))
