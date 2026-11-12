from __future__ import annotations
"""API Задачника команди, інтеграції з особистим Telegram-акаунтом (MTProto) та ШІ-парсера контексту."""
import datetime as dt
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, admin_only, can_write, current_user
from app.core.db import get_db
from app.models import Buyer, Client, Team, TeamTask, TelegramGroup, TelegramMessageLog, User
from app.services import task_ai_parser, task_notify, telegram_tasks

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
log = logging.getLogger("fbrent.tasks")
_TASK_CATEGORIES = {"issue_accounts", "card_issue", "bm_share", "account_check", "procurement", "finance", "general"}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic-схеми
# ─────────────────────────────────────────────────────────────────────────────

class TaskCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    raw_source_text: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    category: str = "general"
    assignee_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    buyer_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    due_at: Optional[dt.datetime] = None
    checklist: Optional[List[Dict[str, Any]]] = None
    use_ai_enrichment: bool = True


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    buyer_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    due_at: Optional[dt.datetime] = None
    checklist: Optional[List[Dict[str, Any]]] = None


class TaskCommentIn(BaseModel):
    text: str


class TelegramGroupCreateIn(BaseModel):
    chat_id: int
    title: str
    username: Optional[str] = None
    chat_type: str = "supergroup"
    is_monitored: bool = True
    auto_create_tasks: bool = True
    team_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    default_assignee_id: Optional[uuid.UUID] = None
    topic_filter: Optional[str] = None


class CreateFromThreadIn(BaseModel):
    chat_id: int
    topic_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    buyer_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None


class TelegramGroupPatchIn(BaseModel):
    title: Optional[str] = None
    username: Optional[str] = None
    is_monitored: Optional[bool] = None
    auto_create_tasks: Optional[bool] = None
    team_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    default_assignee_id: Optional[uuid.UUID] = None
    topic_filter: Optional[str] = None


class SimulateMessageIn(BaseModel):
    group_id: Optional[uuid.UUID] = None
    sender_username: Optional[str] = "WebLumi"
    sender_name: Optional[str] = "Igor Buyer"
    raw_text: str
    reply_to_msg_id: Optional[int] = None
    force_create_task: bool = False


class TelegramSendCodeIn(BaseModel):
    api_id: int
    api_hash: str = ""
    phone: str


class TelegramVerifyCodeIn(BaseModel):
    code: str
    password: Optional[str] = None


