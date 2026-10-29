from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import DB, CurrentUser, audit, require_role
from ..errors import AppError, NotFound
from ..mailer import send
from ..models import EmailCode, PasswordReset, User
from ..security import create_token, hash_password, sign_payload, verify_password, verify_payload

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
OAUTH_COOKIE = "statease_oauth"

# Simple in-memory throttle for credential endpoints (per client IP + email).
_attempts: dict[str, deque[float]] = defaultdict(deque)
LIMIT, WINDOW = 10, 15 * 60


def _throttle(key: str) -> None:
    now = time.time()
    q = _attempts[key]
    while q and q[0] < now - WINDOW:
        q.popleft()
    if len(q) >= LIMIT:
        raise AppError("too_many_attempts", "Too many attempts. Wait a few minutes and try again.", 429)
    q.append(now)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(analyst|developer|admin)$")


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
            "has_password": u.has_password, "google_linked": bool(u.google_sub), "email_verified": u.email_verified,
            "created_at": u.created_at.isoformat()}


def _session(db: Session, user: User) -> dict:
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return {"token": create_token(user.id, user.token_version), "user": user_out(user)}


def _first_user(db: Session) -> bool:
    return db.scalar(select(func.count(User.id)).where(User.email != "local@statease.local")) == 0


def _adopt_local_data(db: Session, user: User) -> int:
    """The first account on an installation previously used in local mode takes over the local projects,
    so switching to sign-in mode never hides existing work."""
    from ..models import DbConnection, Project, QueryHistory, SavedQuery

    local = db.scalar(select(User).where(User.email == "local@statease.local"))
    if local is None:
        return 0
    moved = 0
    for model in (Project, DbConnection, SavedQuery, QueryHistory):
        for row in db.scalars(select(model).where(model.owner_id == local.id)):
            row.owner_id = user.id
            moved += model is Project
    if moved:
        audit(db, user, "user.adopted_local_projects", projects=moved)
    return moved


def _code_hash(user_id: int, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hashlib.sha256(key + f":{user_id}:{code}".encode()).hexdigest()


def _send_code(db: Session, user: User) -> None:
    """E-mail a fresh 6-digit code; earlier unused codes stop working."""
    s = get_settings()
    now = datetime.now(UTC)
    for old in db.scalars(select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.used_at.is_(None))):
        old.used_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(EmailCode(user_id=user.id, purpose="verify", code_hash=_code_hash(user.id, code),
                     expires_at=now + timedelta(minutes=s.verification_code_minutes)))
    db.commit()
    send(user.email, f"{code} is your StatEase verification code",
         f"Your StatEase Analytics verification code is: {code}\n\n"
         f"Enter it on the sign-up page to confirm your email address. It expires in {s.verification_code_minutes} "
         "minutes.\n\nIf you did not create an account, you can ignore this email.")


def _validate_password(pw: str) -> None:
    if len(pw) < 8 or pw.isdigit() or pw.lower() == pw and pw.isalpha() and len(pw) < 12:
        raise AppError("weak_password", "Use at least 8 characters, mixing letters with numbers or symbols.", 422)


@router.get("/config")
def auth_config():
    s = get_settings()
    return {"mode": s.auth_mode, "allow_registration": s.allow_registration, "google": s.google_enabled,
            "python_console": s.enable_python_console}


@router.post("/register", status_code=201)
def register(body: SignupIn, request: Request, db: DB):
    s = get_settings()
    if s.auth_mode != "password":
        raise AppError("not_available", "Accounts are not used in local mode.", 400)
    if not s.allow_registration:
        raise AppError("registration_closed", "Sign-up is disabled. Ask an administrator for an account.", 403)
    _throttle(f"register:{_client(request)}")
    _validate_password(body.password)
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise AppError("email_taken", "An account with this email already exists. Sign in instead.", 409)
    first = _first_user(db)
    verify = s.require_email_verification
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), email_verified=not verify,
                display_name=(body.display_name or "").strip() or None, role="admin" if first else "analyst")
    db.add(user)
    db.flush()
    if first:
        _adopt_local_data(db, user)
    audit(db, user, "user.register")
    if verify:
        _send_code(db, user)
        return {"verification_required": True, "email": user.email}
    return _session(db, user)


