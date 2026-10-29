from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="statease-test-"))
os.environ["STATEASE_ENVIRONMENT"] = "test"
os.environ["STATEASE_AUTH_MODE"] = "local"  # test_auth.py switches to password mode explicitly
os.environ["STATEASE_SMTP_HOST"] = ""  # never send real e-mail from tests, whatever backend/.env contains
os.environ["STATEASE_PUBLIC_URL"] = "http://testserver"
os.environ["STATEASE_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["STATEASE_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["STATEASE_ENABLE_PYTHON_CONSOLE"] = "true"
os.environ["STATEASE_PYTHON_TIMEOUT_SECONDS"] = "20"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
