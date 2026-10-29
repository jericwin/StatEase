"""Outgoing e-mail (password resets). Uses SMTP when configured; otherwise logs the message."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("statease.mail")


def send(to: str, subject: str, text: str) -> bool:
    s = get_settings()
    if not s.smtp_host:
        # Development fallback: the administrator can copy the link from the server log.
        log.warning("SMTP is not configured; e-mail to %s not sent.\nSubject: %s\n%s", to, subject, text)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
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
