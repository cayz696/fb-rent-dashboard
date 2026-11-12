from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()
ALGO = "HS256"
COOKIE = "fbr_session"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def make_token(user_id: uuid.UUID, purpose: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "purpose": purpose, "iat": now, "exp": now + ttl},
        settings.secret_key,
        algorithm=ALGO,
    )


def read_token(token: str, purpose: str) -> uuid.UUID | None:
    data = _decode(token)
    if not data or data.get("purpose") != purpose:
        return None
    return uuid.UUID(data["sub"])


def token_remaining(token: str, purpose: str) -> timedelta | None:
    data = _decode(token)
    if not data or data.get("purpose") != purpose:
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="FB Rent")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
