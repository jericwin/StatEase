# Roadmap

## Completed

| Phase | Delivered |
|---|---|
| 1 Foundation | FastAPI + SQLAlchemy + Alembic, React/TS/Vite/Tailwind shell (desktop, tablet, mobile; light/dark), projects, auth modes, tests and scripts |
| 2 Data import | CSV/TSV/Excel/JSON/Parquet, wizard with validation, inference, variable editor, profiling, Parquet persistence, versions |
| 3 Statistical engine | Descriptives, t-tests, correlation, one-/two-way ANOVA, assumption checks, R reference tests |
| 4 Guided analysis | Recommendations, checklist, role-based variable assignment, saved configurations, multiple results, interpretations |
| 5 Advanced statistics | RM/mixed ANOVA, Welch ANOVA, ANCOVA, post hoc, linear/logistic regression, nonparametric, categorical, reliability |
| 6 Reporting | DOCX/XLSX with checklists, presets, charts, verification |
| 7 Large data | Parquet + DuckDB paging, column-selective loads, background jobs with progress, virtualized grid, limits, benchmarks |
| 8 Hardening | E2E (desktop + mobile, five widths), access control, error handling, backup docs |
| Developer mode | SQL workbench (DuckDB/SQLite/PostgreSQL/MySQL), connections, saved queries/history, save-as-dataset lineage, Python sandbox, reproducible code |
| Second release | Landing page and public demos, email/password + Google sign-in, password reset, dashboard, Compare, objectives → report, editable report tables/charts with recomputation, report-based Word/Excel export with native Excel charts; API Explorer removed |

## Planned (not yet available in the app)

- Exploratory factor analysis and principal component analysis (with KMO/Bartlett diagnostics).
- Multiple-response frequency summaries.
- Two-proportion tests and McNemar's test.
- Ordinal and multinomial logistic regression; robust (HC3) standard errors as an option.
- Simple-effects analysis for significant interactions; estimated marginal means for factorial ANOVA.
- Fisher's exact test for tables larger than 2 × 2 (network algorithm or Monte Carlo, clearly labelled).
- Native, editable Excel charts in addition to images.
- Process-level isolation of analysis jobs (worker processes) so running calculations can be cancelled immediately.
- Container-based sandbox runner for the Python console.
- Project sharing between accounts.
- Survival analysis and cluster analysis, only with validated implementations.

## Known limitations

- Analyses load the columns they use into memory; practical size is bounded by RAM (see README benchmarks).
- Excel import is in-memory (100 MB default limit).
- Cancelling a run that is already computing discards its result but does not interrupt the calculation.
- Importing files as tables into PostgreSQL/MySQL connections is not supported (SQLite only).
