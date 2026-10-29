# StatEase Analytics

A web application for research statistics without code: **upload data → accept or choose a comparison → export an editable Word or Excel report.**

StatEase reads your Excel, CSV, JSON or Parquet data, detects what kind of variable each column is, suggests the analyses that fit your data, computes them with established statistical libraries (SciPy, statsmodels, pingouin), checks assumptions, writes plain-language and APA-style interpretations from the computed numbers, and generates `.docx`/`.xlsx` reports containing exactly the tables, charts and text you select.

Users can paste their **objectives of the study**; each objective is matched to the right analysis and becomes a report section. Tables and charts in the report can be renamed, reordered, edited and re-pointed at other groups or variables — values are recalculated from the data, and manually typed values are marked.

Optional **Advanced tools** (SQL workbench with database connections, a sandboxed Python console, and reproducible code for every result) are never required for the main workflow.

## Quick start

### Docker (simplest)

```bash
docker compose up --build
# open http://localhost:8000
```

Create an account on the sign-up page (the first account becomes the administrator). Metadata is stored in SQLite and files in a Docker volume. For PostgreSQL, see [Production](#production). To run without accounts on a single computer, set `STATEASE_AUTH_MODE=local`.

### Local development

Requirements: Python 3.12+ and Node.js 20+ (tested with Python 3.13.1 and Node 24).

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm ci
npm run dev                       # http://localhost:5173 (proxies /api to :8000)
```

`scripts/dev.ps1` (Windows) and `scripts/dev.sh` start both. Database migrations run automatically at startup (`alembic upgrade head`).

To serve the production build from the backend only: `cd frontend && npm run build`, then start uvicorn and open http://localhost:8000.

Try it without your own data: the landing page has three public demos (Fertilizer Trial on Pechay, Experimental Group Comparison, Survey Data Analysis) that work without signing in. After signing in, **Open a demo** creates a project with fictional sample data, finished analyses and an editable report built from the demo's objectives.

### Sign-in options

- **Email and password** — always available in the default `password` mode; passwords are hashed with scrypt; repeated failures are throttled.
- **Email verification** — sign-up e-mails a 6-digit code (15 minutes, 5 attempts, resend after 30 s); the account cannot sign in until the code is entered. Turn off with `STATEASE_REQUIRE_EMAIL_VERIFICATION=false`. Without SMTP the code is written to the server log.
- **Forgot password** — sends a one-hour, single-use link by e-mail (configure `STATEASE_SMTP_*`). Without SMTP the link is written to the server log so an administrator can pass it on. Resetting signs out all other sessions.
- **Continue with Google** — real OAuth 2.0 / OpenID Connect (authorization code flow with PKCE and a signed state cookie). Create an OAuth client of type *Web application* in Google Cloud Console, add the redirect URI `<STATEASE_PUBLIC_URL>/api/v1/auth/google/callback`, and set `STATEASE_GOOGLE_CLIENT_ID`, `STATEASE_GOOGLE_CLIENT_SECRET` and `STATEASE_PUBLIC_URL`. Until these are set the button is shown greyed out with a short note. The client secret stays on the server.
- If the installation was previously used in local mode, the **first account created takes over the existing local projects**, so no work is hidden.

## What is implemented

| Area | Status |
|---|---|
| Projects: create, rename, duplicate, archive/restore, delete (confirmed), metadata export, activity log | Implemented |
| Import: CSV, TSV, TXT, XLSX/XLSM, XLS, JSON, NDJSON, Parquet; worksheet choice; delimiter, header, encoding, skip rows, decimal comma, missing-value tokens | Implemented |
| Import validation: duplicate/empty column names (renamed and reported), ragged rows, mixed types, ambiguous dates (with suggested format), empty files, nested JSON (flattened or stored as text, always reported) | Implemented |
| Variable inference with explanation; editable level, label, category labels and order, missing-value codes, units; scale-item detection | Implemented |
| Data explorer: server-paged virtualized grid, sort, search, filter, column visibility; data-quality profile; versions & lineage; CSV/Parquet/original download | Implemented |
| Scale scores (mean/sum, reverse items) as a new dataset version | Implemented |
| Landing page, public demo previews, sign-up/login, Google sign-in, password reset, protected dashboard | Implemented |
| Recommendation engine (top suggestions first, e.g. "Compare Formulation 1 and Formulation 2"), "Run all recommended" | Implemented |
| Compare: two groups, several groups (with corrected post hoc tests) or two measurements (asks paired vs relationship); automatic test with optional override | Implemented |
| Objectives first: after import, paste the Statement of the Problem (with 1.1/1.2 sub-items) → checklist of the variables each objective needs → results and report contain only those analyses (profile, level/acceptability, most acceptable/ranking, difference, relationship, prediction, reliability) | Implemented |
| Report builder: checklist (include, reorder, rename), live document preview, table editor (columns, rows, cells), chart editor (type, labels, groups), recompute for other groups/variables, add from library, autosave | Implemented |
| 29 analyses (list below) with assumption checks, effect sizes, CIs, charts, interpretations, reproducible code | Implemented |
| Results workspace, editable interpretations | Implemented |
| Word and Excel export of the edited report (numbered tables and figures, method notes, manual-value markers; Excel with numeric cells and native editable charts), verified before download | Implemented |
| SQL workbench: project datasets (read-only DuckDB), SQLite, PostgreSQL, MySQL/MariaDB; schema browser; history; saved queries; format; export; save result as dataset with lineage | Implemented |
| Python console (subprocess sandbox, disabled by default) | Implemented |
| Roles analyst / developer / admin; per-user project isolation; audit log | Implemented |
| Background analysis jobs with progress; interrupted runs re-queued on restart | Implemented |

Planned work is listed in [docs/ROADMAP.md](docs/ROADMAP.md); nothing in the navigation is a placeholder.

### Analyses

- **Descriptive:** descriptive statistics (selectable statistics, presets, split by group), frequency tables, ranking of groups by mean ("most acceptable")
- **Compare groups:** two-group and multi-group comparisons across several measures (automatic test per measure), one-sample, independent-samples (Student and Welch), paired-samples t-tests
- **ANOVA:** one-way, Welch's, factorial (two/three-way, Type II/III), repeated-measures (Mauchly, Greenhouse–Geisser, Huynh–Feldt), mixed-design, ANCOVA; post hoc Tukey HSD, Games–Howell, Bonferroni/Holm
- **Correlation:** Pearson, Spearman, Kendall (matrix, CIs, multiple-comparison correction), partial correlation
- **Regression:** simple/multiple linear (VIF, Breusch–Pagan, Durbin–Watson, residual plots), binary logistic (odds ratios, pseudo-R², classification table, separation detection)
- **Nonparametric:** Mann–Whitney U, Wilcoxon signed-rank, Kruskal–Wallis (+ Dunn), Friedman (+ pairwise Wilcoxon)
- **Categorical:** chi-square independence and goodness-of-fit, Fisher's exact (2 × 2), one-sample proportion (exact binomial, Wilson CI)
- **Reliability:** Cronbach's α (Feldt CI), item–total correlations, α if item deleted, inter-item correlations
- **Assumption checks:** normality diagnostics, homogeneity of variance

Methods, formulas, assumptions and limitations: [docs/STATISTICAL_METHODS.md](docs/STATISTICAL_METHODS.md). The in-app **Methods guide** is generated from the same registry.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # 51 tests: R reference values, edge cases, auth (incl. Google flow), reports, full API workflow
cd backend && .venv/Scripts/ruff check app tests
cd frontend && npm run typecheck && npm test           # TypeScript strict + Vitest (14 tests)
cd frontend && npm run build && npx playwright test    # E2E against a running backend (E2E_BASE_URL, default :8000; E2E_SERVER_LOG = its log, read for the sign-up code; run it with STATEASE_SMTP_HOST= empty)
```

The Playwright suite runs the whole journey (landing page → sign up → enter the e-mailed code → upload from the dashboard → review variables → objectives step → Compare Formulation 1 vs 2 → enter objectives → generate report → rename a table and recalculate it for another group → download Word and Excel → reload) on a 1440 px desktop and a 390 px phone, plus public demos, login validation and password reset, horizontal-overflow checks at 360, 390, 768, 1024 and 1440 px, and accessible names.

Statistical results are verified against published R output for classic datasets (`sleep`, `PlantGrowth`, `cars`, Agresti's party-identification table, Fisher's tea-tasting table) and against independent computations; see `backend/tests/test_stats_reference.py`.

## Production

```bash
cp .env.example .env          # set STATEASE_SECRET_KEY and POSTGRES_PASSWORD
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

The first account registered becomes the administrator. Put the service behind HTTPS (reverse proxy). See [docs/SECURITY.md](docs/SECURITY.md) and [docs/DATABASE.md](docs/DATABASE.md) (including backup and restore).

## Performance

Measured with `python -m benchmarks.run_benchmark` on an Intel Core (4 cores / 8 threads), 16.8 GB RAM, Windows 11, Python 3.13.1:

| Step | 100,000 rows | 1,000,000 rows (37 MB CSV) |
|---|---:|---:|
| Upload + preview | 0.98 s | 1.29 s |
| Import (convert to Parquet + full profile) | 1.14 s | 1.65 s |
| Sorted page from the middle of the data | 0.13 s | 0.30 s |
| Descriptives (3 variables) | 0.15 s | 0.89 s |
| Independent t-test | 0.19 s | 1.57 s |
| One-way ANOVA (with post hoc) | 1.01 s | 3.09 s |
| Correlation matrix | 0.16 s | 1.13 s |
| Chi-square | 0.30 s | 2.71 s |
| Linear regression | 1.82 s | 1.33 s |
| Mann–Whitney U | 0.22 s | 1.94 s |
| DOCX / XLSX export (7 analyses with charts) | 3.8 s / 3.7 s | 3.8 s / 3.5 s |
| Peak process memory | 461 MB | 821 MB |

Data is stored as Parquet; previews are paged server-side through DuckDB; analyses load only the columns they need. Most procedures need the observations in memory, so the practical limit is your RAM (default cap `STATEASE_ANALYSIS_MAX_ROWS=5,000,000`). Shapiro–Wilk is skipped above 5,000 observations, and this is reported. Excel files are limited to 100 MB because Excel parsing is in-memory; large data should be imported as CSV or Parquet. No approximate algorithms are substituted silently.

## Project layout

```
backend/   FastAPI app (app/), Alembic migrations, tests, benchmarks
  app/api/       REST endpoints (/api/v1/…)
  app/data/      import, type inference, Parquet/DuckDB access, profiling
  app/stats/     analysis registry, procedures, recommendations, code generation
  app/reports/   DOCX/XLSX builders and chart rendering
  app/dev/       SQL engine, sample database, Python sandbox
frontend/  React + TypeScript + Vite + Tailwind; e2e/ Playwright tests
docs/      architecture, methods, database, exports, security, roadmap
```
