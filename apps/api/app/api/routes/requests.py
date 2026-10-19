from __future__ import annotations
"""Заявки на видачу. Джерело: ручне створення в UI (Telegram підключиться пізніше і створюватиме ті самі заявки)."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, admin_only, can_write, current_user
from app.core.db import get_db
from app.models import Account, Client, Request, RequestStatus, Stage, User
from app.schemas.api import ProposedAccount, ProposedIn, RequestCreate, RequestOut
from app.services import accounts as acc_svc
from app.services.state_machine import TransitionError

router = APIRouter(prefix="/api/requests", tags=["requests"])
OPEN = (RequestStatus.new, RequestStatus.proposed)


def _out(db: Session, r: Request) -> RequestOut:
    accs = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(r.proposed_account_ids or [])))}
    client = db.get(Client, r.client_id) if r.client_id else None
    approver = db.get(User, r.approved_by) if r.approved_by else None
    return RequestOut(
        id=r.id, client_id=r.client_id, client_name=client.name if client else None, raw_text=r.raw_text,
        message_link=r.message_link, parsed=r.parsed, status=r.status,
        proposed=[ProposedAccount(id=a.id, code=a.code, stage=a.stage) for i in (r.proposed_account_ids or []) if (a := accs.get(i))],
        approved_by_name=approver.name if approver else None, created_at=r.created_at,
    )


def _reserved_elsewhere(db: Session, except_id: uuid.UUID | None) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for r in db.scalars(select(Request).where(Request.status.in_(OPEN))):
        if r.id != except_id:
            ids.update(r.proposed_account_ids or [])
    return ids


def _propose(db: Session, r: Request) -> None:
    """Обираємо найстаріші за датою готовності `ready`-акаунти, не зарезервовані в інших відкритих заявках."""
    qty = int((r.parsed or {}).get("qty", 1))
    busy = _reserved_elsewhere(db, r.id)
    stmt = select(Account).where(Account.stage == Stage.ready).order_by(Account.ready_at.asc().nulls_last(), Account.code)
    picked = [a for a in db.scalars(stmt) if a.id not in busy][:qty]
    r.proposed_account_ids = [a.id for a in picked]
    r.status = RequestStatus.proposed if picked else RequestStatus.new
    if len(picked) < qty:
        r.parsed = {**(r.parsed or {}), "shortage": qty - len(picked)}
    elif r.parsed and "shortage" in r.parsed:
        r.parsed = {k: v for k, v in r.parsed.items() if k != "shortage"}


def _get(db: Session, rid: uuid.UUID) -> Request:
    r = db.get(Request, rid)
    if not r:
        raise HTTPException(404, "Заявку не знайдено")
    return r


@router.get("", response_model=list[RequestOut])
def list_requests(status: list[RequestStatus] = Query(default=[]), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(Request).order_by(Request.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Request.status.in_(status))
    return [_out(db, r) for r in db.scalars(stmt)]


@router.get("/{rid}", response_model=RequestOut)
def get_request(rid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _out(db, _get(db, rid))


@router.post("", response_model=RequestOut, status_code=201)
def create_request(body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(can_write)):
    if not db.get(Client, body.client_id):
        raise HTTPException(404, "Клієнта не знайдено")
    r = Request(
        client_id=body.client_id, raw_text=body.raw_text, status=RequestStatus.new,
        parsed={"source": "manual", "intent": "issue", "qty": body.qty, "geo": body.geo, "limit": str(body.limit) if body.limit is not None else None, "created_by": actor_of(user)},
    )
    db.add(r)
    db.flush()
    _propose(db, r)
    db.commit()
    return _out(db, r)


@router.post("/{rid}/propose", response_model=RequestOut)
def repropose(rid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    r = _get(db, rid)
    if r.status not in OPEN:
        raise HTTPException(409, "Заявка вже закрита")
    _propose(db, r)
    db.commit()
    return _out(db, r)


@router.put("/{rid}/accounts", response_model=RequestOut)
def set_accounts(rid: uuid.UUID, body: ProposedIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    """«Змінити»: ручний вибір акаунтів для видачі."""
    r = _get(db, rid)
    if r.status not in OPEN:
        raise HTTPException(409, "Заявка вже закрита")
    ids = list(dict.fromkeys(body.account_ids))
    accs = db.scalars(select(Account).where(Account.id.in_(ids))).all()
    if len(accs) != len(ids) or any(a.stage != Stage.ready for a in accs):
        raise HTTPException(409, "Усі акаунти мають бути на етапі «Готовий»")
    if set(ids) & _reserved_elsewhere(db, r.id):
        raise HTTPException(409, "Частина акаунтів зарезервована в іншій заявці")
    r.proposed_account_ids = ids
    r.status = RequestStatus.proposed if ids else RequestStatus.new
    db.commit()
    return _out(db, r)


@router.post("/{rid}/approve", response_model=RequestOut)
def approve(rid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Апрув і видача: всі запропоновані акаунти → issued клієнту (все або нічого)."""
    r = _get(db, rid)
    if r.status != RequestStatus.proposed or not r.proposed_account_ids:
        raise HTTPException(409, "Немає запропонованих акаунтів для видачі")
    limit = (r.parsed or {}).get("limit")
    try:
        for aid in r.proposed_account_ids:
            acc = db.get(Account, aid)
            if not acc:
                raise TransitionError("Акаунт зник")
            acc_svc.transition(db, acc, Stage.issued, actor_of(user), client_id=r.client_id, request_id=r.id)
            if limit:
                acc_svc.update_account(db, acc, actor_of(user), {"spend_limit": Decimal(limit)})
    except TransitionError as e:
        db.rollback()
        raise HTTPException(409, f"Не вдалося видати: {e}")
    r.status = RequestStatus.done
    r.approved_by = user.id
    db.commit()
    return _out(db, r)


@router.post("/{rid}/reject", response_model=RequestOut)
def reject(rid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    r = _get(db, rid)
    if r.status not in OPEN:
        raise HTTPException(409, "Заявка вже закрита")
    r.status = RequestStatus.rejected
    r.approved_by = user.id
    db.commit()
    return _out(db, r)
