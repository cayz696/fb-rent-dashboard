from __future__ import annotations
"""Сервіс інтеграції з особистим Telegram-акаунтом (Telethon MTProto Userbot)
та обробки повідомлень із робочих груп у Задачник Команди."""
import datetime as dt
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Buyer, Client, Request, RequestStatus, SystemState, Team, TeamTask, TelegramGroup, TelegramMessageLog, User
from app.services import task_ai_parser

TG_STATE_KEY = "telegram_userbot_state"


def get_telegram_state(db: Session) -> Dict[str, Any]:
    row = db.get(SystemState, TG_STATE_KEY)
    val = dict(row.value) if row and row.value else {}
    return {
        "status": val.get("status", "disconnected"),  # disconnected | code_sent | connected | error
        "phone": val.get("phone", ""),
        "api_id": val.get("api_id", ""),
        "api_hash_masked": ("••••" + val["api_hash"][-4:]) if val.get("api_hash") and len(str(val.get("api_hash", ""))) > 6 else "",
        "has_credentials": bool(val.get("api_id") and val.get("api_hash")),
        "account_name": val.get("account_name"),
        "account_username": val.get("account_username"),
        "account_id": val.get("account_id"),
        "last_sync_at": val.get("last_sync_at"),
        "error": val.get("error"),
        "auto_poll_seconds": int(val.get("auto_poll_seconds", 60)),
    }


def _save_tg_raw(db: Session, updates: Dict[str, Any]) -> Dict[str, Any]:
    row = db.get(SystemState, TG_STATE_KEY)
    cur = dict(row.value) if row and row.value else {}
    cur.update(updates)
    if not row:
        row = SystemState(key=TG_STATE_KEY, value=cur)
        db.add(row)
    else:
        row.value = cur
    db.commit()
    return cur


