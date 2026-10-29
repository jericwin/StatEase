"""Gmail API delivery (HTTP calls mocked)."""

from __future__ import annotations

import base64
from email import message_from_bytes

import httpx

from app import mailer
from app.config import get_settings


def test_gmail_api_send(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gmail_refresh_token", "refresh-1")
    monkeypatch.setattr(s, "google_client_id", "cid")
    monkeypatch.setattr(s, "google_client_secret", "csecret")
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        body = {"access_token": "at-1"} if url == mailer.GOOGLE_TOKEN else {"id": "m1"}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(mailer.httpx, "post", fake_post)
    assert mailer.send("ana@example.com", "Reset your StatEase password", "Open this link")
    (token_url, token_kw), (send_url, send_kw) = calls
    assert token_kw["data"]["refresh_token"] == "refresh-1" and token_kw["data"]["grant_type"] == "refresh_token"
    assert send_url == mailer.GMAIL_SEND and send_kw["headers"]["Authorization"] == "Bearer at-1"
    msg = message_from_bytes(base64.urlsafe_b64decode(send_kw["json"]["raw"]))
    assert msg["To"] == "ana@example.com" and msg["Subject"] == "Reset your StatEase password"


def test_gmail_api_failure_is_reported(monkeypatch):
    monkeypatch.setattr(get_settings(), "gmail_refresh_token", "revoked")

    def fake_post(url, **kw):
        return httpx.Response(400, json={"error": "invalid_grant"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(mailer.httpx, "post", fake_post)
    assert mailer.send("ana@example.com", "s", "t") is False
