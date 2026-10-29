"""Email/password accounts, password reset and Google OAuth (token exchange mocked; everything else real)."""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.api import auth as auth_api
from app.config import get_settings

API = "/api/v1"


@pytest.fixture()
def password_mode(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "auth_mode", "password")
    monkeypatch.setattr(s, "google_client_id", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_client_secret", "secret")
    monkeypatch.setattr(s, "public_url", "http://testserver")
    auth_api._attempts.clear()
    yield s


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _last_code(caplog, email):
    """Codes are e-mailed; with SMTP disabled in tests the message is written to the log instead."""
    for rec in reversed(caplog.records):
        msg = rec.getMessage()
        if email in msg and "verification code is:" in msg:
            return re.search(r"verification code is: (\d{6})", msg).group(1)
    raise AssertionError("no verification code logged")


def register(client, caplog, email, password, **extra):
    """Sign up and confirm the e-mail code; returns the session token."""
    with caplog.at_level("WARNING", logger="statease.mail"):
        r = client.post(f"{API}/auth/register", json={"email": email, "password": password, **extra})
    assert r.status_code == 201, r.text
    assert r.json() == {"verification_required": True, "email": email.lower()}
    v = client.post(f"{API}/auth/verify-email", json={"email": email, "code": _last_code(caplog, email.lower())})
    assert v.status_code == 200, v.text
    return v.json()["token"]


def test_signup_login_and_protection(client, password_mode, caplog):
    # A project made earlier in local mode must be taken over by the first account.
    password_mode.auth_mode = "local"
    client.post(f"{API}/projects", json={"name": "Made in local mode"})
    password_mode.auth_mode = "password"
    assert client.get(f"{API}/projects").status_code == 401
    r = client.post(f"{API}/auth/register", json={"email": "Ana@Example.com", "password": "short"})
    assert r.status_code == 422
    token = register(client, caplog, "ana@example.com", "correct-horse-7", display_name="Ana")
    assert client.get(f"{API}/auth/me", headers=_bearer(token)).json()["email"] == "ana@example.com"
    # First account on an installation previously used in local mode takes over the local projects.
    owned = client.get(f"{API}/projects", headers=_bearer(token))
    assert owned.status_code == 200 and owned.json()["total"] >= 1
    assert client.get(f"{API}/auth/me", headers=_bearer(token)).json()["role"] == "admin"
    dup = client.post(f"{API}/auth/register", json={"email": "ANA@example.com", "password": "correct-horse-7"})
    assert dup.status_code == 409
    bad = client.post(f"{API}/auth/login", json={"email": "ana@example.com", "password": "wrong-password-1"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    ok = client.post(f"{API}/auth/login", json={"email": "ana@example.com", "password": "correct-horse-7"})
    assert ok.status_code == 200
    assert client.get(f"{API}/projects", headers=_bearer("forged.token")).status_code == 401


def test_users_cannot_see_each_others_projects(client, password_mode, caplog):
    t1 = register(client, caplog, "u1@example.com", "pass-word-11")
    t2 = register(client, caplog, "u2@example.com", "pass-word-22")
    p = client.post(f"{API}/projects", json={"name": "Private"}, headers=_bearer(t1)).json()
    assert client.get(f"{API}/projects/{p['id']}", headers=_bearer(t2)).status_code == 404
    assert client.delete(f"{API}/projects/{p['id']}", headers=_bearer(t2)).status_code == 404


def test_login_throttling(client, password_mode):
    for _ in range(10):
        client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "x"})
    r = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 429


def test_password_reset_flow(client, password_mode, caplog):
    register(client, caplog, "reset@example.com", "first-pass-1")
    old = client.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": "first-pass-1"}).json()["token"]
    unknown = client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"})
    with caplog.at_level("WARNING", logger="statease.mail"):
        known = client.post(f"{API}/auth/forgot-password", json={"email": "reset@example.com"})
    assert unknown.json() == known.json()  # no account enumeration
    link = re.search(r"reset-password\?token=([\w-]+)", caplog.text)
    assert link, "reset link should be logged when SMTP is not configured"
    token = link.group(1)
    r = client.post(f"{API}/auth/reset-password", json={"token": token, "password": "second-pass-2"})
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=_bearer(old)).status_code == 401  # old sessions revoked
    assert client.post(f"{API}/auth/reset-password", json={"token": token, "password": "third-pass-3"}).status_code == 400
    assert client.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": "second-pass-2"}).status_code == 200


