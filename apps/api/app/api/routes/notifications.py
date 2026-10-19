from __future__ import annotations
"""Сповіщення: єдиний список актуального, що потребує уваги — заявки, сигнали, помилки bridge.
Агрегується на льоту (без окремої таблиці). «Непрочитані» клієнт рахує по last_seen."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.db import get_db
from app.models import BridgeCommand, Client, CommandStatus, Request, RequestStatus, User
from app.services import signals as signals_svc

router = APIRouter(prefix="/api", tags=["notifications"])


class Notification(BaseModel):
    type: str
    severity: str  # info | warning | danger
    title: str
    message: str
    link: str | None = None
    created_at: datetime


class Notifications(BaseModel):
    count: int
    items: list[Notification]


@router.get("/notifications", response_model=Notifications)
def notifications(db: Session = Depends(get_db), _: User = Depends(current_user)):
    items: list[Notification] = []

    # відкриті заявки
    reqs = db.scalars(
        select(Request).where(Request.status.in_((RequestStatus.new, RequestStatus.proposed)))
        .order_by(Request.created_at.desc()).limit(50)
    ).all()
    names = dict(db.execute(select(Client.id, Client.name)).all())
    for r in reqs:
        proposed = len(r.proposed_account_ids or [])
        items.append(Notification(
            type="request", severity="warning" if r.status == RequestStatus.proposed else "info",
            title=f"Заявка: {names.get(r.client_id, '—')}",
            message=(r.raw_text or "")[:120] + (f" · підібрано {proposed}" if proposed else ""),
            link="/requests", created_at=r.created_at,
        ))

    # сигнали (перевірка 24г, проблемні оголошення, нульовий спенд, баланси, звірка FBM, clover/bridge офлайн)
    now = datetime.now(timezone.utc)
    for s in signals_svc.compute(db):
        link = f"/accounts/{s.account_id}" if s.account_id else ("/buyers" if s.type in ("low_balance", "team_low_balance", "fbm_discrepancy") else None)
        items.append(Notification(
            type=f"signal:{s.type}", severity=s.severity,
            title=s.code or "Сигнал", message=s.message,
            link=link, created_at=now,
        ))

    # помилки bridge за добу
    since = now - timedelta(hours=24)
    errs = db.scalars(
        select(BridgeCommand).where(BridgeCommand.status == CommandStatus.error, BridgeCommand.done_at >= since)
        .order_by(BridgeCommand.done_at.desc()).limit(20)
    ).all()
    for c in errs:
        items.append(Notification(
            type="bridge_error", severity="danger", title="AdsPower: помилка",
            message=f"{c.command}: {(c.result or {}).get('error', '')}"[:160],
            link=None, created_at=c.done_at or now,
        ))

    items.sort(key=lambda n: n.created_at, reverse=True)
    return Notifications(count=len(items), items=items[:100])
