"""Черга команд для bridge (AdsPower). Сервер ніколи не звертається до макбука напряму:
bridge підключається сам (WebSocket), забирає `pending` команди й повертає результат."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, BridgeCommand, CommandStatus, Stage, SystemState
from app.services import accounts as acc_svc
from app.services.state_machine import TransitionError

# Білий список команд (ТЗ §6.2) і обов'язкові аргументи
WHITELIST: dict[str, tuple[str, ...]] = {
    "list_profiles": (),
    "create_profile": ("account_id", "name"),
    "update_profile_group": ("profile_id", "group"),
    "open_profile": ("profile_id",),
    "close_profile": ("profile_id",),
    "find_profile": ("name",),
}
ONLINE_WINDOW = timedelta(seconds=60)
OFFLINE_SIGNAL = timedelta(minutes=15)
KEY = "bridge_last_seen"

# Секретні payload'и для create_profile_full (cookies, паролі, 2FA) — ТІЛЬКИ в пам'яті процесу (ТЗ §4).
# Не пишуться в БД. Віддаються bridge через WebSocket у момент claim і одразу видаляються.
# Якщо сервер перезапуститься до доставки — payload втрачається, команда падає (оператор повторює імпорт).
_pending_payloads: dict[str, dict] = {}


class BridgeError(Exception):
    pass


def touch(db: Session) -> None:
    now = datetime.now(timezone.utc)
    st = db.get(SystemState, KEY)
    if st:
        st.value = {"at": now.isoformat()}
    else:
        db.add(SystemState(key=KEY, value={"at": now.isoformat()}))
    db.commit()


def last_seen(db: Session) -> datetime | None:
    st = db.get(SystemState, KEY)
    return datetime.fromisoformat(st.value["at"]) if st and st.value.get("at") else None


def pending_count(db: Session) -> int:
    return len(db.scalars(select(BridgeCommand.id).where(BridgeCommand.status.in_((CommandStatus.pending, CommandStatus.sent)))).all())


def status(db: Session) -> dict:
    seen = last_seen(db)
    now = datetime.now(timezone.utc)
    return {"online": bool(seen and now - seen <= ONLINE_WINDOW), "last_seen": seen, "pending": pending_count(db)}


def enqueue(db: Session, command: str, args: dict, created_by: str) -> BridgeCommand:
    if command not in WHITELIST:
        raise BridgeError(f"Команда {command} не дозволена")
    missing = [a for a in WHITELIST[command] if not args.get(a)]
    if missing:
        raise BridgeError(f"Не вистачає аргументів: {', '.join(missing)}")
    cmd = BridgeCommand(command=command, args=args, created_by=created_by, status=CommandStatus.pending)
    db.add(cmd)
    db.flush()
    return cmd


def enqueue_profile_full(db: Session, account_id, name: str, fb_user_id: str, payload: dict, created_by: str,
                         group: str | None = None) -> BridgeCommand:
    """Створення профілю AdsPower з cookies/паролем/2FA. У БД — лише несекретні args (+group для розкладки);
    секретний `payload` (паролі, cookies, 2FA, нотатки) осідає в пам'яті (_pending_payloads) і не персиститься (ТЗ §4)."""
    args = {"account_id": str(account_id), "name": name, "fb_user_id": fb_user_id}
    if group:
        args["group"] = group
    cmd = BridgeCommand(
        command="create_profile_full", args=args,
        created_by=created_by, status=CommandStatus.pending,
    )
    db.add(cmd)
    db.flush()
    _pending_payloads[str(cmd.id)] = payload
    return cmd


def requeue_sent(db: Session) -> None:
    """Після перепідключення команди без відповіді повертаються в чергу (виконання ідемпотентне на стороні bridge).
    create_profile_full доставляється повторно, лише якщо секрет ще в пам'яті; інакше (перезапуск сервера) — помилка."""
    for c in db.scalars(select(BridgeCommand).where(BridgeCommand.status == CommandStatus.sent)):
        if c.command == "create_profile_full" and str(c.id) not in _pending_payloads:
            c.status = CommandStatus.error
            c.result = {"error": "Секрет профілю недоступний (перезапуск сервера) — повторіть імпорт"}
            _fail_event(db, c, c.result["error"])
        else:
            c.status = CommandStatus.pending
    db.commit()


