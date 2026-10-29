"""Linear (simple and multiple) and binary logistic regression."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

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
    sig_phrase,
)
from .common import normality_assessment, qq_data, scatter_data


def _opts(spec, config):
    return {**spec.defaults(), **{k: v for k, v in (config.get("options") or {}).items() if v is not None}}


def design(ctx: Context, df: pd.DataFrame, predictors: list[str], res: Result) -> tuple[pd.DataFrame, dict[str, str]]:
    """Numeric predictors as-is; categorical predictors dummy-coded against their first category."""
    cols: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for p in predictors:
        meta = ctx.meta(p)
        if meta.level in {"nominal", "binary"} or (meta.level == "ordinal" and meta.data_type == "string"):
            cat = ctx.categorical(df, p).cat.remove_unused_categories()
            if len(cat.cat.categories) < 2:
                raise AnalysisError(f"Predictor '{ctx.label(p)}' has only one category in the analysed data.")
            if len(cat.cat.categories) > 20:
                raise AnalysisError(f"Predictor '{ctx.label(p)}' has {len(cat.cat.categories)} categories; too many "
                                    "for dummy coding.")
            ref = cat.cat.categories[0]
            for lv in cat.cat.categories[1:]:
                key = f"x{len(cols)}"
                cols[key] = (cat == lv).astype(float)
                labels[key] = f"{ctx.label(p)}: {lv} (vs {ref})"
            res.notes.append(f"'{ctx.label(p)}' is categorical and was dummy-coded with '{ref}' as the reference group.")
        else:
            key = f"x{len(cols)}"
            cols[key] = ctx.numeric(df, p)
            labels[key] = ctx.label(p)
    X = pd.DataFrame(cols, index=df.index)
    return X, labels


def _check_rank(X: pd.DataFrame, labels: dict[str, str]) -> None:
    const = [labels[c] for c in X.columns if X[c].std() == 0]
    if const:
        raise AnalysisError(f"Predictor(s) with no variation: {', '.join(const)}.")
    mat = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    if np.linalg.matrix_rank(mat) < mat.shape[1]:
        raise AnalysisError("The predictors are perfectly collinear (one is an exact combination of others), so the "
                            "model cannot be estimated.", code="singular_model",
                            suggestion="Remove redundant predictors, e.g. a total score together with all its items.")


def _vif(X: pd.DataFrame) -> dict[str, float]:
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    if X.shape[1] < 2:
        return {}
    mat = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    return {c: float(variance_inflation_factor(mat, i + 1)) for i, c in enumerate(X.columns)}


def run_linear(ctx: Context, config: dict[str, Any]) -> Result:
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import het_breuschpagan
    from statsmodels.stats.stattools import durbin_watson

    res = Result(LINEAR, config, ctx)
    o = _opts(LINEAR, config)
    level = float(o["ci_level"])
    dv = assigned(config, "dependent")[0]
    preds = assigned(config, "predictors")
    df = listwise(ctx.frame([dv, *preds]), [dv, *preds], res)
    y = ctx.numeric(df, dv)
    if y.std() == 0:
        raise AnalysisError(f"The outcome '{ctx.label(dv)}' does not vary, so regression is not possible.")
    X, labels = design(ctx, df, preds, res)
    if len(df) < X.shape[1] + 2:
        raise AnalysisError(f"Only {len(df)} complete cases for {X.shape[1]} predictor terms; more cases are needed.")
    _check_rank(X, labels)
    model = sm.OLS(y.to_numpy(float), sm.add_constant(X.to_numpy(float), has_constant="add")).fit()
    res.n = int(model.nobs)
    ci = model.conf_int(alpha=1 - level)
    sd_y = float(y.std(ddof=1))
    rows = [{"term": "(Intercept)", "b": model.params[0], "se": model.bse[0], "beta": None, "t": model.tvalues[0],
             "p": model.pvalues[0], "ci_lower": ci[0, 0], "ci_upper": ci[0, 1]}]
    vif = _vif(X)
    for i, c in enumerate(X.columns, start=1):
        beta = model.params[i] * X[c].std(ddof=1) / sd_y
        rows.append({"term": labels[c], "b": model.params[i], "se": model.bse[i], "beta": beta, "t": model.tvalues[i],
                     "p": model.pvalues[i], "ci_lower": ci[i, 0], "ci_upper": ci[i, 1], "vif": vif.get(c)})
    res.table("main", "main", f"Coefficients: {ctx.label(dv)}",
              [col("term", "Predictor", "text"), col("b", "B", "num"), col("se", "SE", "num"),
               col("beta", "β (standardised)", "num", "effect"), col("t", "t", "stat", "statistic"),
               col("p", "p", "p", "p"), col("ci_lower", f"{level:.0%} CI lower", "num", "ci"),
               col("ci_upper", f"{level:.0%} CI upper", "num", "ci"), col("vif", "VIF", "num", "assumptions")],
              rows, ["B: unstandardised coefficient. β: standardised coefficient."])
    rmse = math.sqrt(model.mse_resid)
    res.table("fit", "main", "Model Summary",
              [col("r", "R", "num"), col("r2", "R²", "num", "effect"), col("adj_r2", "Adjusted R²", "num", "effect"),
               col("rmse", "RMSE", "num"), col("F", "F", "stat", "statistic"), col("df1", "df1", "int", "df"),
               col("df2", "df2", "int", "df"), col("p", "p", "p", "p"), col("n", "N", "int", "n"),
               col("aic", "AIC", "num")],
              [{"r": math.sqrt(max(model.rsquared, 0)), "r2": model.rsquared, "adj_r2": model.rsquared_adj, "rmse": rmse,
                "F": model.fvalue, "df1": int(model.df_model), "df2": int(model.df_resid), "p": model.f_pvalue,
                "n": res.n, "aic": model.aic}])
    resid, fitted = model.resid, model.fittedvalues
    normality_assessment(res, resid, ctx.label(dv), what="residuals")
    bp = het_breuschpagan(resid, model.model.exog)
    ok = bp[1] >= ctx.alpha
    res.assumption("Constant residual variance (Breusch–Pagan)", "ok" if ok else "violated",
                   f"LM = {bp[0]:.2f}, {fmt_p(bp[1], ctx.p_style)}. " + (
                       "No evidence of heteroscedasticity." if ok else
                       "Residual spread changes with the fitted values; standard errors may be inaccurate. Consider "
                       "robust (HC3) standard errors or transforming the outcome."), statistic=bp[0], p=bp[1])
    dw = durbin_watson(resid)
    res.assumption("Independence of residuals (Durbin–Watson)", "ok" if 1.5 <= dw <= 2.5 else "warning",
                   f"DW = {dw:.2f} (values near 2 indicate no first-order autocorrelation; only meaningful if rows have "
                   "a natural order such as time).", statistic=dw)
    if vif:
        worst = max(vif.values())
        res.assumption("Multicollinearity (VIF)", "ok" if worst < 5 else "warning" if worst < 10 else "violated",
                       f"Largest VIF = {worst:.2f}. " + ("Acceptable." if worst < 5 else
                                                       "Predictors overlap strongly; individual coefficients are "
                                                       "unstable and hard to interpret."), statistic=worst)
    res.assumption("Linearity", "info", "Check the residuals-vs-fitted plot: a curved pattern means a straight-line "
                   "model is not adequate for at least one predictor.")
    if len(resid) < 20 * X.shape[1] and len(resid) < 10 * X.shape[1]:
        res.warn(f"Only {len(resid)} cases for {X.shape[1]} predictor terms; estimates may be unstable.")
    rd, note = scatter_data(fitted, resid, fit=False)
    rd["zero_line"] = True
    res.chart("resid", "scatter", "Residuals vs fitted values", rd, "Fitted values", "Residuals",
              "Residuals should scatter randomly around zero with constant spread.", note)
    res.chart("qq", "qq", "Normal Q–Q plot of residuals", qq_data(resid), "Theoretical quantiles", "Residuals",
              "Checks the normality of residuals.")
    if X.shape[1] == 1:
        sd, note = scatter_data(X.iloc[:, 0].to_numpy(float), y.to_numpy(float))
        res.chart("scatter", "scatter", f"{ctx.label(dv)} vs {labels[X.columns[0]]}", sd, labels[X.columns[0]],
                  ctx.label(dv), "Observed data with the fitted regression line.", note)
    sig, phrase = sig_phrase(model.f_pvalue, ctx.alpha)
    d = ctx.decimals
    sig_preds = [r for r in rows[1:] if r["p"] < ctx.alpha]
    res.summary = {"statistic": model.fvalue, "df": [int(model.df_model), int(model.df_resid)], "p": model.f_pvalue,
                   "effect": model.rsquared, "effect_name": "R²", "significant": sig}
    pred_text = "; ".join(
        f"{r['term']} (B = {fmt_num(r['b'], d)}, β = {fmt_num(r['beta'], 2)}, {fmt_p(r['p'], ctx.p_style)})"
        for r in sig_preds)
    res.interpretation = {
        "plain": (f"Together, the predictors explain {model.rsquared:.0%} of the variation in {ctx.label(dv)}; the model "
                  f"is {phrase}. " + (
                      "Significant predictors: " + ", ".join(
                          f"{r['term']} ({'higher' if r['b'] > 0 else 'lower'} {ctx.label(dv)} as it increases)"
                          for r in sig_preds) + "." if sig_preds else "No individual predictor was significant.")
                  + " Regression on observational data shows association, not causation."),
        "technical": (f"Linear regression of {ctx.label(dv)} on {len(preds)} predictor(s): R² = {model.rsquared:.3f}, "
                      f"adjusted R² = {model.rsquared_adj:.3f}, F({int(model.df_model)}, {int(model.df_resid)}) = "
                      f"{model.fvalue:.2f}, {fmt_p(model.f_pvalue, ctx.p_style)}, n = {res.n}."
                      + (f" Significant predictors: {pred_text}." if sig_preds else "")),
    }
    return res


def code_linear(config, v):
    dv, preds = assigned(config, "dependent")[0], assigned(config, "predictors")
    rhs = " + ".join(f"C(Q({p!r}))" if v.get(p) and v[p].level in {"nominal", "binary"} else f"Q({p!r})" for p in preds)
    return (codegen.prelude(v, [dv, *preds], ["import statsmodels.formula.api as smf"])
            + codegen.numeric_ordinal_note(v, [dv, *preds])
            + f"model = smf.ols(\"Q({dv!r}) ~ {rhs}\", data=df).fit()\nprint(model.summary())\n")


def run_logistic(ctx: Context, config: dict[str, Any]) -> Result:
    import statsmodels.api as sm

    res = Result(LOGIT, config, ctx)
    o = _opts(LOGIT, config)
    level = float(o["ci_level"])
    dv = assigned(config, "dependent")[0]
    preds = assigned(config, "predictors")
    df = listwise(ctx.frame([dv, *preds]), [dv, *preds], res)
    ycat = ctx.categorical(df, dv).cat.remove_unused_categories()
    cats = [str(c) for c in ycat.cat.categories]
    if len(cats) != 2:
        raise AnalysisError(f"Logistic regression needs an outcome with exactly two categories; '{ctx.label(dv)}' has "
                            f"{len(cats)}.")
    event = o.get("event") if o.get("event") in cats else cats[1]
    ref = [c for c in cats if c != event][0]
    y = (ycat.astype(str) == event).astype(float).to_numpy()
    X, labels = design(ctx, df, preds, res)
    _check_rank(X, labels)
    events = int(y.sum())
    if min(events, len(y) - events) < 10 * X.shape[1]:
        res.warn(f"Only {min(events, len(y) - events)} cases in the smaller outcome group for {X.shape[1]} predictor "
                 "terms (fewer than 10 per term); estimates may be biased.")
    try:
        model = sm.Logit(y, sm.add_constant(X.to_numpy(float), has_constant="add")).fit(disp=0, maxiter=200)
    except Exception as exc:  # noqa: BLE001 - PerfectSeparationError and LinAlgError
        if "separation" in str(exc).lower() or "singular" in str(exc).lower():
            raise AnalysisError("The predictors perfectly separate the two outcome groups, so the coefficients are "
                                "infinite.", code="perfect_separation",
                                suggestion="Remove or merge the predictor that perfectly predicts the outcome.") from exc
        raise
    if not model.mle_retvals.get("converged", True):
        res.warn("The model did not fully converge; estimates may be unreliable (possible quasi-separation).")
    res.n = int(model.nobs)
    ci = model.conf_int(alpha=1 - level)
    rows = []
    for i, name in enumerate(["(Intercept)", *[labels[c] for c in X.columns]]):
        b = model.params[i]
        rows.append({"term": name, "b": b, "se": model.bse[i], "z": model.tvalues[i], "p": model.pvalues[i],
                     "or": math.exp(b) if abs(b) < 700 else None,
                     "or_lower": math.exp(ci[i, 0]) if abs(ci[i, 0]) < 700 else None,
                     "or_upper": math.exp(ci[i, 1]) if abs(ci[i, 1]) < 700 else None})
    res.table("main", "main", f"Logistic Regression: P({ctx.label(dv)} = {event})",
              [col("term", "Predictor", "text"), col("b", "B", "num"), col("se", "SE", "num"),
               col("z", "Wald z", "stat", "statistic"), col("p", "p", "p", "p"), col("or", "Odds ratio", "num", "effect"),
               col("or_lower", f"OR {level:.0%} CI lower", "num", "ci"), col("or_upper", f"OR {level:.0%} CI upper", "num", "ci")],
              rows, [f"Modelled outcome: '{event}' (reference '{ref}'). Odds ratio > 1 means higher odds of '{event}'."])
    n = model.nobs
    ll, ll0 = model.llf, model.llnull
    cox = 1 - math.exp((2 / n) * (ll0 - ll))
    nag = cox / (1 - math.exp((2 / n) * ll0))
    pred = (model.predict() >= 0.5).astype(float)
    acc = float((pred == y).mean())
    res.table("fit", "main", "Model Fit",
              [col("chi2", "Likelihood-ratio χ²", "stat", "statistic"), col("df", "df", "int", "df"), col("p", "p", "p", "p"),
               col("mcfadden", "McFadden R²", "num", "effect"), col("nagelkerke", "Nagelkerke R²", "num", "effect"),
               col("aic", "AIC", "num"), col("accuracy", "Correctly classified", "pct"), col("n", "N", "int", "n")],
              [{"chi2": model.llr, "df": int(model.df_model), "p": model.llr_pvalue, "mcfadden": model.prsquared,
                "nagelkerke": nag, "aic": model.aic, "accuracy": acc * 100, "n": int(n)}],
              ["Classification uses a 0.5 probability cut-off."])
    tp = int(((pred == 1) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    res.table("classification", "assumptions", "Classification Table",
              [col("observed", "Observed", "text"), col("pred_ref", f"Predicted {ref}", "int"),
               col("pred_event", f"Predicted {event}", "int"), col("pct", "Percent correct", "pct")],
              [{"observed": ref, "pred_ref": tn, "pred_event": int((y == 0).sum()) - tn,
                "pct": tn / max((y == 0).sum(), 1) * 100},
               {"observed": event, "pred_ref": int((y == 1).sum()) - tp, "pred_event": tp,
                "pct": tp / max((y == 1).sum(), 1) * 100}])
    vif = _vif(X)
    if vif:
        worst = max(vif.values())
        res.assumption("Multicollinearity (VIF)", "ok" if worst < 5 else "warning",
                       f"Largest VIF = {worst:.2f}.", statistic=worst)
    res.assumption("Linearity of the logit", "info", "Numeric predictors are assumed to have a linear relationship "
                   "with the log-odds of the outcome.")
    sig, phrase = sig_phrase(model.llr_pvalue, ctx.alpha)
    sig_preds = [r for r in rows[1:] if r["p"] < ctx.alpha and r["or"] is not None]
    res.summary = {"statistic": model.llr, "df": int(model.df_model), "p": model.llr_pvalue, "effect": nag,
                   "effect_name": "Nagelkerke R²", "significant": sig}
    res.interpretation = {
        "plain": (f"The model {'significantly' if sig else 'does not significantly'} predict"
                  f"{'s' if sig else ''} whether {ctx.label(dv)} is '{event}'. "
                  + ("; ".join(f"{r['term']} {'increases' if r['or'] > 1 else 'decreases'} the odds "
                               f"(odds ratio {r['or']:.2f})" for r in sig_preds) + "." if sig_preds else
                     "No individual predictor was significant.")),
        "technical": (f"Binary logistic regression (event = '{event}'): χ²({int(model.df_model)}) = {model.llr:.2f}, "
                      f"{fmt_p(model.llr_pvalue, ctx.p_style)}, Nagelkerke R² = {nag:.3f}, {acc:.1%} correctly "
                      f"classified, n = {int(n)}."),
    }
    return res


def code_logistic(config, v):
    dv, preds = assigned(config, "dependent")[0], assigned(config, "predictors")
    event = _opts(LOGIT, config).get("event") or "<event category>"
    rhs = " + ".join(f"C(Q({p!r}))" if v.get(p) and v[p].level in {"nominal", "binary"} else f"Q({p!r})" for p in preds)
    return (codegen.prelude(v, [dv, *preds], ["import statsmodels.formula.api as smf"])
            + f"df['event'] = (df[{dv!r}].astype(str) == {str(event)!r}).astype(int)\n"
            f"model = smf.logit(\"event ~ {rhs}\", data=df).fit()\nprint(model.summary())\nprint(np.exp(model.params))\n")


CI = Option("ci_level", "Confidence level", "number", 0.95, min=0.5, max=0.999, advanced=True)
LINEAR = register(AnalysisSpec(
    id="linear_regression", name="Linear Regression", plain_name="Predict a numeric outcome from other variables",
    category="regression",
    description="Estimates how a numeric outcome changes with one or more predictors (simple or multiple regression).",
    when_to_use="A numeric outcome and one or more predictors; categorical predictors are dummy-coded.",
    roles=[Role("dependent", "Outcome", "The numeric variable to predict.", SCALE_LEVELS, plain="What do you want to predict?"),
           Role("predictors", "Predictors", "Variables used to predict the outcome.", SCALE_LEVELS | CATEGORICAL_LEVELS,
                1, 30, plain="Using which variables?")],
    options=[CI],
    run=run_linear, code=code_linear,
    assumptions=["Linear relationships.", "Independent residuals.", "Constant residual variance.",
                 "Approximately normal residuals.", "No severe multicollinearity."],
    method="Ordinary least squares (statsmodels OLS). Diagnostics: Breusch–Pagan, Durbin–Watson, VIF, Shapiro–Wilk "
           "on residuals, residual and Q–Q plots.",
    limitations=["Coefficients describe associations; causal claims need an appropriate design."],
))
LOGIT = register(AnalysisSpec(
    id="logistic_regression", name="Binary Logistic Regression", plain_name="Predict a yes/no outcome",
    category="regression",
    description="Models the probability of one of two outcomes (e.g. pass/fail) from predictors.",
    when_to_use="An outcome with exactly two categories.",
    roles=[Role("dependent", "Outcome (two categories)", "The binary outcome.", CATEGORICAL_LEVELS),
           Role("predictors", "Predictors", "", SCALE_LEVELS | CATEGORICAL_LEVELS, 1, 30)],
    options=[Option("event", "Category to model", "level", None, depends_on="dependent",
                    help="The outcome category whose probability is modelled (default: the second category)."), CI],
    run=run_logistic, code=code_logistic,
    assumptions=["Independent observations.", "Linearity of the logit for numeric predictors.",
                 "No perfect separation.", "Adequate events per predictor."],
    method="Maximum-likelihood logistic regression (statsmodels Logit); Wald tests, odds ratios, likelihood-ratio "
           "test, McFadden and Nagelkerke pseudo-R².",
))
