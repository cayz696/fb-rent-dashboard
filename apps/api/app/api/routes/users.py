from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import admin_only
from app.core.db import get_db
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.api import UserAdminOut, UserCreate, UserPatch

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("", response_model=UserAdminOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Логін зайнятий")
    u = User(
        username=body.username,
        name=body.name,
        role=body.role,
        password_hash=hash_password(body.password),
        allowed_sections=body.allowed_sections,
    )
    db.add(u)
    db.commit()
    return u


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == Role.admin, User.is_active)) or 0


@router.patch("/{uid}", response_model=UserAdminOut)
def patch_user(uid: uuid.UUID, body: UserPatch, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Користувача не знайдено")
    demoting = (body.role is not None and body.role != Role.admin) or body.is_active is False
    if demoting and u.role == Role.admin and u.is_active and _active_admins(db) <= 1:
        raise HTTPException(409, "Не можна прибрати останнього активного адміна")
    if body.name is not None:
        u.name = body.name
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    if body.reset_2fa:
        u.totp_secret, u.totp_enabled = None, False
    if "allowed_sections" in body.model_fields_set:
        u.allowed_sections = body.allowed_sections
    db.commit()
    return u
