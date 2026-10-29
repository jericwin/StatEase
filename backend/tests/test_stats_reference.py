"""Statistical engine checked against published reference results (R outputs for classic datasets)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.errors import AnalysisError

from .helpers import run, table

# R: datasets::sleep (Student, 1908)
SLEEP_1 = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0.0, 2.0]
SLEEP_2 = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4]
SLEEP = pd.DataFrame({"extra": SLEEP_1 + SLEEP_2, "group": ["1"] * 10 + ["2"] * 10})
SLEEP_WIDE = pd.DataFrame({"drug1": SLEEP_1, "drug2": SLEEP_2})

# R: datasets::PlantGrowth
PLANT = pd.DataFrame({
    "weight": [4.17, 5.58, 5.18, 6.11, 4.50, 4.61, 5.17, 4.53, 5.33, 5.14,
               4.81, 4.17, 4.41, 3.59, 5.87, 3.83, 6.03, 4.89, 4.32, 4.69,
               6.31, 5.12, 5.54, 5.50, 5.37, 5.29, 4.92, 6.15, 5.80, 5.26],
    "group": ["ctrl"] * 10 + ["trt1"] * 10 + ["trt2"] * 10})

# R: datasets::cars
CARS = pd.DataFrame({
    "speed": [4, 4, 7, 7, 8, 9, 10, 10, 10, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 16, 16,
              17, 17, 17, 18, 18, 18, 18, 19, 19, 19, 20, 20, 20, 20, 20, 22, 23, 24, 24, 24, 24, 25],
    "dist": [2, 10, 4, 22, 16, 10, 18, 26, 34, 17, 28, 14, 20, 24, 28, 26, 34, 34, 46, 26, 36, 60, 80, 20, 26, 54, 32,
             40, 32, 40, 50, 42, 56, 76, 84, 36, 46, 68, 32, 48, 52, 56, 64, 66, 54, 70, 92, 93, 120, 85]})


def main(res):
    return table(res, "main")


def test_student_and_welch_t_sleep():
    res = run(SLEEP, {"group": "nominal"}, "independent_t", {"dependent": "extra", "group": "group"},
              {"test": "both"})
    student, welch = main(res)
    # R: t.test(extra ~ group, data = sleep, var.equal = TRUE): t = -1.8608, df = 18, p = 0.07919
    assert student["t"] == pytest.approx(-1.8608, abs=1e-4)
    assert student["df"] == 18
    assert student["p"] == pytest.approx(0.07919, abs=1e-5)
    # R: Welch: t = -1.8608, df = 17.776, p-value = 0.07939; 95% CI -3.3654832 0.2054832
    assert welch["df"] == pytest.approx(17.776, abs=1e-3)
    assert welch["p"] == pytest.approx(0.07939, abs=1e-5)
    assert welch["ci_lower"] == pytest.approx(-3.3654832, abs=1e-6)
    assert welch["ci_upper"] == pytest.approx(0.2054832, abs=1e-6)
    assert res["summary"]["significant"] is False
    assert "not statistically significant" in res["interpretation"]["technical"]


def test_paired_t_sleep():
    res = run(SLEEP_WIDE, {}, "paired_t", {"first": "drug1", "second": "drug2"})
    r = main(res)[0]
    # R: t.test(sleep$extra[1:10], sleep$extra[11:20], paired = TRUE): t = -4.0621, df = 9, p = 0.002833
    assert r["t"] == pytest.approx(-4.0621, abs=1e-4)
    assert r["df"] == 9
    assert r["p"] == pytest.approx(0.002833, abs=1e-6)
    # 95% CI -2.4598858 -0.7001142
    assert r["ci_lower"] == pytest.approx(-2.4598858, abs=1e-6)
    assert r["ci_upper"] == pytest.approx(-0.7001142, abs=1e-6)


def test_one_way_anova_plantgrowth_with_tukey():
    res = run(PLANT, {"group": "nominal"}, "one_way_anova", {"dependent": "weight", "factor": "group"},
              {"posthoc": "tukey"})
    r = main(res)[0]
    # R: summary(aov(weight ~ group, PlantGrowth)): F = 4.846, df 2, 27, p = 0.0159; SS 3.766, 10.492
    assert r["F"] == pytest.approx(4.846088, abs=1e-5)
    assert r["p"] == pytest.approx(0.01591, abs=1e-5)
    assert r["ss"] == pytest.approx(3.76634, abs=1e-5)
    assert main(res)[1]["ss"] == pytest.approx(10.49209, abs=1e-5)
    ph = {(x["a"], x["b"]): x for x in table(res, "posthoc")}
    # R: TukeyHSD: trt1-ctrl p 0.3908711, trt2-ctrl p 0.1979960, trt2-trt1 p 0.0120064
    assert ph[("ctrl", "trt1")]["p"] == pytest.approx(0.3908711, abs=1e-4)
    assert ph[("ctrl", "trt2")]["p"] == pytest.approx(0.1979960, abs=1e-4)
    assert ph[("trt1", "trt2")]["p"] == pytest.approx(0.0120064, abs=1e-4)
    assert ph[("trt1", "trt2")]["diff"] == pytest.approx(-0.865, abs=1e-9)


def test_kruskal_plantgrowth():
    res = run(PLANT, {"group": "nominal"}, "kruskal_wallis", {"dependent": "weight", "factor": "group"})
    r = main(res)[0]
    # R: kruskal.test(weight ~ group, PlantGrowth): chi-squared = 7.9882, df = 2, p = 0.01842
    assert r["H"] == pytest.approx(7.9882, abs=1e-4)
    assert r["p"] == pytest.approx(0.01842, abs=1e-5)


def test_welch_anova_plantgrowth():
    res = run(PLANT, {"group": "nominal"}, "welch_anova", {"dependent": "weight", "factor": "group"})
    r = main(res)[0]
    # R: oneway.test(weight ~ group, PlantGrowth): F = 5.181, num df = 2.000, denom df = 17.128, p = 0.01739
    assert r["F"] == pytest.approx(5.181, abs=1e-3)
    assert r["df2"] == pytest.approx(17.128, abs=1e-3)
    assert r["p"] == pytest.approx(0.01739, abs=1e-5)


def test_mann_whitney_sleep():
    res = run(SLEEP, {"group": "nominal"}, "mann_whitney", {"dependent": "extra", "group": "group"},
              {"method": "asymptotic"})
    r = main(res)[0]
    # R: wilcox.test(extra ~ group, data = sleep): W = 25.5, p-value = 0.06933
    assert r["U"] == pytest.approx(25.5)
    assert r["p"] == pytest.approx(0.06933, abs=1e-5)


def test_linear_regression_cars():
    res = run(CARS, {}, "linear_regression", {"dependent": "dist", "predictors": ["speed"]})
    coef = main(res)
    fit = table(res, "fit")[0]
    # R: lm(dist ~ speed, cars): -17.5791 (6.7584), 3.9324 (0.4155); R² 0.6511, F 89.57 on 1 and 48 df
    assert coef[0]["b"] == pytest.approx(-17.5791, abs=1e-4)
    assert coef[0]["se"] == pytest.approx(6.7584, abs=1e-4)
    assert coef[1]["b"] == pytest.approx(3.9324, abs=1e-4)
    assert coef[1]["se"] == pytest.approx(0.4155, abs=1e-4)
    assert fit["r2"] == pytest.approx(0.6511, abs=1e-4)
    assert fit["F"] == pytest.approx(89.57, abs=1e-2)
    assert (fit["df1"], fit["df2"]) == (1, 48)


def test_pearson_cars():
    res = run(CARS, {}, "correlation", {"variables": ["speed", "dist"]})
    r = main(res)[0]
    # R: cor.test(cars$speed, cars$dist): t = 9.464, df = 48, cor = 0.8068949, 95% CI 0.6816422 0.8862036
    assert r["r"] == pytest.approx(0.8068949, abs=1e-7)
    assert r["ci_lower"] == pytest.approx(0.6816422, abs=1e-6)
    assert r["ci_upper"] == pytest.approx(0.8862036, abs=1e-6)
    assert r["df"] == 48
    assert "does not show that one variable causes" in res["interpretation"]["plain"]


def test_chi_square_agresti():
    # R ?chisq.test example (Agresti 2007, p. 39): X-squared = 30.07, df = 2, p-value = 2.954e-07
    rows = [("F", "Democrat", 762), ("F", "Independent", 327), ("F", "Republican", 468),
            ("M", "Democrat", 484), ("M", "Independent", 239), ("M", "Republican", 477)]
    df = pd.DataFrame([(g, p) for g, p, n in rows for _ in range(n)], columns=["gender", "party"])
    res = run(df, {"gender": "binary", "party": "nominal"}, "chi_square", {"rows": "gender", "columns": "party"})
    r = main(res)[0]
    assert r["value"] == pytest.approx(30.07, abs=1e-2)
    assert r["df"] == 2
    assert r["p"] == pytest.approx(2.954e-07, rel=1e-3)


def test_fisher_tea_tasting():
    # R ?fisher.test TeaTasting: two-sided p-value = 0.4857
    df = pd.DataFrame([("Milk", "Milk")] * 3 + [("Milk", "Tea")] + [("Tea", "Milk")] + [("Tea", "Tea")] * 3,
                      columns=["truth", "guess"])
    res = run(df, {"truth": "binary", "guess": "binary"}, "fisher_exact", {"rows": "truth", "columns": "guess"})
    fisher = [r for r in main(res) if r["test"].startswith("Fisher")][0]
    assert fisher["p"] == pytest.approx(0.4857, abs=1e-4)
    assert any(a["status"] == "violated" for a in res["assumptions"])  # expected counts < 5


def test_cronbach_alpha_matches_formula_and_pingouin():
    import pingouin as pg

    rng = np.random.default_rng(3)
    latent = rng.normal(size=200)
    items = pd.DataFrame({f"Q{i}": np.clip(np.round(3 + latent + rng.normal(scale=1, size=200)), 1, 5)
                          for i in range(1, 6)})
    res = run(items, {c: "ordinal" for c in items}, "reliability", {"items": list(items.columns)})
    r = main(res)[0]
    expected, ci = pg.cronbach_alpha(items)
    assert r["alpha"] == pytest.approx(expected, abs=1e-10)
    assert r["ci_lower"] == pytest.approx(ci[0], abs=1e-3)
    assert "not whether they measure" in res["interpretation"]["plain"]


def test_rm_anova_matches_manual_computation():
    rng = np.random.default_rng(7)
    base = rng.normal(10, 2, 15)
    df = pd.DataFrame({"t1": base + rng.normal(0, 1, 15), "t2": base + 1 + rng.normal(0, 1, 15),
                       "t3": base + 1.5 + rng.normal(0, 1, 15)})
    res = run(df, {}, "rm_anova", {"within": ["t1", "t2", "t3"]})
    r = main(res)[0]
    y = df.to_numpy()
    n, k = y.shape
    gm = y.mean()
    ss_cond = n * ((y.mean(0) - gm) ** 2).sum()
    ss_subj = k * ((y.mean(1) - gm) ** 2).sum()
    ss_err = ((y - gm) ** 2).sum() - ss_cond - ss_subj
    F = (ss_cond / (k - 1)) / (ss_err / ((n - 1) * (k - 1)))
    assert r["F"] == pytest.approx(F, rel=1e-9)
    assert r["df"] == 2 and r["df_error"] == 28


def test_factorial_balanced_type2_equals_type3():
    rng = np.random.default_rng(11)
    a = np.repeat(["a1", "a2"], 20)
    b = np.tile(np.repeat(["b1", "b2"], 10), 2)
    y = rng.normal(size=40) + (a == "a2") * 1.0 + (b == "b2") * 0.5
    df = pd.DataFrame({"y": y, "A": a, "B": b})
    lv = {"A": "nominal", "B": "nominal"}
    r3 = main(run(df, lv, "factorial_anova", {"dependent": "y", "factors": ["A", "B"]}, {"ss_type": "3"}))
    r2 = main(run(df, lv, "factorial_anova", {"dependent": "y", "factors": ["A", "B"]}, {"ss_type": "2"}))
    for x, z in zip(r3, r2, strict=True):
        assert x["ss"] == pytest.approx(z["ss"], rel=1e-9)


# --------------------------------------------------------------------------- edge cases


def test_constant_outcome_is_rejected():
    df = pd.DataFrame({"y": [1.0] * 10, "g": ["a", "b"] * 5})
    with pytest.raises(AnalysisError, match="same value"):
        run(df, {"g": "nominal"}, "independent_t", {"dependent": "y", "group": "g"})


def test_ttest_with_three_groups_explains_problem():
    with pytest.raises(AnalysisError) as exc:
        run(PLANT, {"group": "nominal"}, "independent_t", {"dependent": "weight", "group": "group"})
    assert "ANOVA" in (exc.value.suggestion or "")


def test_singular_regression_detected():
    df = pd.DataFrame({"y": np.arange(20.0), "x1": np.arange(20.0) % 7, "x2": (np.arange(20.0) % 7) * 2})
    with pytest.raises(AnalysisError) as exc:
        run(df, {}, "linear_regression", {"dependent": "y", "predictors": ["x1", "x2"]})
    assert exc.value.code == "singular_model"


def test_missing_values_reported_not_silently_dropped():
    df = SLEEP.copy()
    df.loc[[0, 15], "extra"] = np.nan
    res = run(df, {"group": "nominal"}, "independent_t", {"dependent": "extra", "group": "group"})
    assert res["missing"]["excluded"] == 2
    assert any("2 of 20 rows were excluded" in n for n in res["notes"])


def test_perfect_correlation_and_tiny_p():
    x = np.arange(100.0)
    df = pd.DataFrame({"x": x, "y": 2 * x + 1})
    r = main(run(df, {}, "correlation", {"variables": ["x", "y"]}))[0]
    assert r["r"] == pytest.approx(1.0)
    assert r.get("ci_lower") is None  # undefined at |r| = 1, not fabricated


def test_p_value_formatting():
    from app.stats.base import fmt_p

    assert fmt_p(0.0000001) == "p < .001"
    assert fmt_p(0.0234) == "p = .023"
    assert fmt_p(0.0234, style="academic") == "p = 0.023"


def test_insufficient_group_size():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0, 5.0], "g": ["a", "a", "a", "a", "b"]})
    with pytest.raises(AnalysisError, match="at least 2"):
        run(df, {"g": "nominal"}, "independent_t", {"dependent": "y", "group": "g"})


def test_descriptives_skew_kurtosis_match_spss_formulas():
    from scipy import stats

    x = np.array([2, 4, 4, 5, 7, 9, 10, 15, 21, 30], dtype=float)
    res = run(pd.DataFrame({"x": x}), {}, "descriptives", {"variables": ["x"]}, {"statistics": ["n", "skewness",
                                                                                             "kurtosis", "sd"]})
    r = table(res, "descriptives")[0]
    assert r["skewness"] == pytest.approx(stats.skew(x, bias=False))
    assert r["kurtosis"] == pytest.approx(stats.kurtosis(x, bias=False))
    assert r["sd"] == pytest.approx(np.std(x, ddof=1))


def test_generated_code_runs_and_matches(tmp_path, monkeypatch):
    """The reproducible code must produce the same statistic as the engine."""
    SLEEP.to_parquet(tmp_path / "dataset.parquet")
    res = run(SLEEP, {"group": "nominal"}, "independent_t", {"dependent": "extra", "group": "group"},
              {"group_a": "1", "group_b": "2"})
    monkeypatch.chdir(tmp_path)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(res["_code"], {})  # noqa: S102 - our own generated code
    assert "-1.8608" in buf.getvalue()
