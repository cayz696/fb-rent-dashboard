"""FBM-pay у дашборді: інвентар карток (знімок), 3DS-коди (живі). Сервер сам ходить у FBM API (ключ у .env).
§4: зберігаємо лише масковані дані (last4), повний номер не чіпаємо; 3DS-коди не персистимо."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_write, current_user
from app.core.config import settings
from app.core.db import get_db
from app.integrations.fbm import Fbm, FbmError
from app.models import Account, SystemState, User

router = APIRouter(prefix="/api/fbm", tags=["fbm"])
SNAPSHOT_KEY = "fbm_cards_snapshot"


def _client() -> Fbm:
    if not settings.fbm_api_key:
        raise HTTPException(503, "FBM не налаштовано (FBM_API_KEY у .env)")
    return Fbm(settings.fbm_api_url, settings.fbm_api_key)


class FbmCardView(BaseModel):
    card_id: str
    last4: str | None
    name: str | None
    status: str | None
    payment_system: str | None
    spend: Decimal | None
    currency: str | None
    owner: str | None
    account_name: str | None
    account_balance: Decimal | None
    linked_code: str | None = None  # код нашого акаунта (по card_last4)


class FbmCards(BaseModel):
    configured: bool
    last_sync: datetime | None
    total: int
    total_spend: Decimal
    by_status: dict[str, int]
    by_account: dict[str, int]
    cards: list[FbmCardView]


class CodeView(BaseModel):
    code: str | None
    type: str | None
    at: datetime | None
    description: str | None


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    st = db.get(SystemState, SNAPSHOT_KEY)
    return {"configured": bool(settings.fbm_api_key), "last_sync": (st.value.get("at") if st else None),
            "total": (st.value.get("total") if st else 0)}


@router.post("/refresh", status_code=200)
def refresh(db: Session = Depends(get_db), _: User = Depends(can_write)):
    with _client() as f:
        try:
            cards = f.cards()
        except FbmError as e:
            raise HTTPException(502, str(e))
    rows = [{
        "card_id": c.card_id, "last4": c.last4, "name": c.name, "status": c.status,
        "payment_system": c.payment_system, "spend": str(c.spend) if c.spend is not None else None,
        "currency": c.currency, "owner": c.owner, "account_name": c.account_name,
        "account_balance": str(c.account_balance) if c.account_balance is not None else None,
    } for c in cards]
    payload = {"at": datetime.now(timezone.utc).isoformat(), "total": len(rows), "cards": rows}
    st = db.get(SystemState, SNAPSHOT_KEY)
    if st:
        st.value = payload
    else:
        db.add(SystemState(key=SNAPSHOT_KEY, value=payload))
    db.commit()
    return {"total": len(rows)}


@router.get("/cards", response_model=FbmCards)
def cards(db: Session = Depends(get_db), _: User = Depends(current_user)):
    st = db.get(SystemState, SNAPSHOT_KEY)
    rows = (st.value.get("cards") if st else []) or []
    by_last4 = {a.card_last4: a.code for a in db.scalars(select(Account).where(Account.card_last4.is_not(None)))}
    out, by_status, by_account, total_spend = [], {}, {}, Decimal(0)
    for r in rows:
        spend = Decimal(r["spend"]) if r.get("spend") else None
        if spend:
            total_spend += spend
        by_status[r.get("status") or "—"] = by_status.get(r.get("status") or "—", 0) + 1
        by_account[r.get("account_name") or "—"] = by_account.get(r.get("account_name") or "—", 0) + 1
        out.append(FbmCardView(
            card_id=r["card_id"], last4=r.get("last4"), name=r.get("name"), status=r.get("status"),
            payment_system=r.get("payment_system"), spend=spend, currency=r.get("currency"),
            owner=r.get("owner"), account_name=r.get("account_name"),
            account_balance=Decimal(r["account_balance"]) if r.get("account_balance") else None,
            linked_code=by_last4.get(r.get("last4")),
        ))
    out.sort(key=lambda c: (c.spend or Decimal(0)), reverse=True)
    return FbmCards(
        configured=bool(settings.fbm_api_key), last_sync=datetime.fromisoformat(st.value["at"]) if st else None,
        total=len(out), total_spend=total_spend.quantize(Decimal("0.01")),
        by_status=dict(sorted(by_status.items(), key=lambda x: -x[1])),
        by_account=dict(sorted(by_account.items(), key=lambda x: -x[1])), cards=out,
    )


@router.get("/cards/{card_id}/codes", response_model=list[CodeView])
def card_codes(card_id: str, type: str = "otp", _: User = Depends(current_user)):
    with _client() as f:
        try:
            codes = f.codes(card_id, type)
        except FbmError as e:
            raise HTTPException(502, str(e))
    return [CodeView(code=c.code, type=c.type, at=c.at, description=c.description) for c in codes]