@router.post("/verify-email")
def verify_email(body: VerifyIn, request: Request, db: DB):
    _throttle(f"verify:{_client(request)}:{body.email.lower()}")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None:
        raise AppError("invalid_code", "That code is not correct.", 400)
    if user.email_verified:
        return _session(db, user)
    row = db.scalar(select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.used_at.is_(None))
                    .order_by(EmailCode.id.desc()))
    if row is None or row.expires_at < datetime.now(UTC):
        raise AppError("code_expired", "This code has expired. Request a new one.", 400)
    if row.attempts >= 5:
        raise AppError("too_many_attempts", "Too many incorrect attempts. Request a new code.", 429)
    if not hmac.compare_digest(row.code_hash, _code_hash(user.id, body.code)):
        row.attempts += 1
        db.commit()
        left = 5 - row.attempts
        raise AppError("invalid_code", f"That code is not correct. {left} attempt{'s' if left != 1 else ''} left.", 400)
    row.used_at = datetime.now(UTC)
    user.email_verified = True
    audit(db, user, "user.email_verified")
    return _session(db, user)


@router.post("/resend-code")
def resend_code(body: ResendIn, request: Request, db: DB):
    """Same answer whether or not the address has an unverified account."""
    _throttle(f"resend:{_client(request)}")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is not None and not user.email_verified and user.is_active:
        recent = db.scalar(select(EmailCode).where(EmailCode.user_id == user.id).order_by(EmailCode.id.desc()))
        if recent is None or (datetime.now(UTC) - recent.created_at).total_seconds() >= 30:
            _send_code(db, user)
    return {"ok": True, "message": "If the account is waiting for verification, a new code has been sent."}


@router.post("/login")
def login(body: LoginIn, request: Request, db: DB):
    _throttle(f"login:{_client(request)}:{body.email.lower()}")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or not user.has_password or not verify_password(body.password, user.password_hash):
        audit(db, None, "user.login_failed", email_domain=body.email.split("@")[-1])
        db.commit()
        if user is not None and not user.has_password:
            raise AppError("use_google", "This account signs in with Google. Use “Continue with Google”.", 401)
        raise AppError("invalid_credentials", "Email or password is incorrect.", 401)
    if not user.email_verified:
        _send_code(db, user)
        raise AppError("email_unverified", "Confirm your email first — we sent a new code to your inbox.", 403,
                       {"email": user.email})
    audit(db, user, "user.login")
    return _session(db, user)


@router.get("/me")
def me(user: CurrentUser):
    return user_out(user)


@router.post("/logout-all")
def logout_all(user: CurrentUser, db: DB):
    """Invalidate every token issued to this account."""
    user.token_version += 1
    audit(db, user, "user.logout_all")
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- password reset


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: DB):
    """Always answers the same way so the endpoint cannot reveal which emails have accounts."""
    _throttle(f"forgot:{_client(request)}")
    s = get_settings()
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=user.id, token_hash=_hash(token),
                             expires_at=datetime.now(UTC) + timedelta(minutes=s.password_reset_minutes)))
        audit(db, user, "user.password_reset_requested")
        db.commit()
        link = f"{s.public_url.rstrip('/')}/reset-password?token={token}"
        send(user.email, "Reset your StatEase password",
             f"Someone (hopefully you) asked to reset the password for {user.email}.\n\n"
             f"Open this link within {s.password_reset_minutes} minutes to choose a new password:\n{link}\n\n"
             "If you did not ask for this, you can ignore this email.")
    return {"ok": True, "message": "If an account exists for that email, we sent a link to reset the password."}


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, db: DB):
    _throttle(f"reset:{_client(request)}")
    _validate_password(body.password)
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash(body.token)))
    if row is None or row.used_at is not None or row.expires_at < datetime.now(UTC):
        raise AppError("invalid_token", "This reset link is invalid or has expired. Request a new one.", 400)
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(body.password)
    user.has_password = True
    user.email_verified = True  # the reset link proves ownership of the address
    user.token_version += 1  # sign out all existing sessions
    row.used_at = datetime.now(UTC)
    audit(db, user, "user.password_reset")
    return _session(db, user)


# --------------------------------------------------------------------------- Google OAuth (OIDC code flow + PKCE)


def _redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/v1/auth/google/callback"


def _safe_next(path: str | None) -> str:
    return path if path and path.startswith("/") and not path.startswith("//") else "/app"