async def send_login_code(db: Session, api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
    """Крок 1: Підключення особистого акаунта Telegram через Telethon — відправка коду підтвердження."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    clean_phone = phone.strip()
    clean_hash = api_hash.strip()
    client = TelegramClient(StringSession(), int(api_id), clean_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(clean_phone)
        temp_session = client.session.save()
        _save_tg_raw(
            db,
            {
                "status": "code_sent",
                "api_id": int(api_id),
                "api_hash": clean_hash,
                "phone": clean_phone,
                "phone_code_hash": sent.phone_code_hash,
                "temp_session": temp_session,
                "error": None,
            },
        )
        return get_telegram_state(db)
    except Exception as e:
        _save_tg_raw(db, {"status": "error", "error": str(e), "api_id": int(api_id), "phone": clean_phone})
        raise ValueError(f"Помилка Telegram API: {e}")
    finally:
        await client.disconnect()


async def verify_login_code(db: Session, code: str, password: Optional[str] = None) -> Dict[str, Any]:
    """Крок 2: Підтвердження SMS/Telegram-коду та (за потреби) хмарного пароля 2FA."""
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import StringSession

    row = db.get(SystemState, TG_STATE_KEY)
    raw = dict(row.value) if row and row.value else {}
    if not raw.get("temp_session") or not raw.get("api_id") or not raw.get("api_hash"):
        raise ValueError("Спочатку запросіть код підтвердження (Крок 1)")

    client = TelegramClient(StringSession(raw["temp_session"]), int(raw["api_id"]), str(raw["api_hash"]))
    await client.connect()
    try:
        try:
            me = await client.sign_in(
                phone=raw["phone"],
                code=code.strip(),
                phone_code_hash=raw.get("phone_code_hash"),
            )
        except SessionPasswordNeededError:
            if not password:
                raise ValueError("Цей акаунт захищено хмарним паролем (2FA). Введіть пароль у поле 2FA.")
            me = await client.sign_in(password=password)

        final_session = client.session.save()
        full_name = " ".join(filter(None, [getattr(me, "first_name", None), getattr(me, "last_name", None)])) or "Telegram User"
        _save_tg_raw(
            db,
            {
                "status": "connected",
                "session_string": final_session,
                "temp_session": None,
                "phone_code_hash": None,
                "account_name": full_name,
                "account_username": getattr(me, "username", None),
                "account_id": getattr(me, "id", None),
                "last_sync_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "error": None,
            },
        )
        return get_telegram_state(db)
    except Exception as e:
        raise ValueError(str(e))
    finally:
        await client.disconnect()


def disconnect_telegram(db: Session) -> Dict[str, Any]:
    _save_tg_raw(
        db,
        {
            "status": "disconnected",
            "session_string": None,
            "temp_session": None,
            "phone_code_hash": None,
            "account_name": None,
            "account_username": None,
            "account_id": None,
            "error": None,
        },
    )
    return get_telegram_state(db)


async def fetch_telegram_dialogs(db: Session, limit: int = 60) -> List[Dict[str, Any]]:
    """Отримує список груп/супергруп із підключеного Telegram-акаунта для додавання в моніторинг."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    row = db.get(SystemState, TG_STATE_KEY)
    raw = dict(row.value) if row and row.value else {}
    if raw.get("status") != "connected" or not raw.get("session_string"):
        raise ValueError("Telegram-акаунт не підключено. Авторизуйтеся у вкладці «Telegram & ШІ».")

    existing = {g.chat_id: g for g in db.scalars(select(TelegramGroup)).all()}
    client = TelegramClient(StringSession(raw["session_string"]), int(raw["api_id"]), str(raw["api_hash"]))
    await client.connect()
    try:
        dialogs = await client.get_dialogs(limit=limit)
        out: List[Dict[str, Any]] = []
        for d in dialogs:
            if not (d.is_group or d.is_channel):
                continue
            cid = int(d.id)
            entity = d.entity
            chat_type = "supergroup" if getattr(entity, "megagroup", False) else ("channel" if d.is_channel else "group")
            out.append(
                {
                    "chat_id": cid,
                    "title": d.name or f"Chat {cid}",
                    "username": getattr(entity, "username", None),
                    "chat_type": chat_type,
                    "unread_count": d.unread_count,
                    "already_added": cid in existing,
                    "is_monitored": existing[cid].is_monitored if cid in existing else False,
                }
            )
        return out
    finally:
        await client.disconnect()


async def sync_messages_from_telegram(db: Session, per_group_limit: int = 25) -> Dict[str, Any]:
    """Зчитує останні повідомлення з усіх активних груп у Telegram та пропускає їх через ШІ-парсер."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    row = db.get(SystemState, TG_STATE_KEY)
    raw = dict(row.value) if row and row.value else {}
    if raw.get("status") != "connected" or not raw.get("session_string"):
        raise ValueError("Telegram-акаунт ще не підключено")

    groups = db.scalars(select(TelegramGroup).where(TelegramGroup.is_monitored == True)).all()  # noqa: E712
    if not groups:
        return {"groups_checked": 0, "new_messages": 0, "tasks_created": 0}

    client = TelegramClient(StringSession(raw["session_string"]), int(raw["api_id"]), str(raw["api_hash"]))
    await client.connect()
    new_msgs = 0
    new_tasks = 0
    try:
        for g in groups:
            try:
                msgs = await client.get_messages(int(g.chat_id), limit=per_group_limit)
                for m in reversed(list(msgs)):
                    if not m or not getattr(m, "message", None):
                        continue
                    text_val = str(m.message).strip()
                    if not text_val:
                        continue
                    # Перевіряємо, чи вже оброблене це повідомлення
                    exists = db.scalar(
                        select(TelegramMessageLog.id).where(
                            TelegramMessageLog.chat_id == g.chat_id,
                            TelegramMessageLog.message_id == int(m.id),
                        )
                    )
                    if exists:
                        continue
                    sender = await m.get_sender()
                    s_uname = getattr(sender, "username", None) if sender else None
                    s_name = (
                        " ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)]))
                        if sender
                        else None
                    )
                    reply_obj = getattr(m, "reply_to", None)
                    reply_id = (
                        (getattr(reply_obj, "reply_to_top_id", None) or getattr(reply_obj, "reply_to_msg_id", None))
                        if reply_obj
                        else None
                    )
                    res = ingest_message(
                        db=db,
                        group=g,
                        raw_text=text_val,
                        sender_username=s_uname,
                        sender_name=s_name,
                        message_id=int(m.id),
                        reply_to_msg_id=reply_id,
                        sent_at=m.date if getattr(m, "date", None) else None,
                        allow_auto_task=False,
                    )
                    new_msgs += 1
                    if res.get("task_created"):
                        new_tasks += 1
            except Exception:
                continue

        _save_tg_raw(db, {"last_sync_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        return {"groups_checked": len(groups), "new_messages": new_msgs, "tasks_created": new_tasks}
    finally:
        await client.disconnect()


# ─────────────────────────────────────────────────────────────────────────────
# Єдиний конвеєр парсингу повідомлення -> Лог -> TeamTask
# ─────────────────────────────────────────────────────────────────────────────

def ingest_message(
    db: Session,
    group: TelegramGroup,
    raw_text: str,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    message_id: Optional[int] = None,
    reply_to_msg_id: Optional[int] = None,
    sent_at: Optional[dt.datetime] = None,
    force_create_task: bool = False,
    allow_auto_task: bool = False,
) -> Dict[str, Any]:
    """Приймає повідомлення з Telegram-групи, підтягує контекст треду, аналізує через ШІ та логує в потік."""
    now = sent_at or dt.datetime.now(dt.timezone.utc)
    if message_id is None:
        max_id = db.scalar(select(func.max(TelegramMessageLog.message_id)).where(TelegramMessageLog.chat_id == group.chat_id))
        message_id = (max_id or 1000) + 1

    # Збираємо контекст попередніх повідомлень у цій групі (або гілці reply)
    context_messages: List[str] = []
    reply_text: Optional[str] = None
    if reply_to_msg_id:
        replied = db.scalar(
            select(TelegramMessageLog).where(
                TelegramMessageLog.chat_id == group.chat_id,
                TelegramMessageLog.message_id == reply_to_msg_id,
            )
        )
        if replied:
            reply_text = replied.raw_text
            context_messages.append(f"[У відповідь на @{replied.sender_username or replied.sender_name or 'user'}]: {replied.raw_text}")

    recent_logs = db.scalars(
        select(TelegramMessageLog)
        .where(TelegramMessageLog.chat_id == group.chat_id)
        .order_by(TelegramMessageLog.id.desc())
        .limit(4)
    ).all()
    for rl in reversed(list(recent_logs)):
        line = f"@{rl.sender_username or rl.sender_name or 'user'}: {rl.raw_text}"
        if line not in context_messages:
            context_messages.append(line)

    is_sup = task_ai_parser.is_support_sender(sender_username, sender_name)
    ai_result = task_ai_parser.analyze_telegram_message(
        db=db,
        raw_text=raw_text,
        sender_username=sender_username,
        sender_name=sender_name,
        chat_title=group.title,
        context_messages=context_messages,
        reply_text=reply_text,
        group_team_id=group.team_id,
        group_client_id=group.client_id,
        topic_filter=group.topic_filter,
    )
    if is_sup and not force_create_task:
        ai_result["is_actionable"] = False
        ai_result["reasoning"] = "Повідомлення від саппорту нашої команди (частина діалогу)."

    cfg = task_ai_parser.get_ai_config(db)
    threshold = int(cfg.get("confidence_threshold", 60))
    should_create = force_create_task or (
        allow_auto_task
        and not is_sup
        and group.auto_create_tasks
        and ai_result.get("is_actionable", False)
        and int(ai_result.get("confidence", 0)) >= threshold
    )

    # Формуємо посилання на повідомлення в Telegram
    if group.username:
        msg_link = f"https://t.me/{group.username.lstrip('@')}/{message_id}"
    else:
        clean_cid = str(abs(group.chat_id))
        if clean_cid.startswith("100") and len(clean_cid) > 5:
            clean_cid = clean_cid[3:]
        msg_link = f"https://t.me/c/{clean_cid}/{message_id}"

    sender_display = (
        f"@{sender_username.lstrip('@')} ({sender_name})"
        if sender_username and sender_name
        else (f"@{sender_username.lstrip('@')}" if sender_username else (sender_name or "Учасник чату"))
    )

    created_task: Optional[TeamTask] = None
    if should_create:
        ents = ai_result.get("entities") or {}
        b_id = uuid.UUID(ents["buyer_id"]) if ents.get("buyer_id") else None
        t_id = uuid.UUID(ents["team_id"]) if ents.get("team_id") else group.team_id
        c_id = uuid.UUID(ents["client_id"]) if ents.get("client_id") else group.client_id

        created_task = TeamTask(
            title=ai_result.get("title") or raw_text[:100],
            description=ai_result.get("description"),
            raw_source_text=raw_text,
            status="inbox",
            priority=ai_result.get("priority", "medium"),
            category=ai_result.get("category", "general"),
            source="telegram",
            telegram_group_id=group.id,
            telegram_chat_title=group.title,
            telegram_sender=sender_display,
            telegram_message_link=msg_link,
            assignee_id=group.default_assignee_id,
            team_id=t_id,
            buyer_id=b_id,
            client_id=c_id,
            checklist=ai_result.get("checklist") or [],
            ai_context={
                "confidence": ai_result.get("confidence", 80),
                "engine": ai_result.get("engine", "domain_ai_v2"),
                "reasoning": ai_result.get("reasoning"),
                "suggested_reply": ai_result.get("suggested_reply"),
                "account_codes": ents.get("account_codes") or [],
                "card_last4": ents.get("card_last4") or [],
                "bm_id": ents.get("bm_id"),
                "qty": ents.get("qty"),
                "geo": ents.get("geo"),
                "limit": ents.get("limit"),
                "context_used": len(context_messages),
            },
            comments=[
                {
                    "id": str(uuid.uuid4())[:8],
                    "author": "ШІ-Диспетчер",
                    "text": f"Задачу автоматично виділено з групи «{group.title}» (впевненість ШІ: {ai_result.get('confidence', 85)}%). {ai_result.get('reasoning', '')}",
                    "created_at": now.isoformat(),
                }
            ],
        )
        db.add(created_task)
        db.flush()
        group.tasks_created = (group.tasks_created or 0) + 1

    log_entry = TelegramMessageLog(
        group_id=group.id,
        chat_id=group.chat_id,
        chat_title=group.title,
        message_id=message_id,
        reply_to_msg_id=reply_to_msg_id,
        sender_username=sender_username,
        sender_name=sender_name,
        raw_text=raw_text,
        message_link=msg_link,
        is_actionable=bool(ai_result.get("is_actionable", False)),
        ai_intent=ai_result.get("category", "noise"),
        ai_confidence=int(ai_result.get("confidence", 0)),
        ai_extracted=ai_result,
        task_id=created_task.id if created_task else None,
        sent_at=now,
    )
    db.add(log_entry)
    group.messages_parsed = (group.messages_parsed or 0) + 1
    group.last_message_at = now
    db.commit()
    if created_task:
        db.refresh(created_task)

    return {
        "log_id": log_entry.id,
        "task_created": created_task is not None,
        "task_id": str(created_task.id) if created_task else None,
        "task_code": created_task.code if created_task else None,
        "ai_result": ai_result,
    }


def convert_task_to_account_request(db: Session, task: TeamTask, actor: str) -> Request:
    """Перетворює задачу категорії `issue_accounts` на повноцінну Заявку на видачу акаунтів (Request) із підбором Ready-пулу."""
    from app.api.routes.requests import _propose

    client_id = task.client_id
    if not client_id:
        first_client = db.scalar(select(Client).order_by(Client.name))
        if first_client:
            client_id = first_client.id

    ctx = task.ai_context or {}
    qty = int(ctx.get("qty") or 1)
    geo = ctx.get("geo")
    limit = ctx.get("limit") if ctx.get("limit") and str(ctx.get("limit")).isdigit() else None

    req = Request(
        client_id=client_id,
        raw_text=task.raw_source_text or task.title,
        message_link=task.telegram_message_link,
        status=RequestStatus.new,
        parsed={
            "source": "telegram_task",
            "task_code": task.code,
            "intent": "issue",
            "qty": qty,
            "geo": geo,
            "limit": limit,
            "buyer_name": task.buyer.name if task.buyer else None,
            "created_by": actor,
        },
    )
    db.add(req)
    db.flush()
    _propose(db, req)
    task.linked_request_id = req.id
    if task.status == "inbox":
        task.status = "in_progress"
    db.commit()
    return req


# ─────────────────────────────────────────────────────────────────────────────
# Побудова контекстних діалогів (останні повідомлення по гілках/топіках)
# ─────────────────────────────────────────────────────────────────────────────

def build_conversation_threads(
    db: Session,
    groups: List[TelegramGroup],
    tasks_by_id: Dict[uuid.UUID, TeamTask],
) -> List[Dict[str, Any]]:
    """Групує останні повідомлення в кожній Telegram-групі за гілками діалогу (топіками або ланцюжками відповідей)
    та формує ШІ-резюме контексту, щоб менеджер бачив повну картину перед постановкою задачі."""
    groups_by_id = {g.id: g for g in groups}
    all_logs = db.scalars(
        select(TelegramMessageLog)
        .order_by(TelegramMessageLog.chat_id, TelegramMessageLog.message_id.asc())
    ).all()

    by_chat: Dict[int, List[TelegramMessageLog]] = {}
    for l in all_logs:
        by_chat.setdefault(l.chat_id, []).append(l)

    threads_out: List[Dict[str, Any]] = []

    for chat_id, chat_logs in by_chat.items():
        if not chat_logs:
            continue
        group_obj = groups_by_id.get(chat_logs[-1].group_id) if chat_logs[-1].group_id else None
        chat_title = group_obj.title if group_obj else (chat_logs[-1].chat_title or f"Chat {chat_id}")

        # Будуємо мапу message_id -> reply_to_msg_id, щоб знайти кореневий топік для кожної відповіді
        parent_map: Dict[int, Optional[int]] = {l.message_id: l.reply_to_msg_id for l in chat_logs}

        def find_root_topic(m_id: int, r_id: Optional[int]) -> int:
            if not r_id:
                return 0
            cur = r_id
            visited = {m_id}
            while cur in parent_map and parent_map[cur] is not None and parent_map[cur] not in visited:
                visited.add(cur)
                cur = parent_map[cur]  # піднімаємося до кореня гілки/топіка (напр. 1075 -> 1073 -> 4)
            return cur

        buckets: Dict[int, List[TelegramMessageLog]] = {}
        for l in chat_logs:
            root_id = find_root_topic(l.message_id, l.reply_to_msg_id)
            buckets.setdefault(root_id, []).append(l)

        # Якщо в групі є основні топіки та поодинокі повідомлення без reply (root_id=0),
        # або це звичайний чат без топіків — залишаємо останні 12 повідомлень на гілку
        for topic_id, t_logs in buckets.items():
            recent_slice = t_logs[-12:]
            # Якщо це одиночне технічне слово саппорту типу "готово" без клієнтських повідомлень — пропускаємо
            if len(recent_slice) == 1 and task_ai_parser.is_support_sender(recent_slice[0].sender_username, recent_slice[0].sender_name):
                if len((recent_slice[0].raw_text or "").strip()) < 15:
                    continue
            msg_dicts: List[Dict[str, Any]] = []
            linked_task: Optional[TeamTask] = None

            for rl in recent_slice:
                is_sup = task_ai_parser.is_support_sender(rl.sender_username, rl.sender_name)
                if rl.task_id and rl.task_id in tasks_by_id:
                    linked_task = tasks_by_id[rl.task_id]
                msg_dicts.append(
                    {
                        "id": rl.id,
                        "message_id": rl.message_id,
                        "reply_to_msg_id": rl.reply_to_msg_id,
                        "sender_username": rl.sender_username,
                        "sender_name": rl.sender_name,
                        "is_support": is_sup,
                        "raw_text": rl.raw_text,
                        "message_link": rl.message_link,
                        "sent_at": rl.sent_at.isoformat() if rl.sent_at else None,
                    }
                )

            summary = task_ai_parser.summarize_conversation_thread(
                db=db,
                chat_title=chat_title,
                topic_id=topic_id if topic_id > 0 else None,
                messages=msg_dicts,
                group_team_id=group_obj.team_id if group_obj else None,
                group_client_id=group_obj.client_id if group_obj else None,
            )

            last_dt = recent_slice[-1].sent_at
            threads_out.append(
                {
                    "thread_key": f"{chat_id}:{topic_id}",
                    "group_id": str(group_obj.id) if group_obj else None,
                    "chat_id": chat_id,
                    "chat_title": chat_title,
                    "topic_id": topic_id if topic_id > 0 else None,
                    "client_display": summary["client_display"],
                    "buyer_tag": summary["buyer_tag"],
                    "buyer_id": summary["buyer_id"],
                    "buyer_name": summary["buyer_name"],
                    "team_id": summary["team_id"],
                    "client_id": summary["client_id"],
                    "resolution_state": summary["resolution_state"],
                    "category": summary["category"],
                    "priority": summary["priority"],
                    "suggested_title": summary["suggested_title"],
                    "context_summary": summary["context_summary"],
                    "ad_account_ids": summary["ad_account_ids"],
                    "entities": summary["entities"],
                    "checklist": summary["checklist"],
                    "messages": msg_dicts,
                    "messages_count": len(msg_dicts),
                    "linked_task_id": str(linked_task.id) if linked_task else None,
                    "linked_task_code": linked_task.code if linked_task else None,
                    "linked_task_status": linked_task.status if linked_task else None,
                    "last_message_at": last_dt.isoformat() if last_dt else None,
                }
            )

    # Сортуємо діалоги: спочатку ті, що потребують дії (needs_action), далі за часом останнього повідомлення
    state_order = {"needs_action": 0, "waiting_client": 1, "resolved_in_chat": 2}
    threads_out.sort(
        key=lambda x: (
            state_order.get(x["resolution_state"], 9),
            -(dt.datetime.fromisoformat(x["last_message_at"]).timestamp() if x.get("last_message_at") else 0),
        )
    )
    return threads_out


def create_task_from_thread(
    db: Session,
    chat_id: int,
    topic_id: Optional[int],
    title: Optional[str],
    description: Optional[str],
    category: Optional[str],
    priority: Optional[str],
    assignee_id: Optional[uuid.UUID],
    buyer_id: Optional[uuid.UUID],
    team_id: Optional[uuid.UUID],
    creator: User,
) -> TeamTask:
    """Створює повноцінну задачу з контексту всього діалогу (включаючи останні повідомлення переписки)."""
    groups = db.scalars(select(TelegramGroup)).all()
    tasks_by_id = {t.id: t for t in db.scalars(select(TeamTask)).all()}
    threads = build_conversation_threads(db, groups, tasks_by_id)
    target_key = f"{chat_id}:{topic_id or 0}"
    thread = next((th for th in threads if th["thread_key"] == target_key), None)
    if not thread:
        raise ValueError("Гілку діалогу не знайдено")

    group_obj = db.get(TelegramGroup, uuid.UUID(thread["group_id"])) if thread.get("group_id") else None
    msgs = thread["messages"]
    ents = thread.get("entities") or {}

    final_title = (title or "").strip() or thread["suggested_title"]
    final_desc = (description or "").strip() or thread["context_summary"]
    final_cat = category or thread["category"]
    final_prio = priority or thread["priority"]
    final_buyer_id = buyer_id or (uuid.UUID(thread["buyer_id"]) if thread.get("buyer_id") else None)
    final_team_id = team_id or (uuid.UUID(thread["team_id"]) if thread.get("team_id") else (group_obj.team_id if group_obj else None))
    final_client_id = uuid.UUID(thread["client_id"]) if thread.get("client_id") else (group_obj.client_id if group_obj else None)
    final_assignee = assignee_id or (group_obj.default_assignee_id if group_obj else creator.id)

    # Формуємо читабельний транскрипт останніх повідомлень діалогу для швидкого перегляду
    transcript_lines = []
    for m in msgs[-8:]:
        role_tag = "🛠 Саппорт" if m.get("is_support") else f"👤 @{m.get('sender_username') or m.get('sender_name') or 'Клієнт'}"
        short_txt = (m.get("raw_text") or "").strip()
        if len(short_txt) > 220:
            short_txt = short_txt[:220] + "…"
        transcript_lines.append(f"{role_tag}: {short_txt}")

    last_msg_link = msgs[-1].get("message_link") if msgs else None

    task = TeamTask(
        title=final_title,
        description=final_desc,
        raw_source_text="\n".join(transcript_lines),
        status="todo",
        priority=final_prio,
        category=final_cat,
        source="telegram",
        telegram_group_id=group_obj.id if group_obj else None,
        telegram_chat_title=thread["chat_title"] + (f" · Гілка #{topic_id}" if topic_id else ""),
        telegram_sender=thread["client_display"],
        telegram_message_link=last_msg_link,
        assignee_id=final_assignee,
        creator_id=creator.id,
        team_id=final_team_id,
        buyer_id=final_buyer_id,
        client_id=final_client_id,
        checklist=thread.get("checklist") or [],
        ai_context={
            "confidence": 92,
            "engine": "thread_context_v2",
            "reasoning": thread["context_summary"],
            "thread_messages": msgs[-10:],
            "ad_account_ids": thread.get("ad_account_ids") or [],
            "account_codes": ents.get("account_codes") or [],
            "card_last4": ents.get("card_last4") or [],
            "bm_id": ents.get("bm_id"),
            "qty": ents.get("qty"),
            "geo": ents.get("geo"),
            "limit": ents.get("limit"),
            "context_used": len(msgs),
        },
        comments=[
            {
                "id": str(uuid.uuid4())[:8],
                "author": creator.name,
                "text": f"Задачу поставлено на основі контексту діалогу ({len(msgs)} повідомлень) у групі «{thread['chat_title']}».",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        ],
    )
    db.add(task)
    db.flush()

    # Прив'язуємо повідомлення цієї гілки до створеної задачі
    msg_ids = [m["id"] for m in msgs]
    if msg_ids:
        for l in db.scalars(select(TelegramMessageLog).where(TelegramMessageLog.id.in_(msg_ids))).all():
            l.task_id = task.id
            l.is_actionable = True

    if group_obj:
        group_obj.tasks_created = (group_obj.tasks_created or 0) + 1

    db.commit()
    db.refresh(task)
    return task


# ─────────────────────────────────────────────────────────────────────────────
# Початкове наповнення структури (реальні команди + демо-потік Telegram)
# ─────────────────────────────────────────────────────────────────────────────

def ensure_initial_structure(db: Session) -> None:
    """Якщо таблиця груп порожня (і демо ще не ініціалізувалося раніше) — створює стартові робочі групи."""
    seeded_flag = db.get(SystemState, "tasks_demo_seeded")
    tg_state = db.get(SystemState, TG_STATE_KEY)
    if seeded_flag or (tg_state and tg_state.value and tg_state.value.get("status") == "connected"):
        return

    existing_groups = db.scalar(select(func.count()).select_from(TelegramGroup)) or 0
    if existing_groups > 0:
        db.add(SystemState(key="tasks_demo_seeded", value={"seeded": True}))
        db.commit()
        return

    db.add(SystemState(key="tasks_demo_seeded", value={"seeded": True}))

    teams = db.scalars(select(Team).order_by(Team.name)).all()
    team_298 = next((t for t in teams if "298" in t.name), teams[0] if teams else None)
    team_4445 = next((t for t in teams if "4445" in t.name), teams[1] if len(teams) > 1 else team_298)
    first_user = db.scalar(select(User).order_by(User.created_at))

    g1 = TelegramGroup(
        chat_id=-1002198451298,
        title="CPA Samurai Team 298 | Баєри & Картки",
        chat_type="supergroup",
        is_monitored=True,
        auto_create_tasks=True,
        team_id=team_298.id if team_298 else None,
        default_assignee_id=first_user.id if first_user else None,
        topic_filter="Звертати особливу увагу на деклайни карток FBM, видачу акаунтів та звірку спенду по WebLumi, WebDD, WebTxmmy.",
    )
    g2 = TelegramGroup(
        chat_id=-1002198454445,
        title="CPA Samurai Team 4445 | Операційний чат",
        chat_type="supergroup",
        is_monitored=True,
        auto_create_tasks=True,
        team_id=team_4445.id if team_4445 else None,
        default_assignee_id=first_user.id if first_user else None,
        topic_filter="Запити на розшарку БМ, ліміти та нові кабінети для баєрів команди.",
    )
    g3 = TelegramGroup(
        chat_id=-1002198459900,
        title="Skull Partners | Фарм, AdsPower & Техвідділ",
        chat_type="supergroup",
        is_monitored=True,
        auto_create_tasks=True,
        default_assignee_id=first_user.id if first_user else None,
        topic_filter="Внутрішній чат фармерів: чеки, селфі, проксі, пачки від постачальників, інтеграція AdsPower.",
    )
    db.add_all([g1, g2, g3])
    db.commit()

    now = dt.datetime.now(dt.timezone.utc)
    sample_stream = [
        (
            g1,
            "WebLumi",
            "Igor WebLumi",
            "Привіт усім! Запускаю нову зв'язку сьогодні.",
            101,
            None,
            now - dt.timedelta(hours=3, minutes=20),
        ),
        (
            g1,
            "WebLumi",
            "Igor WebLumi",
            "Хлопці, терміново! По WebLumi карта ••9443 почала бити деклайн на $20.59, трафік стоїть! Перевірте баланс субакаунта або підв'яжіть нову картку плз 🚨",
            102,
            101,
            now - dt.timedelta(hours=3, minutes=15),
        ),
        (
            g1,
            "WebTxmmy",
            "Tommy Media",
            "Дайте 5 аків США з лімітом 250$ під запуск на вечір, і одразу розшарте на БМ 849201948271625",
            103,
            None,
            now - dt.timedelta(hours=2, minutes=30),
        ),
        (
            g1,
            "WebDD",
            "Denys WebDD",
            "Ок, дякую 👍",
            104,
            None,
            now - dt.timedelta(hours=2, minutes=10),
        ),
        (
            g2,
            "WebDD",
            "Denys WebDD",
            "Потрібно розшарити піксель і БМ 391048572619384 на 3 кабінети WebDD, бо зараз не бачить ліди в кабінеті",
            201,
            None,
            now - dt.timedelta(hours=1, minutes=40),
        ),
        (
            g3,
            "farm_lead",
            "Максим Фарм",
            "Акаунт FB-0001 вилетів на чекпоінт (селфі + код 2FA), потрібно відкрити в AdsPower і пройти перевірку до кінця дня",
            301,
            None,
            now - dt.timedelta(minutes=50),
        ),
        (
            g3,
            "ops_manager",
            "Олексій Ops",
            "Потрібно докупити пачку 30 аків Польща (PL) у постачальника на завтра під залив команди",
            302,
            None,
            now - dt.timedelta(minutes=25),
        ),
    ]

    for grp, uname, sname, txt, mid, r_id, ts_val in sample_stream:
        ingest_message(
            db=db,
            group=grp,
            raw_text=txt,
            sender_username=uname,
            sender_name=sname,
            message_id=mid,
            reply_to_msg_id=r_id,
            sent_at=ts_val,
        )

    # Переведемо декілька стартових задач у різні колонки Канбану для наочності
    tasks = db.scalars(select(TeamTask).order_by(TeamTask.created_at.asc())).all()
    if len(tasks) >= 3:
        tasks[0].status = "in_progress"
        tasks[1].status = "todo"
        db.commit()
