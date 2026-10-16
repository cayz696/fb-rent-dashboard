import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, can_write, current_user
from app.core.db import get_db
from app.models import Account, AccountEvent, Client, Role, Stage, User
from app.schemas.api import (
    AccountCreate, AccountList, AccountOut, AccountPatch, EventOut, TransitionIn,
)
from app.services import accounts as svc
from app.services import bridge as bridge_svc
from app.services import fbm_link as fbm_link_svc
from app.services import signals as signals_svc
from app.services import spend as spend_svc
from app.services.state_machine import TransitionError, next_stages

router = APIRouter(prefix="/api", tags=["accounts"])


def to_out(a: Account, user: User, snaps: dict | None = None, cards: dict | None = None) -> AccountOut:
    out = AccountOut.model_validate(a)
    if snaps and a.id in snaps:
        for k, v in snaps[a.id].items():
            setattr(out, k, v)
    if cards and a.id in cards:
        c = cards[a.id]
        out.card_fbm_id = c.get("card_id"); out.card_name = c.get("name"); out.card_status = c.get("status")
        out.card_spend = Decimal(c["spend"]) if c.get("spend") else None
        out.card_balance = Decimal(c["account_balance"]) if c.get("account_balance") else None
        out.card_currency = c.get("currency")
    out.supplier_name = a.supplier.name if a.supplier else None
    out.client_name = a.client.name if a.client else None
    out.next_stages = sorted(next_stages(a.stage, a.off_reason), key=lambda s: s.value)
    if user.role != Role.admin:  # фінанси — лише admin
        out.purchase_cost = None
    return out


def _get(db: Session, account_id: uuid.UUID) -> Account:
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Акаунт не знайдено")
    return acc


@router.get("/accounts/groups", response_model=list[dict])
def account_groups(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.execute(
        select(Account.adspower_group, func.count()).group_by(Account.adspower_group).order_by(func.count().desc())
    ).all()
    return [{"group": g, "count": n} for g, n in rows]


@router.get("/accounts", response_model=AccountList)
def list_accounts(
    stage: list[Stage] = Query(default=[]),
    client_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    adspower_group: str | None = None,
    signal: bool = False,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cond = []
    if stage:
        cond.append(Account.stage.in_(stage))
    if client_id:
        cond.append(Account.client_id == client_id)
    if supplier_id:
        cond.append(Account.supplier_id == supplier_id)
    if batch_id:
        cond.append(Account.batch_id == batch_id)
    if adspower_group is not None:
        cond.append(Account.adspower_group == (adspower_group or None))
    if signal:
        cond.append(Account.id.in_(signals_svc.account_ids(db)))
    if q:
        like = f"%{q.strip()}%"
        client_ids = select(Client.id).where(Client.name.ilike(like))
        cond.append(or_(
            Account.code.ilike(like), Account.ad_account_id.ilike(like), Account.adspower_profile_id.ilike(like),
            Account.bm_label.ilike(like), Account.fb_user_id.ilike(like), Account.fb_login.ilike(like), Account.client_id.in_(client_ids),
        ))
    total = db.scalar(select(func.count()).select_from(Account).where(*cond)) or 0
    rows = db.scalars(
        select(Account).where(*cond).order_by(Account.updated_at.desc(), Account.code).limit(limit).offset(offset)
    ).all()
    snaps = spend_svc.snapshot_view(list(rows), db)
    cards = fbm_link_svc.account_cards(list(rows), db)
    return AccountList(items=[to_out(a, user, snaps, cards) for a in rows], total=total)


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db), user: User = Depends(can_write)):
    fields = body.model_dump()
    if user.role != Role.admin:
        fields["purchase_cost"] = None
    acc = svc.create_account(db, actor_of(user), **fields)
    db.commit()
    return to_out(acc, user)


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    acc = _get(db, account_id)
    return to_out(acc, user, spend_svc.snapshot_view([acc], db), fbm_link_svc.account_cards([acc], db))


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(
    account_id: uuid.UUID, body: AccountPatch, db: Session = Depends(get_db), user: User = Depends(can_write)
):
    acc = _get(db, account_id)
    changes = body.model_dump(exclude_unset=True)
    if user.role != Role.admin:
        changes.pop("purchase_cost", None)
    svc.update_account(db, acc, actor_of(user), changes)
    if "ad_account_id" in changes:
        spend_svc.backfill(db, acc)
    db.commit()
    return to_out(acc, user, spend_svc.snapshot_view([acc], db))


@router.post("/accounts/{account_id}/transition", response_model=AccountOut)
def transition(
    account_id: uuid.UUID, body: TransitionIn, db: Session = Depends(get_db), user: User = Depends(can_write)
):
    acc = _get(db, account_id)
    if body.to in (Stage.issued, Stage.sold) and user.role != Role.admin:
        raise HTTPException(403, "Видачу/продаж може виконувати лише admin")
    if body.client_id and not db.get(Client, body.client_id):
        raise HTTPException(404, "Клієнта не знайдено")
    try:
        svc.transition(
            db, acc, body.to, actor_of(user), off_reason=body.off_reason, comment=body.comment,
            client_id=body.client_id, request_id=body.request_id, confirm_manual=body.confirm_manual,
            sold_to=body.sold_to, sale_price=body.sale_price,
        )
    except TransitionError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    # Авто-перенос профілю в групу AdsPower (ТЗ v2): дашборд керує розкладкою в AdsPower.
    target_group = svc.adspower_group_for(acc, body.to)
    if acc.adspower_profile_id and target_group and target_group != acc.adspower_group:
        try:
            bridge_svc.enqueue(db, "update_profile_group",
                               {"profile_id": acc.adspower_profile_id, "group": target_group}, actor_of(user))
            acc.adspower_group = target_group  # оптимістично; наступна синхронізація підтвердить
            svc.add_event(db, acc.id, "adspower_group_queued", actor_of(user), payload={"group": target_group})
        except bridge_svc.BridgeError:
            pass
    db.commit()
    return to_out(acc, user)


def _events_out(db: Session, events: list[AccountEvent]) -> list[EventOut]:
    codes = dict(db.execute(select(Account.id, Account.code).where(Account.id.in_({e.account_id for e in events}))).all())
    uids = set()
    for e in events:
        try:
            uids.add(uuid.UUID(e.actor))
        except ValueError:
            pass
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(uids))).all()) if uids else {}
    out = []
    for e in events:
        o = EventOut.model_validate(e)
        o.account_code = codes.get(e.account_id)
        try:
            o.actor_name = names.get(uuid.UUID(e.actor))
        except ValueError:
            o.actor_name = e.actor
        out.append(o)
    return out


@router.get("/accounts/{account_id}/events", response_model=list[EventOut])
def account_events(account_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    _get(db, account_id)
    ev = db.scalars(
        select(AccountEvent).where(AccountEvent.account_id == account_id).order_by(AccountEvent.id.desc())
    ).all()
    return _events_out(db, list(ev))


@router.get("/events", response_model=list[EventOut])
def all_events(
    account_id: uuid.UUID | None = None,
    type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(AccountEvent).order_by(AccountEvent.id.desc()).limit(limit)
    if account_id:
        stmt = stmt.where(AccountEvent.account_id == account_id)
    if type:
        stmt = stmt.where(AccountEvent.type == type)
    return _events_out(db, list(db.scalars(stmt).all()))