@router.get("/google/start", include_in_schema=False)
def google_start(next: str | None = Query(None)):
    s = get_settings()
    if not s.google_enabled:
        raise AppError("google_disabled", "Google sign-in is not configured on this server.", 404)
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"client_id": s.google_client_id, "redirect_uri": _redirect_uri(), "response_type": "code",
              "scope": "openid email profile", "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256", "prompt": "select_account"}
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}", status_code=302)
    resp.set_cookie(OAUTH_COOKIE, sign_payload({"state": state, "verifier": verifier, "next": _safe_next(next)}, 600),
                    max_age=600, httponly=True, samesite="lax", secure=s.public_url.startswith("https"),
                    path="/api/v1/auth/google")
    return resp


def _fail(reason: str) -> RedirectResponse:
    resp = RedirectResponse(f"{get_settings().public_url.rstrip('/')}/login?error={reason}", status_code=302)
    resp.delete_cookie(OAUTH_COOKIE, path="/api/v1/auth/google")
    return resp


def exchange_code(code: str, verifier: str) -> dict:
    """Exchange the authorization code at Google's token endpoint (separate function for testing)."""
    s = get_settings()
    r = httpx.post(GOOGLE_TOKEN, data={"code": code, "client_id": s.google_client_id,
                                       "client_secret": s.google_client_secret, "redirect_uri": _redirect_uri(),
                                       "grant_type": "authorization_code", "code_verifier": verifier}, timeout=15)
    r.raise_for_status()
    return r.json()


def _id_claims(id_token: str) -> dict:
    # The ID token comes straight from Google's token endpoint over TLS, authenticated with our client
    # secret, so TLS validation stands in for signature validation (OpenID Connect Core §3.1.3.7).
    # The issuer, audience and expiry claims are still checked.
    import json

    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as exc:
        raise ValueError("malformed id_token") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("bad issuer")
    aud = claims.get("aud")
    if aud != get_settings().google_client_id and not (isinstance(aud, list) and get_settings().google_client_id in aud):
        raise ValueError("bad audience")
    if int(claims.get("exp", 0)) < time.time():
        raise ValueError("expired")
    return claims


@router.get("/google/callback", include_in_schema=False)
def google_callback(request: Request, db: DB, code: str | None = None, state: str | None = None,
                    error: str | None = None):
    s = get_settings()
    if error or not code or not state:
        return _fail("google_cancelled")
    cookie = verify_payload(request.cookies.get(OAUTH_COOKIE, ""))
    if not cookie or not secrets.compare_digest(cookie.get("state", ""), state):
        return _fail("google_state")
    try:
        tokens = exchange_code(code, cookie["verifier"])
        claims = _id_claims(tokens["id_token"])
    except (httpx.HTTPError, KeyError, ValueError):
        return _fail("google_failed")
    if not claims.get("email") or not claims.get("email_verified"):
        return _fail("google_unverified")
    sub, email = str(claims["sub"]), str(claims["email"]).lower()
    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None:
            user.google_sub = sub  # link an existing account with the same verified email
            user.email_verified = True
        elif not s.allow_registration:
            return _fail("registration_closed")
        else:
            first = _first_user(db)
            user = User(email=email, password_hash=hash_password(secrets.token_urlsafe(32)), has_password=False,
                        email_verified=True, google_sub=sub, display_name=claims.get("name"), role="admin" if first else "analyst")
            db.add(user)
            db.flush()
            if first:
                _adopt_local_data(db, user)
            audit(db, user, "user.register", provider="google")
    if not user.is_active:
        return _fail("account_disabled")
    audit(db, user, "user.login", provider="google")
    session = _session(db, user)
    # The token travels in the URL fragment, which browsers never send to servers or log.
    resp = RedirectResponse(f"{s.public_url.rstrip('/')}/auth/callback#token={session['token']}&next={cookie['next']}",
                            status_code=302)
    resp.delete_cookie(OAUTH_COOKIE, path="/api/v1/auth/google")
    return resp


# --------------------------------------------------------------------------- administration


@router.get("/users")
def list_users(user: CurrentUser, db: DB):
    require_role(user, "admin")
    return {"items": [user_out(u) for u in db.scalars(select(User).order_by(User.id))]}


@router.patch("/users/{user_id}")
def set_role(user_id: int, body: RoleUpdate, user: CurrentUser, db: DB):
    require_role(user, "admin")
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("User")
    target.role = body.role
    audit(db, user, "user.role_changed", target=user_id, role=body.role)
    db.commit()
    return user_out(target)
