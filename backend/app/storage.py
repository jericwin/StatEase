"""Filesystem helpers. All stored paths are relative to ``storage_dir`` and are never sent to clients."""

from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path

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
    """Resolve a stored relative path, refusing anything that escapes the storage root."""
    root = get_settings().storage_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise AppError("invalid_path", "Invalid storage path.", 400)
    return path


def relative(path: Path) -> str:
    return path.resolve().relative_to(get_settings().storage_dir.resolve()).as_posix()
