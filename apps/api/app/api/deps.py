from __future__ import annotations
import uuid

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import COOKIE, read_token
from app.models import Role, User


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


def actor_of(user: User) -> str:
    return str(user.id)
