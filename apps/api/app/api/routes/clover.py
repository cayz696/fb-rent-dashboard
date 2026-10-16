import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request as HttpRequest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, can_write, current_user
from app.core.config import settings
from app.core.db import get_db
from app.integrations.clover_mapper import normalize_ad_account_id
from app.models import Account, SpendSnapshot, User
from app.schemas.api import CloverStatus, LinkIn, SpendPoint, UnmatchedOut
from app.services import accounts as acc_svc
from app.services import spend as spend_svc

router = APIRouter(prefix="/api", tags=["clover"])


def _check_secret(header: str | None, token: str | None):
    expected = settings.clover_spend_secret
    if not expected:
        raise HTTPException(503, "CLOVER_SPEND_SECRET не налаштовано")
    given = header or token or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Невірний секрет")


@router.post("/clover/spend")
async def receive_spend(
    request: HttpRequest, db: Session = Depends(get_db),
    x_clover_secret: str | None = Header(default=None), token: str | None = Query(default=None),
):
    """Прийом Clover Spend Export. Авторизація: заголовок X-Clover-Secret або ?token=."""
    _check_secret(x_clover_secret, token)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Очікується JSON")
    result = spend_svc.ingest(db, payload)
    db.commit()
    return result


@router.get("/clover/status", response_model=CloverStatus)
def status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    last = spend_svc.last_received(db)
    return CloverStatus(
        last_received=last,
        stale=bool(last and datetime.now(timezone.utc) - last > timedelta(hours=spend_svc.STALE_HOURS)),
        snapshots=db.scalar(select(func.count()).select_from(SpendSnapshot)) or 0,
        unmatched=len(_unmatched(db)),
    )


def _unmatched(db: Session) -> list[UnmatchedOut]:
    rows = db.execute(
        select(SpendSnapshot.ad_account_id, func.count(), func.max(SpendSnapshot.received_at))
        .where(SpendSnapshot.account_id.is_(None), SpendSnapshot.ad_account_id != "?")
        .group_by(SpendSnapshot.ad_account_id)
    ).all()
    latest = spend_svc.latest_by_ad(db, [r[0] for r in rows])
    return [
        UnmatchedOut(ad_account_id=ad, spend_today=latest[ad].spend_today, spend_total=latest[ad].spend_total, snapshots=n, last_received=last)
        for ad, n, last in rows
    ]


@router.get("/clover/unmatched", response_model=list[UnmatchedOut])
def unmatched(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _unmatched(db)


@router.post("/clover/link", response_model=dict)
def link(body: LinkIn, db: Session = Depends(get_db), user: User = Depends(can_write)):
    ad = normalize_ad_account_id(body.ad_account_id)
    acc = db.get(Account, body.account_id)
    if not acc or not ad:
        raise HTTPException(404, "Акаунт не знайдено")
    other = spend_svc.find_account(db, ad)
    if other and other.id != acc.id:
        raise HTTPException(409, f"Цей кабінет уже прив'язаний до {other.code}")
    acc_svc.update_account(db, acc, actor_of(user), {"ad_account_id": ad})
    n = spend_svc.backfill(db, acc)
    db.commit()
    return {"linked_snapshots": n, "code": acc.code}


@router.get("/accounts/{account_id}/spend", response_model=list[SpendPoint])
def account_spend(account_id: uuid.UUID, days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db), _: User = Depends(current_user)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Акаунт не знайдено")
    ad = normalize_ad_account_id(acc.ad_account_id)
    return spend_svc.daily_series(db, ad, days) if ad else []
