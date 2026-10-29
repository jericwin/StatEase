"""Database copies of stored files, for hosts whose disk is wiped on restart."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.main import create_app
from app.models import StoredFile

API = "/api/v1"


def _stored() -> dict[str, int]:
    with SessionLocal() as db:
        return {f.path: f.size for f in db.scalars(select(StoredFile))}


def test_files_survive_a_wiped_disk(monkeypatch):
    monkeypatch.setattr(get_settings(), "persist_files_in_db", True)
    with TestClient(create_app()) as client:
        _check(client)


def _check(client):
    pid = client.post(f"{API}/demo", json={"key": "experiment"}).json()["id"]
    ds = client.get(f"{API}/projects/{pid}/datasets").json()["items"][0]
    stored = _stored()
    data_paths = [p for p in stored if p.startswith("datasets/")]
    assert data_paths and all(size > 0 for size in stored.values())

    # Simulate a restart on an ephemeral disk: the Parquet files are gone, the database copies remain.
    for p in data_paths:
        (get_settings().storage_dir / p).unlink()
    preview = client.get(f"{API}/datasets/{ds['id']}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"]
    assert all((get_settings().storage_dir / p).exists() for p in data_paths)

    assert client.delete(f"{API}/projects/{pid}").status_code == 204
    assert not set(data_paths) & set(_stored())