def claim_pending(db: Session) -> list[dict]:
    cmds = db.scalars(select(BridgeCommand).where(BridgeCommand.status == CommandStatus.pending).order_by(BridgeCommand.created_at)).all()
    out = []
    for c in cmds:
        msg = {"type": "command", "id": str(c.id), "command": c.command, "args": c.args}
        if c.command == "create_profile_full":
            payload = _pending_payloads.get(str(c.id))  # не видаляємо: тримаємо до фінального результату (для повторної доставки)
            if payload is None:  # сервер перезапустився — секрету немає
                c.status = CommandStatus.error
                c.result = {"error": "Секрет профілю недоступний (перезапуск сервера) — повторіть імпорт"}
                _fail_event(db, c, c.result["error"])
                continue
            msg["profile"] = payload  # секрети йдуть по WS, не в БД
        c.status = CommandStatus.sent
        out.append(msg)
    db.commit()
    return out


def _fail_event(db: Session, cmd: BridgeCommand, error: str) -> None:
    cmd.done_at = datetime.now(timezone.utc)
    if cmd.args.get("account_id"):
        acc = db.get(Account, uuid.UUID(cmd.args["account_id"]))
        if acc:
            acc_svc.add_event(db, acc.id, "bridge_error", "bridge", payload={"command": cmd.command, "error": error})


def complete(db: Session, cmd_id: uuid.UUID, ok: bool, result: dict | None, error: str | None) -> None:
    cmd = db.get(BridgeCommand, cmd_id)
    if not cmd or cmd.status in (CommandStatus.ok, CommandStatus.error):
        return
    cmd.status = CommandStatus.ok if ok else CommandStatus.error
    cmd.result = result if ok else {"error": error or "невідома помилка"}
    cmd.done_at = datetime.now(timezone.utc)
    _pending_payloads.pop(str(cmd.id), None)  # секрет більше не потрібен
    if ok and cmd.command in ("create_profile", "create_profile_full"):
        _apply_created_profile(db, cmd, result or {})
    if ok and cmd.command == "list_profiles":
        _save_profiles_snapshot(db, result or {})
    if not ok and cmd.args.get("account_id"):
        acc = db.get(Account, uuid.UUID(cmd.args["account_id"]))
        if acc:
            acc_svc.add_event(db, acc.id, "bridge_error", "bridge", payload={"command": cmd.command, "error": error})
    db.commit()


def _apply_created_profile(db: Session, cmd: BridgeCommand, result: dict) -> None:
    """create_profile → пишемо adspower_profile_id в акаунт і подію in_adspower (ТЗ §6.2)."""
    profile_id = result.get("profile_id")
    acc = db.get(Account, uuid.UUID(cmd.args["account_id"])) if cmd.args.get("account_id") else None
    if not acc or not profile_id:
        return
    acc_svc.update_account(db, acc, "bridge", {"adspower_profile_id": str(profile_id)})
    if acc.stage == Stage.purchased:
        try:
            acc_svc.transition(db, acc, Stage.in_adspower, "bridge", comment="Профіль створено в AdsPower")
        except TransitionError:
            pass


SNAPSHOT_KEY = "adspower_snapshot"


def _save_profiles_snapshot(db: Session, result: dict) -> None:
    """Зберігаємо знімок профілів AdsPower (несекретні поля) для дзеркала в дашборді."""
    profiles = result.get("profiles") or []
    st = db.get(SystemState, SNAPSHOT_KEY)
    payload = {"at": datetime.now(timezone.utc).isoformat(), "count": len(profiles), "profiles": profiles}
    if st:
        st.value = payload
    else:
        db.add(SystemState(key=SNAPSHOT_KEY, value=payload))


def profiles_snapshot(db: Session) -> dict | None:
    st = db.get(SystemState, SNAPSHOT_KEY)
    return st.value if st else None


def enqueue_list_profiles(db: Session, created_by: str) -> BridgeCommand:
    cmd = BridgeCommand(command="list_profiles", args={}, created_by=created_by, status=CommandStatus.pending)
    db.add(cmd)
    db.flush()
    return cmd


def offline_too_long(db: Session) -> timedelta | None:
    """Скільки bridge мовчить, якщо довше за 15 хв (і він хоч раз підключався)."""
    seen = last_seen(db)
    if not seen:
        return None
    gap = datetime.now(timezone.utc) - seen
    return gap if gap > OFFLINE_SIGNAL else None
