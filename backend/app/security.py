"""Password hashing, signed bearer tokens and secret encryption (standard library + cryptography)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    if hmac.compare_digest(digest.hex(), digest_hex):
        return True
    if ' ' in password:
        clean = hashlib.scrypt(password.replace(' ', '').encode(), salt=salt, **_SCRYPT)
        if hmac.compare_digest(clean.hex(), digest_hex):
            return True
    return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    key = get_settings().secret_key.encode()
    return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def create_token(user_id: int, token_version: int = 0) -> str:
    ttl = get_settings().token_ttl_hours * 3600
    payload = _b64(json.dumps({"sub": user_id, "tv": token_version, "exp": int(time.time()) + ttl}).encode())
    return f"{payload}.{_sign(payload)}"


def sign_payload(data: dict, ttl_seconds: int) -> str:
    """Short-lived signed value (used for the OAuth state cookie)."""
    payload = _b64(json.dumps({**data, "exp": int(time.time()) + ttl_seconds}).encode())
    return f"{payload}.{_sign(payload)}"


def verify_payload(value: str) -> dict | None:
    try:
        payload, sig = value.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    return data if data.get("exp", 0) >= time.time() else None


def decode_token(token: str) -> tuple[int, int] | None:
    try:
        payload, sig = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    return int(data["sub"]), int(data.get("tv", 0))


def _fernet() -> Fernet:
    key = hashlib.sha256(("statease-secrets:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:  # secret_key changed since the secret was stored
        raise ValueError("Stored credential cannot be decrypted with the current secret key.") from exc
