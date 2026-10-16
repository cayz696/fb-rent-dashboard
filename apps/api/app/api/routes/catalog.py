"""Клієнти, постачальники, партії."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, admin_only, current_user
from app.core.db import get_db
from app.models import Account, Batch, Client, Role, Stage, Supplier, User
from app.schemas.api import BatchIn, BatchOut, ClientIn, ClientOut, SupplierIn, SupplierOut
from app.services import accounts as svc
from app.services import finance as fin_svc

router = APIRouter(prefix="/api", tags=["catalog"])


# ---- suppliers
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Supplier).order_by(Supplier.name)).all()


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = Supplier(**body.model_dump())
    db.add(s)
    db.commit()
    return s


@router.put("/suppliers/{sid}", response_model=SupplierOut)
def update_supplier(sid: uuid.UUID, body: SupplierIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = db.get(Supplier, sid) or _404()
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return s


@router.delete("/suppliers/{sid}", status_code=204)
def delete_supplier(sid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = db.get(Supplier, sid) or _404()
    if db.scalar(select(func.count()).select_from(Batch).where(Batch.supplier_id == sid)) or db.scalar(
        select(func.count()).select_from(Account).where(Account.supplier_id == sid)
    ):
        raise HTTPException(409, "Є пов'язані партії/акаунти")
    db.delete(s)
    db.commit()


# ---- batches
def _batch_out(db: Session, b: Batch, user: User) -> BatchOut:
    total = db.scalar(select(func.count()).select_from(Account).where(Account.batch_id == b.id)) or 0
    off = db.scalar(
        select(func.count()).select_from(Account).where(Account.batch_id == b.id, Account.stage == Stage.off)
    ) or 0
    out = BatchOut.model_validate(b)
    out.supplier_name = b.supplier.name
    out.accounts_total, out.accounts_off = total, off
    if user.role != Role.admin:
        out.unit_cost = None
    return out


@router.get("/batches", response_model=list[BatchOut])
def list_batches(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_batch_out(db, b, user) for b in db.scalars(select(Batch).order_by(Batch.bought_at.desc()))]


@router.post("/batches", response_model=BatchOut, status_code=201)
def create_batch(body: BatchIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not db.get(Supplier, body.supplier_id):
        raise HTTPException(404, "Постачальника не знайдено")
    data = body.model_dump(exclude={"create_accounts"}, exclude_none=True)
    b = Batch(**data)
    db.add(b)
    db.flush()
    if body.create_accounts:
        for _ in range(body.qty):
            svc.create_account(db, actor_of(user), supplier_id=b.supplier_id, batch_id=b.id, purchase_cost=b.unit_cost)
    db.commit()
    db.refresh(b)
    return _batch_out(db, b, user)


# ---- clients
def _client_out(db: Session, c: Client) -> ClientOut:
    out = ClientOut.model_validate(c)
    out.accounts_issued = db.scalar(
        select(func.count()).select_from(Account).where(Account.client_id == c.id, Account.stage == Stage.issued)
    ) or 0
    out.current_balance = fin_svc.client_report(db, c)["balance"]
    return out


@router.get("/clients", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_client_out(db, c) for c in db.scalars(select(Client).order_by(Client.name))]


@router.get("/clients/{cid}", response_model=ClientOut)
def get_client(cid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _client_out(db, db.get(Client, cid) or _404())


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    return _client_out(db, c)


@router.put("/clients/{cid}", response_model=ClientOut)
def update_client(cid: uuid.UUID, body: ClientIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    c = db.get(Client, cid) or _404()
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _client_out(db, c)


@router.delete("/clients/{cid}", status_code=204)
def delete_client(cid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    c = db.get(Client, cid) or _404()
    if db.scalar(select(func.count()).select_from(Account).where(Account.client_id == cid)):
        raise HTTPException(409, "У клієнта є акаунти")
    db.delete(c)
    db.commit()


def _404():
    raise HTTPException(404, "Не знайдено")