class AiConfigUpdateIn(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    confidence_threshold: Optional[int] = Field(default=None, ge=10, le=100)
    ignore_short_noise: Optional[bool] = None
    auto_assign_by_category: Optional[bool] = None
    system_prompt: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Серіалізатори
# ─────────────────────────────────────────────────────────────────────────────

def _chat_context_by_task(db: Session, tasks: List[TeamTask]) -> Dict[uuid.UUID, List[Dict[str, Any]]]:
    """Кілька реплік чату перед коротким повідомленням, з якого зібрана задача."""
    ids = [t.id for t in tasks if t.source == "telegram"]
    if not ids:
        return {}
    anchors = list(db.scalars(select(TelegramMessageLog).where(TelegramMessageLog.task_id.in_(ids))).all())
    by_task: Dict[uuid.UUID, TelegramMessageLog] = {}
    for row in anchors:
        if row.task_id and row.task_id not in by_task:
            by_task[row.task_id] = row
    if not by_task:
        return {}
    times = [row.sent_at for row in by_task.values() if row.sent_at]
    chat_ids = {row.chat_id for row in by_task.values()}
    q = select(TelegramMessageLog).where(TelegramMessageLog.chat_id.in_(chat_ids))
    if times:
        q = q.where(TelegramMessageLog.sent_at >= min(times) - dt.timedelta(days=2))
        q = q.where(TelegramMessageLog.sent_at <= max(times) + dt.timedelta(minutes=1))
    rows = list(
        db.scalars(q.order_by(TelegramMessageLog.chat_id, TelegramMessageLog.sent_at, TelegramMessageLog.id)).all()
    )
    by_chat: Dict[int, List[TelegramMessageLog]] = {}
    for row in rows:
        by_chat.setdefault(row.chat_id, []).append(row)
    out: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    for task_id, anchor in by_task.items():
        seq = by_chat.get(anchor.chat_id, [])
        idx = next((i for i, row in enumerate(seq) if row.id == anchor.id), None)
        window = [anchor] if idx is None else seq[max(0, idx - 4) : idx + 1]
        out[task_id] = [
            {
                "id": row.id,
                "sender_username": row.sender_username,
                "sender_name": row.sender_name,
                "is_support": task_ai_parser.is_support_sender(row.sender_username, row.sender_name),
                "raw_text": row.raw_text,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "is_trigger": row.id == anchor.id,
            }
            for row in window
        ]
    return out


def _serialize_task(
    t: TeamTask,
    users_map: Dict[uuid.UUID, User],
    teams_map: Dict[uuid.UUID, Team],
    buyers_map: Dict[uuid.UUID, Buyer],
    clients_map: Dict[uuid.UUID, Client],
    chat_context: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    assignee = users_map.get(t.assignee_id) if t.assignee_id else None
    creator = users_map.get(t.creator_id) if t.creator_id else None
    team = teams_map.get(t.team_id) if t.team_id else None
    buyer = buyers_map.get(t.buyer_id) if t.buyer_id else None
    client = clients_map.get(t.client_id) if t.client_id else None
    chk = t.checklist or []
    done_cnt = sum(1 for item in chk if isinstance(item, dict) and item.get("done"))

    return {
        "id": str(t.id),
        "code": t.code,
        "title": t.title,
        "description": t.description,
        "raw_source_text": t.raw_source_text,
        "status": t.status,
        "priority": t.priority,
        "category": t.category,
        "source": t.source,
        "telegram_group_id": str(t.telegram_group_id) if t.telegram_group_id else None,
        "telegram_chat_title": t.telegram_chat_title,
        "telegram_sender": t.telegram_sender,
        "telegram_message_link": t.telegram_message_link,
        "assignee_id": str(t.assignee_id) if t.assignee_id else None,
        "assignee_name": assignee.name if assignee else None,
        "creator_id": str(t.creator_id) if t.creator_id else None,
        "creator_name": creator.name if creator else None,
        "team_id": str(t.team_id) if t.team_id else None,
        "team_name": team.name if team else None,
        "buyer_id": str(t.buyer_id) if t.buyer_id else None,
        "buyer_name": buyer.name if buyer else None,
        "client_id": str(t.client_id) if t.client_id else None,
        "client_name": client.name if client else None,
        "linked_request_id": str(t.linked_request_id) if t.linked_request_id else None,
        "checklist": chk,
        "checklist_done": done_cnt,
        "checklist_total": len(chk),
        "ai_context": t.ai_context or {},
        "chat_context": chat_context or [],
        "comments": t.comments or [],
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _serialize_group(
    g: TelegramGroup,
    teams_map: Dict[uuid.UUID, Team],
    clients_map: Dict[uuid.UUID, Client],
    users_map: Dict[uuid.UUID, User],
) -> Dict[str, Any]:
    team = teams_map.get(g.team_id) if g.team_id else None
    client = clients_map.get(g.client_id) if g.client_id else None
    assignee = users_map.get(g.default_assignee_id) if g.default_assignee_id else None
    return {
        "id": str(g.id),
        "chat_id": g.chat_id,
        "title": g.title,
        "username": g.username,
        "chat_type": g.chat_type,
        "is_monitored": g.is_monitored,
        "auto_create_tasks": g.auto_create_tasks,
        "team_id": str(g.team_id) if g.team_id else None,
        "team_name": team.name if team else None,
        "client_id": str(g.client_id) if g.client_id else None,
        "client_name": client.name if client else None,
        "default_assignee_id": str(g.default_assignee_id) if g.default_assignee_id else None,
        "default_assignee_name": assignee.name if assignee else None,
        "topic_filter": g.topic_filter,
        "messages_parsed": g.messages_parsed or 0,
        "tasks_created": g.tasks_created or 0,
        "last_message_at": g.last_message_at.isoformat() if g.last_message_at else None,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _serialize_log(l: TelegramMessageLog, tasks_map: Dict[uuid.UUID, TeamTask]) -> Dict[str, Any]:
    t = tasks_map.get(l.task_id) if l.task_id else None
    return {
        "id": l.id,
        "group_id": str(l.group_id) if l.group_id else None,
        "chat_id": l.chat_id,
        "chat_title": l.chat_title,
        "message_id": l.message_id,
        "reply_to_msg_id": l.reply_to_msg_id,
        "sender_username": l.sender_username,
        "sender_name": l.sender_name,
        "raw_text": l.raw_text,
        "message_link": l.message_link,
        "is_actionable": l.is_actionable,
        "ai_intent": l.ai_intent,
        "ai_confidence": l.ai_confidence,
        "ai_extracted": l.ai_extracted or {},
        "task_id": str(l.task_id) if l.task_id else None,
        "task_code": t.code if t else None,
        "task_status": t.status if t else None,
        "sent_at": l.sent_at.isoformat() if l.sent_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Головний ендпоінт огляду Задачника
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_tasks_overview(
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    team_id: Optional[uuid.UUID] = Query(default=None),
    buyer_id: Optional[uuid.UUID] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    telegram_tasks.ensure_initial_structure(db)

    users_map = {u.id: u for u in db.scalars(select(User).where(User.is_active == True).order_by(User.name)).all()}  # noqa: E712
    teams_map = {t.id: t for t in db.scalars(select(Team).order_by(Team.name)).all()}
    buyers_map = {b.id: b for b in db.scalars(select(Buyer).order_by(Buyer.name)).all()}
    clients_map = {c.id: c for c in db.scalars(select(Client).order_by(Client.name)).all()}

    all_tasks = db.scalars(select(TeamTask).order_by(TeamTask.created_at.desc())).all()
    tasks_by_id = {t.id: t for t in all_tasks}

    # Статистика по всіх задачах
    total_logs = db.scalar(select(func.count()).select_from(TelegramMessageLog)) or 0
    noise_logs = db.scalar(select(func.count()).select_from(TelegramMessageLog).where(TelegramMessageLog.is_actionable == False)) or 0  # noqa: E712

    stats = {
        "total": len([t for t in all_tasks if t.status != "rejected"]),
        "inbox": sum(1 for t in all_tasks if t.status == "inbox"),
        "todo": sum(1 for t in all_tasks if t.status == "todo"),
        "in_progress": sum(1 for t in all_tasks if t.status == "in_progress"),
        "review": sum(1 for t in all_tasks if t.status == "review"),
        "done": sum(1 for t in all_tasks if t.status == "done"),
        "rejected": sum(1 for t in all_tasks if t.status == "rejected"),
        "urgent": sum(1 for t in all_tasks if t.priority == "urgent" and t.status not in ("done", "rejected")),
        "from_telegram": sum(1 for t in all_tasks if t.source == "telegram"),
        "messages_total": total_logs,
        "noise_filtered": noise_logs,
    }

    # Фільтрація списку задач
    filtered = all_tasks
    if status:
        filtered = [t for t in filtered if t.status == status]
    if category:
        filtered = [t for t in filtered if t.category == category]
    if priority:
        filtered = [t for t in filtered if t.priority == priority]
    if assignee_id:
        filtered = [t for t in filtered if t.assignee_id == assignee_id]
    if team_id:
        filtered = [t for t in filtered if t.team_id == team_id]
    if buyer_id:
        filtered = [t for t in filtered if t.buyer_id == buyer_id]
    if q:
        q_low = q.strip().lower()
        filtered = [
            t for t in filtered
            if q_low in (t.title or "").lower()
            or q_low in (t.code or "").lower()
            or q_low in (t.raw_source_text or "").lower()
            or q_low in (t.telegram_sender or "").lower()
            or q_low in (t.description or "").lower()
        ]

    groups = db.scalars(select(TelegramGroup).order_by(TelegramGroup.created_at.asc())).all()
    recent_logs = db.scalars(select(TelegramMessageLog).order_by(TelegramMessageLog.sent_at.desc(), TelegramMessageLog.id.desc()).limit(60)).all()
    threads = telegram_tasks.build_conversation_threads(db, groups, tasks_by_id)

    chat_context = _chat_context_by_task(db, filtered)
    return {
        "stats": stats,
        "tasks": [
            _serialize_task(t, users_map, teams_map, buyers_map, clients_map, chat_context.get(t.id))
            for t in filtered
        ],
        "groups": [_serialize_group(g, teams_map, clients_map, users_map) for g in groups],
        "threads": threads,
        "recent_messages": [_serialize_log(l, tasks_by_id) for l in recent_logs],
        "telegram_state": telegram_tasks.get_telegram_state(db),
        "ai_config": task_ai_parser.public_ai_config(db),
        "users": [{"id": str(u.id), "name": u.name, "username": u.username, "role": u.role.value} for u in users_map.values()],
        "teams": [{"id": str(t.id), "name": t.name} for t in teams_map.values()],
        "buyers": [{"id": str(b.id), "name": b.name, "team_id": str(b.team_id) if b.team_id else None} for b in buyers_map.values()],
        "clients": [{"id": str(c.id), "name": c.name} for c in clients_map.values()],
    }


@router.post("/from-thread", status_code=201)
def create_task_from_thread_endpoint(body: CreateFromThreadIn, db: Session = Depends(get_db), user: User = Depends(can_write)):
    try:
        t = telegram_tasks.create_task_from_thread(
            db=db,
            chat_id=body.chat_id,
            topic_id=body.topic_id,
            title=body.title,
            description=body.description,
            category=body.category,
            priority=body.priority,
            assignee_id=body.assignee_id,
            buyer_id=body.buyer_id,
            team_id=body.team_id,
            creator=user,
        )
        return {"id": str(t.id), "code": t.code, "title": t.title}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Операції з задачами
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_task(body: TaskCreateIn, db: Session = Depends(get_db), user: User = Depends(can_write)):
    title = body.title.strip()
    desc = body.description
    category = body.category
    priority = body.priority
    checklist = body.checklist or []
    ai_context: Dict[str, Any] = {}
    buyer_id = body.buyer_id
    team_id = body.team_id
    client_id = body.client_id

    if body.use_ai_enrichment:
        source_txt = body.raw_source_text or f"{title}\n{desc or ''}".strip()
        ai_res = task_ai_parser.analyze_telegram_message(
            db=db,
            raw_text=source_txt,
            sender_name=user.name,
            chat_title="Ручне створення",
            group_team_id=team_id,
            group_client_id=client_id,
        )
        ents = ai_res.get("entities") or {}
        if not buyer_id and ents.get("buyer_id"):
            buyer_id = uuid.UUID(ents["buyer_id"])
        if not team_id and ents.get("team_id"):
            team_id = uuid.UUID(ents["team_id"])
        if not client_id and ents.get("client_id"):
            client_id = uuid.UUID(ents["client_id"])
        if category == "general" and ai_res.get("category") not in ("general", "noise"):
            category = ai_res["category"]
        if not checklist and ai_res.get("checklist"):
            checklist = ai_res["checklist"]
        ai_context = {
            "confidence": ai_res.get("confidence", 90),
            "engine": ai_res.get("engine", "domain_ai_v2"),
            "reasoning": ai_res.get("reasoning"),
            "suggested_reply": ai_res.get("suggested_reply"),
            "account_codes": ents.get("account_codes") or [],
            "card_last4": ents.get("card_last4") or [],
            "bm_id": ents.get("bm_id"),
            "qty": ents.get("qty"),
            "geo": ents.get("geo"),
            "limit": ents.get("limit"),
        }

    t = TeamTask(
        title=title,
        description=desc,
        raw_source_text=body.raw_source_text,
        status=body.status,
        priority=priority,
        category=category,
        source="manual",
        assignee_id=body.assignee_id,
        creator_id=user.id,
        team_id=team_id,
        buyer_id=buyer_id,
        client_id=client_id,
        due_at=body.due_at,
        checklist=checklist,
        ai_context=ai_context,
        comments=[
            {
                "id": str(uuid.uuid4())[:8],
                "author": user.name,
                "text": "Задачу створено в панелі управління.",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        ],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    task_notify.notify_assigned(db, t, actor_id=user.id)
    db.commit()
    return {"id": str(t.id), "code": t.code}


@router.patch("/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskPatchIn, db: Session = Depends(get_db), user: User = Depends(can_write)):
    t = db.get(TeamTask, task_id)
    if not t:
        raise HTTPException(404, "Задачу не знайдено")

    old_status = t.status
    old_assignee = t.assignee_id
    fields_set = body.model_fields_set
    if "title" in fields_set and body.title is not None:
        t.title = body.title.strip()
    if "description" in fields_set:
        t.description = body.description
    if "status" in fields_set and body.status is not None:
        t.status = body.status
        if body.status == "done" and old_status != "done":
            t.completed_at = dt.datetime.now(dt.timezone.utc)
        elif body.status != "done":
            t.completed_at = None
    if "priority" in fields_set and body.priority is not None:
        t.priority = body.priority
    if "category" in fields_set and body.category is not None:
        t.category = body.category
    if "assignee_id" in fields_set:
        t.assignee_id = body.assignee_id
    if "team_id" in fields_set:
        t.team_id = body.team_id
    if "buyer_id" in fields_set:
        t.buyer_id = body.buyer_id
    if "client_id" in fields_set:
        t.client_id = body.client_id
    if "due_at" in fields_set:
        t.due_at = body.due_at
    if "checklist" in fields_set and body.checklist is not None:
        t.checklist = body.checklist

    if "assignee_id" in fields_set and t.assignee_id != old_assignee:
        task_notify.notify_assigned(db, t, actor_id=user.id)
    if "status" in fields_set and body.status is not None:
        task_notify.notify_status(db, t, old_status, t.status, actor_id=user.id)
    db.commit()
    return {"ok": True, "id": str(t.id), "status": t.status}


@router.post("/{task_id}/comments")
def add_task_comment(task_id: uuid.UUID, body: TaskCommentIn, db: Session = Depends(get_db), user: User = Depends(can_write)):
    t = db.get(TeamTask, task_id)
    if not t:
        raise HTTPException(404, "Задачу не знайдено")
    text_val = body.text.strip()
    if not text_val:
        raise HTTPException(400, "Порожній коментар")

    comments = list(t.comments or [])
    comments.append(
        {
            "id": str(uuid.uuid4())[:8],
            "author": user.name,
            "text": text_val,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    t.comments = comments
    db.commit()
    return {"ok": True, "comments": t.comments}


@router.post("/{task_id}/convert-to-request")
def convert_to_request(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(can_write)):
    t = db.get(TeamTask, task_id)
    if not t:
        raise HTTPException(404, "Задачу не знайдено")
    req = telegram_tasks.convert_task_to_account_request(db, t, actor_of(user))
    return {"ok": True, "request_id": str(req.id), "proposed_count": len(req.proposed_account_ids or [])}


@router.delete("/{task_id}")
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    t = db.get(TeamTask, task_id)
    if not t:
        raise HTTPException(404, "Задачу не знайдено")
    # Відв'язуємо логи повідомлень перед видаленням
    for l in db.scalars(select(TelegramMessageLog).where(TelegramMessageLog.task_id == t.id)).all():
        l.task_id = None
    db.delete(t)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Telegram-групи та потік повідомлень
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/groups", status_code=201)
def create_telegram_group(body: TelegramGroupCreateIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    existing = db.scalar(select(TelegramGroup).where(TelegramGroup.chat_id == body.chat_id))
    if existing:
        existing.title = body.title.strip()
        existing.is_monitored = body.is_monitored
        existing.auto_create_tasks = body.auto_create_tasks
        if body.team_id is not None:
            existing.team_id = body.team_id
        if body.client_id is not None:
            existing.client_id = body.client_id
        if body.default_assignee_id is not None:
            existing.default_assignee_id = body.default_assignee_id
        if body.topic_filter is not None:
            existing.topic_filter = body.topic_filter
        db.commit()
        return {"id": str(existing.id), "updated": True}

    g = TelegramGroup(
        chat_id=body.chat_id,
        title=body.title.strip(),
        username=body.username.strip() if body.username else None,
        chat_type=body.chat_type,
        is_monitored=body.is_monitored,
        auto_create_tasks=body.auto_create_tasks,
        team_id=body.team_id,
        client_id=body.client_id,
        default_assignee_id=body.default_assignee_id,
        topic_filter=body.topic_filter,
    )
    db.add(g)
    db.commit()
    return {"id": str(g.id), "updated": False}


@router.patch("/groups/{group_id}")
def patch_telegram_group(group_id: uuid.UUID, body: TelegramGroupPatchIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    g = db.get(TelegramGroup, group_id)
    if not g:
        raise HTTPException(404, "Групу не знайдено")
    fset = body.model_fields_set
    if "title" in fset and body.title is not None:
        g.title = body.title.strip()
    if "username" in fset:
        g.username = body.username
    if "is_monitored" in fset and body.is_monitored is not None:
        g.is_monitored = body.is_monitored
    if "auto_create_tasks" in fset and body.auto_create_tasks is not None:
        g.auto_create_tasks = body.auto_create_tasks
    if "team_id" in fset:
        g.team_id = body.team_id
    if "client_id" in fset:
        g.client_id = body.client_id
    if "default_assignee_id" in fset:
        g.default_assignee_id = body.default_assignee_id
    if "topic_filter" in fset:
        g.topic_filter = body.topic_filter
    db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}")
def delete_telegram_group(
    group_id: uuid.UUID,
    delete_tasks: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(can_write),
):
    g = db.get(TelegramGroup, group_id)
    if not g:
        raise HTTPException(404, "Групу не знайдено")

    logs = db.scalars(
        select(TelegramMessageLog).where(
            or_(TelegramMessageLog.group_id == g.id, TelegramMessageLog.chat_id == g.chat_id)
        )
    ).all()
    tasks = db.scalars(select(TeamTask).where(TeamTask.telegram_group_id == g.id)).all()

    if delete_tasks:
        for l in logs:
            db.delete(l)
        db.flush()
        for t in tasks:
            db.delete(t)
        db.flush()
    else:
        for l in logs:
            l.group_id = None
        for t in tasks:
            t.telegram_group_id = None

    db.delete(g)
    db.commit()
    return {"ok": True, "deleted_tasks": len(tasks) if delete_tasks else 0, "deleted_logs": len(logs) if delete_tasks else 0}


@router.post("/simulate-message")
def simulate_incoming_telegram_message(body: SimulateMessageIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    """Приймає реальне або тестове повідомлення, проганяє через ШІ-аналізатор контексту та логує/створює задачу."""
    group: Optional[TelegramGroup] = None
    if body.group_id:
        group = db.get(TelegramGroup, body.group_id)
    if not group:
        group = db.scalar(select(TelegramGroup).order_by(TelegramGroup.created_at.asc()))
    if not group:
        telegram_tasks.ensure_initial_structure(db)
        group = db.scalar(select(TelegramGroup).order_by(TelegramGroup.created_at.asc()))
    if not group:
        raise HTTPException(400, "Спочатку додайте хоча б одну групу для моніторингу")

    res = telegram_tasks.ingest_message(
        db=db,
        group=group,
        raw_text=body.raw_text,
        sender_username=body.sender_username,
        sender_name=body.sender_name,
        reply_to_msg_id=body.reply_to_msg_id,
        force_create_task=body.force_create_task,
        allow_auto_task=True,
    )
    return res


@router.post("/messages/{log_id}/create-task")
def force_create_task_from_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(can_write)):
    """Примусово перетворює повідомлення з потоку Telegram на задачу (якщо ШІ пропустив його або була низька впевненість)."""
    l = db.get(TelegramMessageLog, log_id)
    if not l:
        raise HTTPException(404, "Повідомлення не знайдено")
    if l.task_id:
        return {"ok": True, "task_id": str(l.task_id)}

    group = db.get(TelegramGroup, l.group_id) if l.group_id else None
    ai_res = l.ai_extracted if isinstance(l.ai_extracted, dict) else {}
    ents = ai_res.get("entities") if isinstance(ai_res.get("entities"), dict) else {}

    def _uuid(value):
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError):
            return None

    b_id = _uuid(ents.get("buyer_id"))
    t_id = _uuid(ents.get("team_id")) or (group.team_id if group else None)
    c_id = _uuid(ents.get("client_id")) or (group.client_id if group else None)

    cat = ai_res.get("category") if ai_res.get("category") in _TASK_CATEGORIES else "general"
    title = ai_res.get("title") if isinstance(ai_res.get("title"), str) else ""
    if not title or title in ("Повідомлення без задачі (чат)", "Інформаційне повідомлення"):
        raw = l.raw_text or "Задача з Telegram"
        title = (raw[:80] + "…") if len(raw) > 80 else raw
    title = title[:250]
    sender = f"@{l.sender_username}" if l.sender_username else (l.sender_name or "Учасник")

    task = TeamTask(
        title=title,
        description=ai_res.get("description") or f"Створено вручну з повідомлення у «{l.chat_title or 'Telegram'}»",
        raw_source_text=l.raw_text,
        status="inbox",
        priority=ai_res.get("priority") if ai_res.get("priority") in ("low", "medium", "high", "urgent") else "medium",
        category=cat,
        source="telegram",
        telegram_group_id=l.group_id,
        telegram_chat_title=(l.chat_title or "")[:250] or None,
        telegram_sender=sender[:120],
        telegram_message_link=l.message_link,
        assignee_id=group.default_assignee_id if group else user.id,
        creator_id=user.id,
        team_id=t_id,
        buyer_id=b_id,
        client_id=c_id,
        checklist=ai_res.get("checklist") if isinstance(ai_res.get("checklist"), list) and ai_res.get("checklist") else task_ai_parser._build_checklist(cat, ents),
        ai_context={
            "confidence": ai_res.get("confidence", 75),
            "engine": ai_res.get("engine", "manual_promote"),
            "reasoning": "Задача створена оператором із потоку повідомлень Telegram.",
            "suggested_reply": ai_res.get("suggested_reply") or "Прийнято в роботу!",
            "account_codes": ents.get("account_codes") or [],
            "card_last4": ents.get("card_last4") or [],
            "bm_id": ents.get("bm_id"),
            "qty": ents.get("qty"),
            "geo": ents.get("geo"),
            "limit": ents.get("limit"),
        },
    )
    db.add(task)
    try:
        db.flush()
        l.task_id = task.id
        l.is_actionable = True
        if group:
            group.tasks_created = (group.tasks_created or 0) + 1
        db.commit()
        db.refresh(task)
        task_notify.notify_assigned(db, task, actor_id=user.id)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log.exception("create task from telegram log %s failed", log_id)
        raise HTTPException(400, "Не вдалося створити задачу з цього повідомлення") from exc
    return {"ok": True, "task_id": str(task.id), "task_code": task.code}


# ─────────────────────────────────────────────────────────────────────────────
# Підключення особистого Telegram-акаунта (MTProto Telethon) та ШІ
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/telegram/send-code")
async def tg_send_code(body: TelegramSendCodeIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.send_login_code(db, body.api_id, body.api_hash, body.phone)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/telegram/qr")
async def tg_qr_start(db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.start_qr_login(db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/telegram/qr")
def tg_qr_view(_: User = Depends(can_write)):
    return telegram_tasks.qr_login_view()


class TelegramQrPasswordIn(BaseModel):
    password: str


@router.post("/telegram/qr/password")
async def tg_qr_password(body: TelegramQrPasswordIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.finish_qr_password(db, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/telegram/resend-code")
async def tg_resend_code(db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.resend_login_code(db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/telegram/verify-code")
async def tg_verify_code(body: TelegramVerifyCodeIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.verify_login_code(db, body.code, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/telegram/disconnect")
def tg_disconnect(db: Session = Depends(get_db), _: User = Depends(can_write)):
    return telegram_tasks.disconnect_telegram(db)


@router.get("/telegram/dialogs")
async def tg_list_dialogs(db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.fetch_telegram_dialogs(db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/telegram/sync")
async def tg_sync_now(db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return await telegram_tasks.sync_messages_from_telegram(db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/ai-config")
def update_ai_config(body: AiConfigUpdateIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    return task_ai_parser.save_ai_config(db, body.model_dump(exclude_unset=True))
