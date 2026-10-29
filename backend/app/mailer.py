"""Outgoing e-mail (password resets, verification codes).

Sends through the Gmail API when a Gmail refresh token is configured (works on hosts that block SMTP ports,
such as Render's free plan), otherwise through SMTP when configured, otherwise logs the message.
"""

from __future__ import annotations

import base64
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from .config import get_settings

log = logging.getLogger("statease.mail")

GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def send(to: str, subject: str, text: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    if s.gmail_refresh_token:
        return _send_gmail(msg, to)
    if not s.smtp_host:
        # Development fallback: the administrator can copy the link from the server log.
        log.warning("E-mail is not configured; e-mail to %s not sent.\nSubject: %s\n%s", to, subject, text)
        return False
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("Failed to send e-mail to %s", to)
        return False


def _send_gmail(msg: EmailMessage, to: str) -> bool:
    """Send as the Gmail account that granted the gmail.send scope to our OAuth client."""
    s = get_settings()
    try:
        token = httpx.post(GOOGLE_TOKEN, timeout=20, data={
            "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "refresh_token": s.gmail_refresh_token, "grant_type": "refresh_token"})
        token.raise_for_status()
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = httpx.post(GMAIL_SEND, timeout=20, json={"raw": raw},
                       headers={"Authorization": f"Bearer {token.json()['access_token']}"})
        r.raise_for_status()
        return True
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        detail = exc.response.text[:300] if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        log.error("Failed to send e-mail to %s through Gmail: %s", to, detail)
        return False
