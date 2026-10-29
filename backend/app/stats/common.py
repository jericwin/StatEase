"""Shared statistical helpers: summaries, assumption checks and chart data."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .base import Result, fmt_p

MAX_POINTS = 2000  # cap on raw points sent to scatter/QQ charts


def describe(x: np.ndarray, ci_level: float = 0.95) -> dict[str, Any]:
    """Descriptive statistics of a 1-D numeric array with NaN removed by the caller."""
    n = len(x)
    out: dict[str, Any] = {"n": n}
    if n == 0:
        return out
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1)) if n > 1 else math.nan
    se = sd / math.sqrt(n) if n > 1 else math.nan
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    out.update(mean=mean, sd=sd, variance=sd**2 if n > 1 else math.nan, se=se, median=float(med),
               min=float(np.min(x)), max=float(np.max(x)), range=float(np.ptp(x)), sum=float(np.sum(x)),
               q1=float(q1), q3=float(q3), iqr=float(q3 - q1))
    if n > 1:
        t = stats.t.ppf(0.5 + ci_level / 2, n - 1)
        out["ci_lower"], out["ci_upper"] = mean - t * se, mean + t * se
    # Bias-corrected sample skewness (G1) and excess kurtosis (G2), as reported by SPSS and JASP.
    if n >= 3 and sd > 0:
        out["skewness"] = float(stats.skew(x, bias=False))
        out["se_skewness"] = math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))
    if n >= 4 and sd > 0:
        out["kurtosis"] = float(stats.kurtosis(x, bias=False))
        out["se_kurtosis"] = 2 * out["se_skewness"] * math.sqrt((n * n - 1) / ((n - 3) * (n + 5)))
    vals, counts = np.unique(x, return_counts=True)
    top = counts.max()
    modes = vals[counts == top]
    out["mode"] = float(modes[0]) if top > 1 else None
    out["mode_count"] = int(len(modes)) if top > 1 else 0
    return out


def shapiro(x: np.ndarray, max_n: int) -> dict[str, Any] | None:
    n = len(x)
    if n < 3 or np.ptp(x) == 0:
        return None
    if n > max_n:
        return {"skipped": True, "n": n}
    w, p = stats.shapiro(x)
    return {"W": float(w), "p": float(p), "n": n}


def normality_assessment(res: Result, x: np.ndarray, label: str, *, what: str = "values") -> bool | None:
    """Add a normality assumption entry. Returns False if non-normality looks consequential."""
    n = len(x)
    sw = shapiro(x, res.ctx.shapiro_max_n)
    skew = float(stats.skew(x, bias=False)) if n >= 3 and np.ptp(x) > 0 else None
    name = f"Normality of {what} ({label})"
    if sw is None:
        res.assumption(name, "info", "Not enough variation or observations to assess normality.")
        return None
    if sw.get("skipped"):
        status = "warning" if skew is not None and abs(skew) > 2 else "ok"
        res.assumption(name, status,
                       f"Shapiro–Wilk not computed for n = {n:,} (limit {res.ctx.shapiro_max_n:,}); with large "
                       f"samples the test flags trivial departures. Skewness = {skew:.2f}. Inspect the Q–Q plot.",
                       skewness=skew)
        return status == "ok"
    large = n > 200
    if sw["p"] < res.ctx.alpha:
        if large:
            res.assumption(name, "info",
                           f"Shapiro–Wilk W = {sw['W']:.3f}, {fmt_p(sw['p'], res.ctx.p_style)}. With n = {n}, small "
                           "departures from normality are detected; parametric tests are generally robust at this "
                           "sample size. Check the Q–Q plot for severe skew or outliers.",
                           statistic=sw["W"], p=sw["p"], test="Shapiro–Wilk")
            return True
        res.assumption(name, "violated",
                       f"Shapiro–Wilk W = {sw['W']:.3f}, {fmt_p(sw['p'], res.ctx.p_style)}: the {what} depart from a "
                       "normal distribution. Consider the nonparametric alternative, especially with small samples.",
                       statistic=sw["W"], p=sw["p"], test="Shapiro–Wilk")
        return False
    res.assumption(name, "ok",
                   f"Shapiro–Wilk W = {sw['W']:.3f}, {fmt_p(sw['p'], res.ctx.p_style)}: no evidence against "
                   "normality. (A non-significant test does not prove normality, particularly in small samples.)",
                   statistic=sw["W"], p=sw["p"], test="Shapiro–Wilk")
    return True


def levene(res: Result, groups: list[np.ndarray], center: str = "median") -> dict[str, Any] | None:
    groups = [g for g in groups if len(g) > 1]
    if len(groups) < 2 or all(np.ptp(g) == 0 for g in groups):
        return None
    stat, p = stats.levene(*groups, center=center)
    df1 = len(groups) - 1
    df2 = sum(len(g) for g in groups) - len(groups)
    name = "Equality of variances (Levene" + (", median-centred)" if center == "median" else ")")
    ok = p >= res.ctx.alpha
    res.assumption(name, "ok" if ok else "violated",
                   f"F({df1}, {df2}) = {stat:.2f}, {fmt_p(p, res.ctx.p_style)}. "
                   + ("No evidence that group variances differ." if ok else
                      "Group variances differ; prefer a procedure that does not assume equal variances."),
                   statistic=float(stat), df1=df1, df2=df2, p=float(p), test="Levene")
    return {"F": float(stat), "df1": df1, "df2": df2, "p": float(p), "equal": ok}


def p_adjust(p: list[float], method: str) -> list[float]:
    if method in (None, "none") or not p:
        return list(p)
    from statsmodels.stats.multitest import multipletests

    arr = np.asarray(p, dtype=float)
    mask = np.isfinite(arr)
    out = np.full_like(arr, np.nan)
    if mask.any():
        out[mask] = multipletests(arr[mask], method={"bonferroni": "bonferroni", "holm": "holm",
                                                     "fdr": "fdr_bh"}[method])[1]
    return out.tolist()


# --------------------------------------------------------------------------- effect sizes


def cohen_label(d: float) -> str:
    a = abs(d)
    return "negligible" if a < 0.2 else "small" if a < 0.5 else "medium" if a < 0.8 else "large"


def r_label(r: float) -> str:
    a = abs(r)
    return "negligible" if a < 0.1 else "weak" if a < 0.3 else "moderate" if a < 0.5 else "strong"


def eta_label(e: float) -> str:
    return "negligible" if e < 0.01 else "small" if e < 0.06 else "medium" if e < 0.14 else "large"


def cramer_label(v: float, df_min: int) -> str:
    # Cohen (1988) thresholds scaled by min(r-1, c-1)
    k = max(df_min, 1)
    small, med, large = 0.1 / math.sqrt(k), 0.3 / math.sqrt(k), 0.5 / math.sqrt(k)
    return "negligible" if v < small else "small" if v < med else "medium" if v < large else "large"


# --------------------------------------------------------------------------- charts


def histogram_data(x: np.ndarray, bins: int | None = None) -> dict[str, Any]:
    if len(x) == 0:
        return {"bins": []}
    if bins is None:
        bins = int(min(40, max(5, math.ceil(math.log2(len(x)) + 1))))  # Sturges, bounded
    counts, edges = np.histogram(x, bins=bins)
    out = {"bins": [[float(edges[i]), float(edges[i + 1]), int(counts[i])] for i in range(len(counts))]}
    if len(x) > 2 and np.std(x) > 0:
        mu, sd = float(np.mean(x)), float(np.std(x, ddof=1))
        width = float(edges[1] - edges[0])
        grid = np.linspace(edges[0], edges[-1], 60)
        out["normal"] = [[float(g), float(stats.norm.pdf(g, mu, sd) * len(x) * width)] for g in grid]
    return out


def box_stats(name: str, x: np.ndarray) -> dict[str, Any]:
    if len(x) == 0:
        return {"name": name, "n": 0}
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    lo_f, hi_f = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = x[(x >= lo_f) & (x <= hi_f)]
    outliers = x[(x < lo_f) | (x > hi_f)]
    return {"name": name, "n": int(len(x)), "min": float(inside.min()) if len(inside) else float(q1),
            "q1": float(q1), "median": float(med), "q3": float(q3),
            "max": float(inside.max()) if len(inside) else float(q3),
            "outliers": [float(v) for v in outliers[:200]], "n_outliers": int(len(outliers))}


def mean_ci(name: str, x: np.ndarray, level: float) -> dict[str, Any]:
    n = len(x)
    if n == 0:
        return {"name": name, "n": 0}
    m = float(np.mean(x))
    if n < 2:
        return {"name": name, "n": n, "mean": m, "lower": None, "upper": None}
    se = float(np.std(x, ddof=1) / math.sqrt(n))
    t = stats.t.ppf(0.5 + level / 2, n - 1)
    return {"name": name, "n": n, "mean": m, "lower": m - t * se, "upper": m + t * se}


def qq_data(x: np.ndarray) -> dict[str, Any]:
    x = np.sort(x)
    n = len(x)
    if n < 3:
        return {"points": []}
    idx = np.unique(np.linspace(0, n - 1, min(n, MAX_POINTS)).astype(int))
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)  # Blom plotting positions
    theo = stats.norm.ppf(probs)
    # Reference line through the first and third quartiles.
    q1x, q3x = np.percentile(x, [25, 75])
    q1t, q3t = stats.norm.ppf([0.25, 0.75])
    slope = (q3x - q1x) / (q3t - q1t) if q3t != q1t else 0.0
    intercept = q1x - slope * q1t
    return {"points": [[float(theo[i]), float(x[i])] for i in idx], "line": {"slope": float(slope),
                                                                             "intercept": float(intercept)}}


def scatter_data(x: np.ndarray, y: np.ndarray, fit: bool = True) -> tuple[dict[str, Any], str | None]:
    n = len(x)
    note = None
    if n > MAX_POINTS:
        rng = np.random.default_rng(0)
        idx = np.sort(rng.choice(n, MAX_POINTS, replace=False))
        xs, ys = x[idx], y[idx]
        note = f"A random sample of {MAX_POINTS:,} of {n:,} points is shown; statistics use all points."
    else:
        xs, ys = x, y
    data: dict[str, Any] = {"points": [[float(a), float(b)] for a, b in zip(xs, ys, strict=True)]}
    if fit and n > 2 and np.ptp(x) > 0:
        slope, intercept = np.polyfit(x, y, 1)
        data["fit"] = {"slope": float(slope), "intercept": float(intercept),
                       "x_min": float(np.min(x)), "x_max": float(np.max(x))}
    return data, note


def group_arrays(y: pd.Series, g: pd.Series) -> tuple[list[str], list[np.ndarray]]:
    names, arrays = [], []
    for level in g.cat.categories:
        arr = y[g == level].to_numpy(dtype=float)
        names.append(str(level))
        arrays.append(arr)
    return names, arrays
