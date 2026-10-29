# Statistical Methods

Principles that apply to every analysis:

- **Established libraries.** Calculations use SciPy, statsmodels and pingouin; hand-written formulas (effect sizes, Dunn's test, Cronbach's α, Huynh–Feldt ε) are tested against those libraries or published values.
- **Full precision internally.** Values are rounded only for display and export (project setting: decimals, p-value style).
- **p-values.** Three decimals; below .001 shown as *p* < .001, never *p* = .000. APA style omits the leading zero for p and for statistics bounded by ±1.
- **Significance level.** α is a project setting (default .05) and is applied consistently; significance is always stated in text, not only through colour.
- **Missing data.** Listwise deletion over the variables used in each analysis, unless stated otherwise (descriptives: available cases per variable; correlation: pairwise by default). The number of excluded rows is always reported. Declared missing-value codes (e.g. 99) are converted to missing when data is read; the stored data is never altered.
- **No silent substitution.** If an assumption appears violated, a warning names the alternative (e.g. Welch's ANOVA, Mann–Whitney U); the selected test is never replaced automatically.
- **Normality tests.** Shapiro–Wilk is reported for n ≤ 5,000 (configurable). For n > 200, a significant result is shown as information rather than a violation, because trivial departures become significant at large n; Q–Q plots are provided.
- **Ordinal ratings.** Ordinal variables may be analysed numerically where the role allows it (as is common for Likert data); text-labelled ordered categories are then scored 1…k in their declared order, and this is noted in the result.
- **Errors.** Analyses that cannot be computed reliably (constant variables, empty groups, perfect collinearity, perfect separation, too few cases) stop with an explanation and, where possible, a suggested alternative.
- **Causality.** Correlation and regression interpretations state that results show association, not causation.

## Comparisons and test selection

`compare_two_groups` (two independent groups, e.g. Formulation 1 vs Formulation 2) and `compare_groups` (three or more) compare every selected measure in one table. The test is chosen per measure and the reason is printed under the table:

- ordinal measure → Mann–Whitney U / Kruskal–Wallis;
- smallest group under 30 and a group clearly non-normal (Shapiro–Wilk) → rank-based test;
- otherwise → Welch's t-test (two groups); one-way ANOVA, or Welch's ANOVA when Levene's test (median-centred) is significant (three or more).

With three or more groups, pairwise differences are reported only through corrected post hoc tests (Tukey HSD, Games–Howell, or Dunn with Holm correction) and only for measures whose overall test is significant. Testing several measures is not adjusted by default; Holm or Bonferroni adjustment is an option. Users can override the test. When two measurement columns are compared, StatEase asks whether they come from the same participants: if yes, a paired t-test or Wilcoxon signed-rank test is used (never an independent-groups test); if not, a correlation is used.

The same functions are verified against R: Welch's t for the `sleep` data (t = −1.8608, df = 17.776, p = .07939) and one-way ANOVA with Tukey HSD for `PlantGrowth`.

## Objectives of the study

Objectives are parsed with fixed rules (no AI): wording decides the intent (describe, compare, relationship, predict, reliability, profile) and column names, labels and category values in the sentence decide the variables and groups ("Formulation 1" restricts a descriptive table to that group). The statistical method is then chosen from the data as above. If the needed columns cannot be identified, the objective is shown with a short question and column selectors instead of a guessed analysis.

## Procedures

| Analysis | Implementation | Effect size / extras | Assumption checks |
|---|---|---|---|
| Descriptive statistics | numpy/scipy; SD with n − 1; quartiles by linear interpolation; t-based CI | Skewness G1 and excess kurtosis G2 (bias-corrected, as in SPSS/JASP) with SEs | — |
| Frequencies | counts, %, valid %, cumulative % (ordered categories only) | mode | — |
| One-sample t | `scipy.stats.ttest_1samp` | Cohen's d with normal-approximation CI | normality |
| Independent t | `scipy.stats.ttest_ind`; Welch (default) and/or Student | Cohen's d (pooled SD), Hedges' g, CI for d | Levene (median-centred), normality per group, independence note |
| Paired t | `scipy.stats.ttest_rel` on complete pairs | Cohen's dz | normality of differences |
| One-way ANOVA | sums of squares computed directly; F from `scipy.stats.f` | η², ω² | Levene, residual normality; post hoc Tukey HSD (`scipy.stats.tukey_hsd`, Tukey–Kramer), Games–Howell (pingouin), Bonferroni/Holm t-tests. Post hoc runs only when the omnibus test is significant unless requested. |
| Welch's ANOVA | `pingouin.welch_anova` | η² (descriptive) | Games–Howell post hoc |
| Factorial ANOVA | statsmodels OLS with sum-to-zero coding, `anova_lm` Type III (default) or II | partial η² | Levene across cells, residual normality, interaction plot; empty cells reported |
| Repeated-measures ANOVA | `pingouin.rm_anova` | partial η², generalized η² | Mauchly's test; Greenhouse–Geisser and Huynh–Feldt corrections (GG used in interpretation if ε < .75, else HF); Holm-adjusted paired comparisons |
| Mixed-design ANOVA | `pingouin.mixed_anova` | partial η² | sphericity, Levene; GG-corrected p for within effects |
| ANCOVA | OLS, Type III, sum-to-zero coding | partial η²; adjusted means at covariate means | homogeneity of regression slopes (factor × covariate), residual variance, normality |
| Correlation | `scipy.stats.pearsonr` / `spearmanr` / `kendalltau` (τ-b) | Pearson CI: Fisher z (exact SciPy). Spearman CI: Fisher z with Bonett–Wright variance (approximate, disclosed). No CI for Kendall. | linearity/outlier notes, normality; optional Holm/Bonferroni/FDR |
| Partial correlation | `pingouin.partial_corr` | zero-order r for comparison | — |
| Linear regression | `statsmodels.OLS`; categorical predictors dummy-coded vs. first category | R², adjusted R², standardised β, RMSE, AIC | VIF, Breusch–Pagan, Durbin–Watson, residual normality, residual and Q–Q plots; rank check for singular designs |
| Logistic regression | `statsmodels.Logit` | odds ratios with CIs, McFadden and Nagelkerke R², classification table | separation detection, convergence, events per predictor, VIF |
| Mann–Whitney U | `scipy.stats.mannwhitneyu` (auto/exact/asymptotic with continuity correction) | rank-biserial r | — |
| Wilcoxon signed-rank | `scipy.stats.wilcoxon`, zero differences dropped | matched-pairs rank-biserial r | — |
| Kruskal–Wallis | `scipy.stats.kruskal` (tie-corrected) | ε² | Dunn's test with tie correction, Holm/Bonferroni |
| Friedman | `scipy.stats.friedmanchisquare` | Kendall's W | pairwise Wilcoxon, adjusted |
| Chi-square independence | `scipy.stats.chi2_contingency`; likelihood-ratio G | Cramér's V, φ (2 × 2) | expected counts (< 5 in > 20 % of cells or any < 1 → violation); Fisher's exact reported automatically for 2 × 2 tables with small expected counts; adjusted residuals |
| Fisher's exact | `scipy.stats.fisher_exact` (2 × 2) | sample odds ratio | — |
| Goodness of fit | `scipy.stats.chisquare`, equal or user-given proportions | Cohen's w | expected counts |
| Proportion test | `scipy.stats.binomtest` (exact) | Wilson score CI | — |
| Cronbach's α | formula; Feldt CI (matches pingouin) | standardised α, mean inter-item r | corrected item–total r, α if deleted, reverse-scoring support; notes that α ≠ validity or unidimensionality |
| Normality diagnostics | Shapiro–Wilk, D'Agostino K² | skewness, kurtosis with SEs | histograms, Q–Q plots |
| Homogeneity of variance | Levene (mean), Brown–Forsythe (median), Bartlett | — | — |

Nonparametric results are described as differences in distributions or tendencies (stochastic ordering), not as differences in medians, unless distribution shapes are equal.

Effect-size labels use Cohen (1988) conventions (d: .2/.5/.8; r: .1/.3/.5; η²: .01/.06/.14; Cramér's V scaled by the table's degrees of freedom). They are rough guides, not substantive judgements.

## Verification

`backend/tests/test_stats_reference.py` compares results with R output to the published precision:

| Check | Reference |
|---|---|
| Student and Welch t, df, p, CI | `t.test(extra ~ group, sleep)` |
| Paired t, CI | `t.test(..., paired = TRUE)` on `sleep` |
| One-way ANOVA F, SS, p; Tukey HSD p-values | `aov`, `TukeyHSD` on `PlantGrowth` |
| Welch ANOVA | `oneway.test` on `PlantGrowth` |
| Kruskal–Wallis | `kruskal.test` on `PlantGrowth` |
| Mann–Whitney (W = U) | `wilcox.test` on `sleep` |
| Linear regression B, SE, R², F | `lm(dist ~ speed, cars)` |
| Pearson r, CI | `cor.test` on `cars` |
| Chi-square | `?chisq.test` example (Agresti) |
| Fisher's exact | `?fisher.test` TeaTasting |
| Cronbach's α, CI | pingouin |
| RM ANOVA F | manual sums of squares |
| Type II = Type III in balanced designs | statsmodels |

Edge cases tested: constant outcome, too many groups for a t-test, singular regression, missing values reported, perfect correlation (no fabricated CI), tiny p-values, group with one observation, and generated code reproducing the engine's statistic.
