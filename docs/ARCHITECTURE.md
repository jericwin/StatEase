# Architecture

## Overview

```
Browser (React SPA)  ──HTTP/JSON──▶  FastAPI (/api/v1)
                                       ├─ SQLAlchemy ──▶ metadata DB (SQLite | PostgreSQL)
                                       ├─ Polars / DuckDB ──▶ Parquet files (datasets)
                                       ├─ Statistical engine (SciPy, statsmodels, pingouin)
                                       ├─ Report builders (python-docx, openpyxl, matplotlib)
                                       ├─ Thread-pool job runner (analysis runs)
                                       ├─ SQL engine (DuckDB workspace, SQLite, PostgreSQL, MySQL)
                                       └─ Python sandbox (separate process)
```

One process serves both the API and the built frontend. No external or paid services are used.

## Backend (`backend/app`)

| Module | Responsibility |
|---|---|
| `config.py` | Settings from `STATEASE_*` environment variables (pydantic-settings). |
| `db.py`, `models.py` | SQLAlchemy 2 models; JSONB on PostgreSQL; UTC-aware timestamps. Migrations in `alembic/`. |
| `deps.py`, `security.py` | Current user (local mode or bearer token), ownership checks, roles, audit log; scrypt password hashes, HMAC-signed tokens, Fernet-encrypted connection secrets. |
| `errors.py` | Uniform error body `{"error": {"code", "message", "details"}}`. |
| `storage.py` | Relative storage paths, safe file names, path-traversal protection. |
| `data/importer.py` | Staged uploads, format readers, validation, streaming conversion to Parquet. |
| `data/inference.py` | Measurement-level inference with explanations; questionnaire-scale detection. |
| `data/store.py` | Column-selective loading (missing codes applied on read), DuckDB-paged previews, profiling. |
| `services.py` | Dataset creation and versioning (shared by import, SQL, transforms, demo). |
| `stats/base.py` | Analysis registry (`AnalysisSpec`, roles, options), run `Context`, uniform `Result`, formatting, validation. |
| `stats/*.py` | Procedures, each registering a spec, a `run` function and a code generator. |
| `stats/engine.py` | Validation, execution, warning capture, result headings, reproducible code. |
| `stats/recommend.py` | Rule-based recommendations. |
| `reports/` | Report options/checklist filtering, chart rendering, DOCX and XLSX builders. |
| `jobs.py` | Thread-pool execution of analysis runs; re-queues interrupted runs on startup. |
| `dev/` | SQL engine and statement classification, sample DB, Python sandbox. |
| `api/` | Routers: auth, projects, datasets, analyses, exports, sql, python, system. |

### Uniform result structure

Every procedure returns the same shape: `tables[]` (columns carry a format and a checklist *group* such as `statistic`, `p`, `ci`, `effect`, `mean`), `charts[]` (data specifications, not images), `assumptions[]` (status ok / warning / violated / info), `warnings[]`, `notes[]`, `summary`, `interpretation {plain, technical}`, `method`, `code`. The UI, the interpretation display and both exporters render any analysis from this structure, and the report checklist filters it by kind and group.

Chart specifications are rendered by ECharts in the browser and by matplotlib in exports, so both show the same data.

### Execution model

`POST /analyses/runs` creates `AnalysisRun` rows (status `queued`) and submits them to a thread pool (`STATEASE_ANALYSIS_WORKERS`). The UI polls configurations for progress. Runs record the exact dataset version used. Queued or running analyses can be cancelled; a calculation already executing finishes in its thread, but its result is discarded. Runs interrupted by a restart are re-queued.

## Frontend (`frontend/src`)

React 19, TypeScript (strict), Vite, Tailwind CSS 4 with design tokens (light/dark), Radix primitives (dialog, checkbox, tabs, popover, menu, tooltip, switch), TanStack Query (server state), TanStack Virtual (data grid), ECharts (core build, SVG renderer), CodeMirror 6 (SQL/Python), React Hook Form + Zod (login).

| Path | Content |
|---|---|
| `components/layout/AppShell.tsx` | Sidebar (collapsible on desktop, drawer below 1024 px), page header. |
| `components/ui/` | Buttons, form controls, dialogs/sheets/popovers, feedback (callouts, badges, toasts, tabs). |
| `pages/` | Projects, Overview (three primary actions), Import wizard, Data explorer, Analyze, Results, Export center, Settings, Methods guide, dev tools. |
| `features/analysis/` | Analysis configuration cards and the variable role selector. |
| `features/results/` | APA-style tables, charts with data-table alternatives, result viewer. |
| `features/DataGrid.tsx` | Virtualized grid that fetches 200-row blocks on scroll. |

Below 1280 px the Analyze page switches from two columns to tabs; below 1024 px the Results page shows the list and the detail view one at a time.