def _id_token(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


def test_google_oauth_flow(client, password_mode, monkeypatch):
    start = client.get(f"{API}/auth/google/start?next=/app/projects", follow_redirects=False)
    assert start.status_code == 302
    q = parse_qs(urlparse(start.headers["location"]).query)
    assert q["client_id"] == ["client-123.apps.googleusercontent.com"]
    assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == ["http://testserver/api/v1/auth/google/callback"]
    state = q["state"][0]

    seen = {}

    def fake_exchange(code, verifier):
        seen.update(code=code, verifier=verifier)
        return {"id_token": _id_token({"iss": "https://accounts.google.com", "aud": "client-123.apps.googleusercontent.com",
                                       "exp": time.time() + 600, "sub": "g-42", "email": "Gina@Gmail.com",
                                       "email_verified": True, "name": "Gina"})}

    monkeypatch.setattr(auth_api, "exchange_code", fake_exchange)
    # A wrong state is rejected (CSRF protection).
    bad = client.get(f"{API}/auth/google/callback?code=abc&state=wrong", follow_redirects=False)
    assert "error=google_state" in bad.headers["location"]
    start = client.get(f"{API}/auth/google/start?next=/app/projects", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = client.get(f"{API}/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert cb.status_code == 302 and seen["code"] == "abc" and len(seen["verifier"]) > 40
    frag = urlparse(cb.headers["location"]).fragment
    token = parse_qs(frag)["token"][0]
    assert parse_qs(frag)["next"] == ["/app/projects"]
    me = client.get(f"{API}/auth/me", headers=_bearer(token)).json()
    assert me["email"] == "gina@gmail.com" and me["google_linked"] and not me["has_password"]
    # Password login is refused for a Google-only account, with a helpful message.
    r = client.post(f"{API}/auth/login", json={"email": "gina@gmail.com", "password": "anything-1"})
    assert r.json()["error"]["code"] == "use_google"


def test_google_rejects_wrong_audience(client, password_mode, monkeypatch):
    monkeypatch.setattr(auth_api, "exchange_code", lambda c, v: {"id_token": _id_token({
        "iss": "https://accounts.google.com", "aud": "someone-else", "exp": time.time() + 600, "sub": "x",
        "email": "x@example.com", "email_verified": True})})
    start = client.get(f"{API}/auth/google/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = client.get(f"{API}/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert "error=google_failed" in cb.headers["location"]


def test_google_hidden_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    assert client.get(f"{API}/auth/config").json()["google"] is False
    assert client.get(f"{API}/auth/google/start", follow_redirects=False).status_code == 404


def test_email_verification_code(client, password_mode, caplog):
    with caplog.at_level("WARNING", logger="statease.mail"):
        r = client.post(f"{API}/auth/register", json={"email": "vera@example.com", "password": "verify-pass-1"})
    assert r.json()["verification_required"] and "token" not in r.json()
    code = _last_code(caplog, "vera@example.com")
    # Not usable before verification: login sends a new code and refuses.
    with caplog.at_level("WARNING", logger="statease.mail"):
        r = client.post(f"{API}/auth/login", json={"email": "vera@example.com", "password": "verify-pass-1"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_unverified"
    new_code = _last_code(caplog, "vera@example.com")
    if new_code != code:  # the old code was replaced by the new one
        bad = client.post(f"{API}/auth/verify-email", json={"email": "vera@example.com", "code": code})
        assert bad.status_code == 400
    wrong = "000000" if new_code != "000000" else "111111"
    r = client.post(f"{API}/auth/verify-email", json={"email": "vera@example.com", "code": wrong})
    assert r.status_code == 400 and "attempt" in r.json()["error"]["message"]
    r = client.post(f"{API}/auth/verify-email", json={"email": "vera@example.com", "code": new_code})
    assert r.status_code == 200 and r.json()["user"]["email_verified"]
    assert client.post(f"{API}/auth/login", json={"email": "vera@example.com", "password": "verify-pass-1"}).status_code == 200
    # Resend answers identically for unknown addresses.
    a = client.post(f"{API}/auth/resend-code", json={"email": "nobody@example.com"}).json()
    b = client.post(f"{API}/auth/resend-code", json={"email": "vera@example.com"}).json()
    assert a == b


def test_verification_code_attempt_limit(client, password_mode, caplog):
    with caplog.at_level("WARNING", logger="statease.mail"):
        client.post(f"{API}/auth/register", json={"email": "lim@example.com", "password": "limit-pass-1"})
    code = _last_code(caplog, "lim@example.com")
    wrong = "123456" if code != "123456" else "654321"
    for _ in range(5):
        client.post(f"{API}/auth/verify-email", json={"email": "lim@example.com", "code": wrong})
    r = client.post(f"{API}/auth/verify-email", json={"email": "lim@example.com", "code": code})
    assert r.status_code == 429  # even the right code is refused after 5 wrong attempts; a new code is needed
