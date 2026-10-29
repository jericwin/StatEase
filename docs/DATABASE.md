# Database and Storage

## Metadata database

SQLite by default (`backend/var/statease.db`); PostgreSQL for multi-user deployments via `STATEASE_DATABASE_URL=postgresql+psycopg://…`. JSON columns use `JSONB` on PostgreSQL. Migrations live in `backend/alembic/versions` and run automatically at startup (or manually: `cd backend && alembic upgrade head`).

| Table | Purpose |
|---|---|
| `users` | email, scrypt password hash, role (analyst / developer / admin) |
| `projects` | owner, name, description, status (active/archived), reporting settings (α, CI level, p style, decimals) |
| `datasets` | project, name, source file name, original upload path, format, row/column counts, `parent_version_id` + `lineage_json` (SQL query, transforms, import options and issues) |
| `dataset_versions` | version number, Parquet path, SHA-256, schema, full profile, note |
| `variables` | per version: name, label, measurement level, storage type, category labels and order, missing-value codes, unit, inferred level and note, scale group |
| `analysis_configurations` | project, dataset version, analysis type, variables + options (JSON), source (manual/recommended), position |
| `analysis_runs` | configuration, exact dataset version used, status, parameters snapshot, summary, error code/message, timings |
| `analysis_results` | full result JSON, user-edited interpretation |
| `exports` | format, options, artifact path, size, status, error |
| `audit_logs` | user, project, action, details (no passwords or data values) |
| `db_connections` | external connection profiles; password encrypted (Fernet, key derived from `STATEASE_SECRET_KEY`) |
| `saved_queries`, `query_history` | SQL/Python scripts and execution history |

Foreign keys cascade from projects to everything they own; indexes cover the common lookups (owner, project, status).

## File storage

Under `STATEASE_STORAGE_DIR` (default `backend/var/storage`):

```
originals/   untouched uploaded files
datasets/    one Parquet file per dataset version (zstd)
exports/     generated .docx/.xlsx
uploads/     staged uploads awaiting confirmation (deleted after import)
sqlite/      managed SQLite databases for the SQL workbench
sandbox/     temporary Python console working directories
```

Large data is never stored in the metadata database. Paths are stored relative to the storage root and are never sent to the browser.

## Versioning and lineage

An import creates version 1. Computing a scale score creates a new version (metadata carried over); earlier versions are kept. Analyses are configured on a version; runs record the version they used, and "Run" uses the latest version of the same dataset. Datasets saved from SQL record the query and source dataset versions.

## Backup and restore

Back up the metadata database **and** the storage directory together, while the application is stopped (or with the database's online backup tool).

```bash
# SQLite + files (local mode)
tar czf statease-backup.tgz backend/var/statease.db backend/var/storage

# PostgreSQL deployment (docker compose production)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec db pg_dump -U statease statease > statease.sql
docker run --rm -v data-transform_statease-data:/data -v "$PWD":/backup alpine tar czf /backup/files.tgz /data
```

Restore by putting the files back in place (or `psql < statease.sql`) and starting the application; migrations bring an older schema up to date.
