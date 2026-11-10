from __future__ import annotations
import uuid

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import COOKIE, read_token
from app.models import Role, User

# Як у web session.ts: без кастомного списку ці розділи лише для admin.
DEFAULT_RESTRICTED_SECTIONS = frozenset({"finance", "reports", "settings"})


def current_user(session: str | None = Cookie(default=None, alias=COOKIE), db: Session = Depends(get_db)) -> User:
    uid = read_token(session, "session") if session else None
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active:
        raise HTTPException(401, "Потрібен вхід")
    return user


def require(*roles: Role):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Недостатньо прав")
        return user
    return dep


admin_only = require(Role.admin)
can_write = require(Role.admin, Role.operator)


def has_section(user: User, section: str) -> bool:
    allowed = [s for s in (user.allowed_sections or []) if s]
    if user.role == Role.admin and not allowed:
        return True
    if allowed:
        return section in allowed
    return section not in DEFAULT_RESTRICTED_SECTIONS


def require_section(section: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_section(user, section):
            raise HTTPException(403, "Немає доступу до цього розділу")
        return user
    return dep


def actor_of(user: User) -> str:
    return str(user.id)
