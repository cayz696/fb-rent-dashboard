from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import (
    COOKIE, make_token, new_totp_secret, read_token, totp_uri, verify_password, verify_totp,
)
from app.models import User
from app.schemas.api import LoginIn, LoginOut, TotpSetupOut, TotpVerifyIn, UserOut

router = APIRouter(prefix="/api", tags=["auth"])
PRE_TTL = timedelta(minutes=5)


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Невірний логін або пароль")
    return LoginOut(
        step="totp_required" if user.totp_enabled else "totp_setup",
        pre_token=make_token(user.id, "pre", PRE_TTL),
    )


def _pre_user(token: str, db: Session) -> User:
    uid = read_token(token, "pre")
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active:
        raise HTTPException(401, "Крок входу прострочений, увійдіть знову")
    return user


@router.post("/auth/2fa/setup", response_model=TotpSetupOut)
def setup_2fa(pre_token: str, db: Session = Depends(get_db)):
    user = _pre_user(pre_token, db)
    if user.totp_enabled:
        raise HTTPException(409, "2FA вже налаштовано")
    # Ідемпотентно: не перегенеровуємо секрет, якщо налаштування вже почалось,
    # щоб раніше відсканований QR лишався дійсним (інакше код із застосунку «ламається»).
    if not user.totp_secret:
        user.totp_secret = new_totp_secret()
        db.commit()
    return TotpSetupOut(secret=user.totp_secret, uri=totp_uri(user.totp_secret, user.username))


@router.post("/auth/2fa/verify", response_model=UserOut)
def verify_2fa(body: TotpVerifyIn, response: Response, db: Session = Depends(get_db)):
    user = _pre_user(body.pre_token, db)
    if not user.totp_secret or not verify_totp(user.totp_secret, body.code):
        raise HTTPException(401, "Невірний код")
    if not user.totp_enabled:
        user.totp_enabled = True
        db.commit()
    ttl = timedelta(hours=settings.session_ttl_hours)
    response.set_cookie(
        COOKIE, make_token(user.id, "session", ttl), max_age=int(ttl.total_seconds()),
        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/",
    )
    return user


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
