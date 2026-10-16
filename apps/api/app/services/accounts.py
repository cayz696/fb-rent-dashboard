from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountEvent, OffReason, Stage
from app.services.state_machine import CHECK_HOURS, TransitionError, TransitionInput, validate


def add_event(db: Session, account_id, type_: str, actor: str, *, from_stage=None, to_stage=None, payload=None):
    ev = AccountEvent(
        account_id=account_id, type=type_, actor=actor, from_stage=from_stage, to_stage=to_stage, payload=payload or {}
    )
    db.add(ev)
    return ev


def create_account(db: Session, actor: str, **fields) -> Account:
    acc = Account(stage=Stage.purchased, **fields)
    db.add(acc)
    db.flush()
    db.refresh(acc)  # підтягнути server_default code
    add_event(db, acc.id, "created", actor, to_stage=Stage.purchased, payload={"code": acc.code})
    return acc


def _jsonable(v):
    if isinstance(v, Decimal):
        return str(v)
    return str(v) if v is not None and not isinstance(v, (int, float, bool, str)) else v


def update_account(db: Session, acc: Account, actor: str, changes: dict) -> Account:
    diff = {}
    for k, v in changes.items():
        old = getattr(acc, k)
        if old != v:
            diff[k] = {"from": _jsonable(old), "to": _jsonable(v)}
            setattr(acc, k, v)
    if diff:
        add_event(db, acc.id, "updated", actor, payload=diff)
    return acc


def transition(
    db: Session, acc: Account, target: Stage, actor: str, *, off_reason: OffReason | None = None,
    comment: str | None = None, client_id=None, request_id=None, confirm_manual: bool = False,
    sold_to: str | None = None, sale_price=None,
) -> Account:
    effective_client = client_id or acc.client_id
    validate(TransitionInput(
        current=acc.stage, current_off_reason=acc.off_reason, target=target, off_reason=off_reason,
        comment=comment, client_id=effective_client, request_id=request_id, confirm_manual=confirm_manual,
        sold_to=sold_to, sale_price=sale_price,
    ))
    prev, prev_client = acc.stage, acc.client_id
    payload: dict = {}
    if comment:
        payload["comment"] = comment
    now = datetime.now(timezone.utc)

    acc.stage = target
    acc.off_reason = off_reason if target == Stage.off else None
    if target == Stage.checking:
        acc.check_until = now + timedelta(hours=CHECK_HOURS)
        payload["check_until"] = acc.check_until.isoformat()
    if target == Stage.ready:
        acc.check_until = None
        acc.ready_at = now
    if target == Stage.issued:
        acc.client_id = effective_client
        payload["client_id"] = str(effective_client)
        if request_id:
            payload["request_id"] = str(request_id)
        else:
            payload["manual_confirm"] = True
    if target == Stage.sold:
        acc.sold_to = sold_to
        acc.sale_price = sale_price
        acc.sold_at = now
        payload["sold_to"] = sold_to
        payload["sale_price"] = str(sale_price)
        if prev_client:  # був в оренді — звільняємо клієнта
            payload["client_id"] = str(prev_client)
            acc.client_id = None
    if target in (Stage.returned, Stage.off) and prev_client:
        payload["client_id"] = str(prev_client)
        acc.client_id = None
    if target == Stage.off:
        payload["off_reason"] = off_reason.value

    add_event(db, acc.id, "stage_change", actor, from_stage=prev, to_stage=target, payload=payload)
    return acc


def adspower_group_for(acc: Account, stage: Stage) -> str | None:
    """Етап дашборда → цільова група AdsPower (ТЗ v2). None → не переносимо."""
    if stage == Stage.ready:
        return "Готовий"
    if stage == Stage.sold:
        return "Продано"
    if stage == Stage.warmup:
        return "Прогрев"
    if stage == Stage.issued and acc.client:
        return acc.client.name  # мітка команди/клієнта, кому передано
    return None


def get_by_code(db: Session, code: str) -> Account | None:
    return db.scalar(select(Account).where(Account.code == code))


__all__ = ["create_account", "update_account", "transition", "add_event", "TransitionError"]
