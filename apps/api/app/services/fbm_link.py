"""Звʼязок карток FBM з акаунтами по card_last4 (зі знімка fbm_cards_snapshot).
Дає спенд/статус/баланс картки на рівні акаунта. §4: лише масковані дані."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import SystemState

SNAPSHOT_KEY = "fbm_cards_snapshot"
_VALID = "VALID CARD"


def _rank(card: dict) -> tuple:
    """Пріоритет при кількох картках з однаковим last4: активна + більший спенд."""
    return (card.get("status") == _VALID, float(card.get("spend") or 0))


def cards_by_last4(db: Session) -> dict[str, dict]:
    st = db.get(SystemState, SNAPSHOT_KEY)
    rows = (st.value.get("cards") if st else []) or []
    out: dict[str, dict] = {}
    for r in rows:
        l4 = r.get("last4")
        if not l4:
            continue
        if l4 not in out or _rank(r) > _rank(out[l4]):
            out[l4] = r
    return out


def account_cards(accounts, db: Session) -> dict:
    """{account.id: card_dict} для акаунтів із заповненим card_last4."""
    idx = cards_by_last4(db)
    return {a.id: idx[a.card_last4] for a in accounts if a.card_last4 and a.card_last4 in idx}
