"""Filesystem helpers. All stored paths are relative to ``storage_dir`` and are never sent to clients."""

from __future__ import annotations

import re
import unicodedata
import uuid
from contextvars import ContextVar
from pathlib import Path

from sqlalchemy import delete, select

from .config import get_settings
from .errors import AppError

_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str, default: str = "file") -> str:
    """Return a filename with no path components or unsafe characters."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = Path(name.replace("\\", "/")).name
    name = _UNSAFE.sub("_", name).strip(" .")
    return (name or default)[:150]


def new_relative_path(subdir: str, suffix: str) -> str:
    return f"{subdir}/{uuid.uuid4().hex}{suffix}"


def resolve(relative: str) -> Path:
    """Resolve a stored relative path, refusing anything that escapes the storage root.

    With ``persist_files_in_db`` the file is restored from the database when the local copy is missing
    (ephemeral disks), and paths resolved during a request are saved to the database when it ends.
    """
    path = _local_path(relative)
    if get_settings().persist_files_in_db and relative.split("/", 1)[0] in PERSISTED_DIRS:
        touched = _touched.get()
        if touched is not None:
            touched.add(relative)
        if not path.exists():
            _restore(relative, path)
    return path


def _local_path(relative: str) -> Path:
    root = get_settings().storage_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise AppError("invalid_path", "Invalid storage path.", 400)
    return path


def relative(path: Path) -> str:
    return path.resolve().relative_to(get_settings().storage_dir.resolve()).as_posix()


# --------------------------------------------------------------------------- database copies of stored files

# Only durable artefacts are copied; staged uploads and SQLite/sandbox scratch files stay local.
PERSISTED_DIRS = {"datasets", "originals", "exports"}
_touched: ContextVar[set[str] | None] = ContextVar("storage_touched", default=None)


def track_request() -> set[str]:
    """Start collecting the stored paths resolved in the current (request) context."""
    touched: set[str] = set()
    _touched.set(touched)
    return touched


def persist_tracked(touched: set[str]) -> None:
    """Save files resolved during a request that exist locally but have no database copy yet."""
    if touched:
        persist(touched)


def persist(paths: set[str]) -> None:
    from .db import SessionLocal
    from .models import StoredFile

    limit = get_settings().persist_max_mb * 1024 * 1024
    with SessionLocal() as db:
        known = set(db.scalars(select(StoredFile.path).where(StoredFile.path.in_(paths))))
        for rel in sorted(paths - known):
            path = _local_path(rel)
            if path.is_file() and path.stat().st_size <= limit:
                db.add(StoredFile(path=rel, size=path.stat().st_size, data=path.read_bytes()))
        db.commit()


def _restore(rel: str, path: Path) -> None:
    from .db import SessionLocal
    from .models import StoredFile

    with SessionLocal() as db:
        row = db.get(StoredFile, rel)
        if row is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(row.data)
        tmp.replace(path)


def remove(rel: str) -> None:
    """Delete a stored file and its database copy."""
    _local_path(rel).unlink(missing_ok=True)
    if get_settings().persist_files_in_db:
        from .db import SessionLocal
        from .models import StoredFile

        with SessionLocal() as db:
            db.execute(delete(StoredFile).where(StoredFile.path == rel))
            db.commit()
