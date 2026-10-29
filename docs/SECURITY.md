# Security

## Authentication and authorisation

- **Password mode** (default): email/password accounts; passwords hashed with scrypt; HMAC-SHA256 bearer tokens (`STATEASE_TOKEN_TTL_HOURS`, default 72) kept in the browser's localStorage. Each token carries the account's token version, so a password reset or "sign out everywhere" invalidates all earlier tokens. Login, sign-up and reset requests are throttled per client (10 per 15 minutes). The first account becomes admin and takes over any projects created earlier in local mode; registration can be closed with `STATEASE_ALLOW_REGISTRATION=false`.
- **Google sign-in**: OpenID Connect authorization code flow with PKCE (S256) and a signed, HttpOnly, 10-minute state cookie (CSRF protection). The code is exchanged server-side with the client secret; the ID token's issuer, audience and expiry are checked (signature validation is replaced by TLS to Google's token endpoint, as permitted by OpenID Connect Core §3.1.3.7). Only verified Google e-mail addresses are accepted; an existing account with the same verified e-mail is linked. The session token is returned in the URL fragment, which browsers do not send to servers.
- **Password reset**: random single-use tokens stored only as SHA-256 hashes, valid for `STATEASE_PASSWORD_RESET_MINUTES` (60). The forgot-password endpoint answers identically whether or not an account exists.
- **Local mode** (`STATEASE_AUTH_MODE=local`): a single local administrator is used automatically, no sign-in. Use only on a single computer bound to localhost.
- Roles: **analyst** (statistical features), **developer** (+ SQL workbench and database connections), **admin** (+ write statements on writable connections, Python console, user roles).
- Every project resource is checked server-side against its owner; another user's IDs return 404.
- In production the app refuses to start with the default secret key.

## Data handling

- Original uploads are stored unchanged; transformations create new versions.
- Stored paths are relative to the storage root and resolved with traversal protection; uploaded file names are sanitised; staged upload IDs are validated.
- Upload size limits: `STATEASE_MAX_UPLOAD_MB` (512) and `STATEASE_MAX_EXCEL_MB` (100).
- The audit log records actions (imports, deletions, exports, SQL writes, logins) without passwords, query results or data values.

## SQL workbench

- **Project datasets** are exposed through an in-memory DuckDB session with views over the project's Parquet files. After the views are created, file-system access is restricted to the datasets directory, external access is disabled, memory and threads are limited, and the configuration is locked. Reading arbitrary files, `COPY`, `ATTACH`, `INSTALL` and changing settings fail (covered by tests).
- Every statement is parsed with sqlglot and classified. On project datasets only reads are allowed; use "Save as dataset" for modified copies.
- **External connections** are read-only unless the profile allows writes (set by an admin). Write and DDL statements additionally require the admin role and an explicit confirmation listing the statements. PostgreSQL sessions use `default_transaction_read_only`; MySQL uses `SET SESSION TRANSACTION READ ONLY`; SQLite opens with `mode=ro`.
- Timeouts (`STATEASE_SQL_TIMEOUT_SECONDS`) via DuckDB interrupt, PostgreSQL `statement_timeout`, MySQL `max_execution_time`, SQLite progress handler; row limits on results and exports.
- Passwords are encrypted at rest (Fernet; key derived from `STATEASE_SECRET_KEY`) and never returned to the browser, logged or exported. Use least-privilege database accounts.
- SQLite connections can only open files in the managed `storage/sqlite/` directory.

## Python console

Disabled by default (`STATEASE_ENABLE_PYTHON_CONSOLE=false`); admin role required.

Each run executes in a **separate Python process** (`python -I`) in a fresh temporary directory containing only a copy of the selected dataset. The parent enforces a wall-clock limit and a memory limit (polled RSS; the process is killed when exceeded). The child receives an environment with `STATEASE_*` settings and credential-like variables removed. Inside the child, an audit hook blocks sockets, subprocesses, `ctypes`, writing outside the working directory, and reading outside the working directory and the Python installation.

**Limitation:** an in-process audit hook is defence in depth, not an operating-system security boundary, and memory limits on Windows are enforced by polling. Do not enable the console on a shared server unless the application runs in a container with no network access, a read-only root filesystem and container resource limits (for example `docker run --network none --read-only --memory 1g --pids-limit 64`). Enable it only for trusted users.

## Transport and deployment

- Serve behind HTTPS (reverse proxy) in production. CORS is limited to `STATEASE_CORS_ORIGINS`.
- The Docker image runs as a non-root user.
- Keep the storage directory and database backups private: they contain research data.
