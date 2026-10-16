import asyncio
import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, can_write, current_user
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import Account, BridgeCommand, CommandStatus, User
from app.services import bridge as svc

router = APIRouter(prefix="/api", tags=["bridge"])


class CommandOut(BaseModel):
    id: uuid.UUID
    command: str
    args: dict
    status: CommandStatus
    result: dict | None
    created_by: str
    created_by_name: str | None = None
    created_at: object
    done_at: object | None


class BridgeStatus(BaseModel):
    online: bool
    last_seen: object | None
    pending: int


def _cmd_out(db: Session, c: BridgeCommand) -> CommandOut:
    name = None
    try:
        u = db.get(User, uuid.UUID(c.created_by))
        name = u.name if u else None
    except ValueError:
        name = c.created_by
    return CommandOut(id=c.id, command=c.command, args=c.args, status=c.status, result=c.result, created_by=c.created_by,
                      created_by_name=name, created_at=c.created_at, done_at=c.done_at)


@router.get("/bridge/status", response_model=BridgeStatus)
def bridge_status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return svc.status(db)


@router.get("/bridge/commands", response_model=list[CommandOut])
def list_commands(account_id: uuid.UUID | None = None, limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(BridgeCommand).order_by(BridgeCommand.created_at.desc()).limit(limit)
    if account_id:
        stmt = stmt.where(BridgeCommand.args["account_id"].astext == str(account_id))
    return [_cmd_out(db, c) for c in db.scalars(stmt)]


@router.post("/bridge/commands/{cid}/cancel", response_model=CommandOut)
def cancel(cid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    c = db.get(BridgeCommand, cid)
    if not c:
        raise HTTPException(404, "Команду не знайдено")
    if c.status != CommandStatus.pending:
        raise HTTPException(409, "Скасувати можна лише команду в черзі")
    c.status = CommandStatus.error
    c.result = {"error": "скасовано вручну"}
    db.commit()
    return _cmd_out(db, c)


def _account(db: Session, aid: uuid.UUID) -> Account:
    a = db.get(Account, aid)
    if not a:
        raise HTTPException(404, "Акаунт не знайдено")
    return a


def _open_command(db: Session, acc: Account, command: str) -> BridgeCommand | None:
    stmt = select(BridgeCommand).where(
        BridgeCommand.command == command, BridgeCommand.status.in_((CommandStatus.pending, CommandStatus.sent)),
        BridgeCommand.args["account_id"].astext == str(acc.id),
    )
    return db.scalar(stmt)


@router.post("/accounts/{aid}/adspower/create-profile", response_model=CommandOut, status_code=201)
def create_profile(aid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(can_write)):
    acc = _account(db, aid)
    if acc.adspower_profile_id:
        raise HTTPException(409, "Профіль AdsPower уже прив'язано")
    if _open_command(db, acc, "create_profile"):
        raise HTTPException(409, "Команда створення профілю вже в черзі")
    cmd = svc.enqueue(db, "create_profile", {"account_id": str(acc.id), "name": acc.code}, actor_of(user))
    db.commit()
    return _cmd_out(db, cmd)


@router.post("/accounts/{aid}/adspower/{action}", response_model=CommandOut, status_code=201)
def profile_action(aid: uuid.UUID, action: str, db: Session = Depends(get_db), user: User = Depends(can_write)):
    if action not in ("open", "close"):
        raise HTTPException(404, "Невідома дія")
    acc = _account(db, aid)
    if not acc.adspower_profile_id:
        raise HTTPException(409, "У акаунта немає профілю AdsPower")
    cmd = svc.enqueue(db, f"{action}_profile", {"account_id": str(acc.id), "profile_id": acc.adspower_profile_id}, actor_of(user))
    db.commit()
    return _cmd_out(db, cmd)


# ---------------------------------------------------------------- WebSocket для bridge
def _db_call(fn, *a):
    with SessionLocal() as db:
        return fn(db, *a)


@router.websocket("/bridge/ws")
async def bridge_ws(ws: WebSocket):
    """Протокол: bridge → {type: hello|hb|result}, сервер → {type: command}. Авторизація: Authorization: Bearer <BRIDGE_TOKEN>."""
    given = ws.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not settings.bridge_token or not hmac.compare_digest(given.encode(), settings.bridge_token.encode()):
        await ws.close(code=4401)
        return
    await ws.accept()
    await run_in_threadpool(_db_call, svc.requeue_sent)
    await run_in_threadpool(_db_call, svc.touch)

    async def sender():
        while True:
            for msg in await run_in_threadpool(_db_call, svc.claim_pending):
                await ws.send_json(msg)
            await asyncio.sleep(1)

    async def receiver():
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind in ("hello", "hb"):
                await run_in_threadpool(_db_call, svc.touch)
            elif kind == "result":
                await run_in_threadpool(_db_call, svc.complete, uuid.UUID(msg["id"]), bool(msg.get("ok")), msg.get("result"), msg.get("error"))
                await run_in_threadpool(_db_call, svc.touch)

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
