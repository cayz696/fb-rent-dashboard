from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, admin_only
from app.core.db import get_db
from app.models import Client, ClientPayment, User
from app.schemas.api import ClientReport, FinanceOverview, PaymentIn, PaymentOut
from app.services import finance as svc

# Фінанси — лише admin (operator без фінансів, viewer без цього розділу за рішенням: фінанси чутливі)
router = APIRouter(prefix="/api/finance", tags=["finance"], dependencies=[Depends(admin_only)])


@router.get("", response_model=FinanceOverview)
def overview(db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/clients/{cid}", response_model=ClientReport)
def client_report(cid: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Клієнта не знайдено")
    return svc.client_report(db, c)


@router.get("/clients/{cid}/payments", response_model=list[PaymentOut])
def payments(cid: uuid.UUID, db: Session = Depends(get_db)):
    rows = db.scalars(select(ClientPayment).where(ClientPayment.client_id == cid).order_by(ClientPayment.paid_at.desc(), ClientPayment.created_at.desc())).all()
    names = {str(u.id): u.name for u in db.scalars(select(User))}
    out = []
    for p in rows:
        o = PaymentOut.model_validate(p)
        o.created_by_name = names.get(p.created_by, p.created_by)
        out.append(o)
    return out


@router.post("/clients/{cid}/payments", response_model=PaymentOut, status_code=201)
def add_payment(cid: uuid.UUID, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not db.get(Client, cid):
        raise HTTPException(404, "Клієнта не знайдено")
    if body.amount == 0:
        raise HTTPException(422, "Сума не може бути нульовою")
    p = ClientPayment(client_id=cid, amount=body.amount, note=body.note, created_by=actor_of(user), **({"paid_at": body.paid_at} if body.paid_at else {}))
    db.add(p)
    db.commit()
    db.refresh(p)
    o = PaymentOut.model_validate(p)
    o.created_by_name = user.name
    return o
