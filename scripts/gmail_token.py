"""Grant StatEase permission to send e-mail as your Gmail account and save the refresh token.

Run from the repository root:  backend/.venv/Scripts/python scripts/gmail_token.py
Prerequisites: the Gmail API is enabled for the Google Cloud project, and http://127.0.0.1:8765/ is an
authorised redirect URI of the OAuth client whose ID and secret are in .env.

The refresh token is written to STATEASE_GMAIL_REFRESH_TOKEN in .env and backend/.env; it is never printed.
Copy it to the production host's environment as well.
"""

from __future__ import annotations

import http.server
import re
import secrets
import sys
import urllib.parse
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_FILES = [ROOT / ".env", ROOT / "backend" / ".env"]
REDIRECT = "http://127.0.0.1:8765/"
SCOPE = "https://www.googleapis.com/auth/gmail.send"


def read_env(key: str) -> str:
    for f in ENV_FILES:
        m = re.search(rf"^{key}=(.*)$", f.read_text(encoding="utf-8"), re.M) if f.exists() else None
        if m and m.group(1).strip():
            return m.group(1).strip()
    sys.exit(f"{key} is not set in .env")


def write_env(key: str, value: str) -> None:
    for f in ENV_FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        line = f"{key}={value}"
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M) if re.search(rf"^{key}=", text, re.M) \
            else text.rstrip("\n") + f"\n{line}\n"
        f.write_text(text, encoding="utf-8")


def main() -> None:
    client_id, client_secret = read_env("STATEASE_GOOGLE_CLIENT_ID"), read_env("STATEASE_GOOGLE_CLIENT_SECRET")
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})
    print("Open this address, choose the sending Gmail account and allow 'Send email on your behalf':\n" + url,
          flush=True)

    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if q.get("state") != state:
                self.send_response(400)
                self.end_headers()
                return
            result.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("StatEase: done. You can close this tab.".encode())

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(("127.0.0.1", 8765), Handler) as server:
        while not result:
            server.handle_request()
    if "code" not in result:
        sys.exit(f"Not granted: {result.get('error', 'unknown error')}")
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    r.raise_for_status()
    token = r.json().get("refresh_token")
    if not token:
        sys.exit("Google returned no refresh token; remove StatEase's access at myaccount.google.com and retry.")
    write_env("STATEASE_GMAIL_REFRESH_TOKEN", token)
    print("Saved STATEASE_GMAIL_REFRESH_TOKEN to .env and backend/.env.")


if __name__ == "__main__":
    main()
