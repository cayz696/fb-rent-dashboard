"""Імпорт замовлення зі стоку → реєстрація акаунтів + готовий файл для AdsPower.
Замінює ручний крок з ChatGPT. Секрети (паролі/cookies/2FA) не зберігаються (ТЗ §4)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, can_write
from app.core.db import get_db
from app.integrations.order_parser import OrderParseError, ParsedAccount, account_remark, parse_order, to_adspower_file
from app.models import Account, Stage, User
from app.schemas.api import ImportPreview, ImportPreviewRow, ImportResult
from app.services import accounts as acc_svc
from app.services import bridge as bridge_svc

router = APIRouter(prefix="/api/import", tags=["import"])
MAX_BYTES = 5 * 1024 * 1024


async def _read(file: UploadFile) -> str:
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Файл завеликий (>5 МБ)")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Очікується текстовий файл UTF-8")


def _parse(text: str) -> list[ParsedAccount]:
    try:
        return parse_order(text)
    except OrderParseError as e:
        raise HTTPException(422, str(e))


def _existing_ids(db: Session, ids: list[str]) -> set[str]:
    ids = [i for i in ids if i]
    if not ids:
        return set()
    return set(db.scalars(select(Account.fb_user_id).where(Account.fb_user_id.in_(ids))))


@router.post("/order/preview", response_model=ImportPreview)
async def preview(file: UploadFile, db: Session = Depends(get_db), _: User = Depends(can_write)):
    accounts = _parse(await _read(file))
    dupes = _existing_ids(db, [a.fb_user_id for a in accounts])
    rows = [
        ImportPreviewRow(name=a.name, fb_user_id=a.fb_user_id, fb_login=a.fb_login, country=a.country,
                         twofa_ok=bool(a.twofa_secret), warnings=a.warnings, duplicate=a.fb_user_id in dupes)
        for a in accounts
    ]
    new = sum(1 for r in rows if not r.duplicate)
    return ImportPreview(total=len(rows), new=new, duplicates=len(rows) - new, rows=rows)


def _profile_payload(a: ParsedAccount) -> dict:
    """Секретний payload для bridge (cookies/пароль/2FA/нотатки) — тільки по WS, у БД не потрапляє.
    remark містить логін/пароль/пошту — тому теж лише тут, не в args."""
    return {
        "username": a.fb_login, "password": a.fb_password, "fakey": a.twofa_secret,
        "cookie": a.cookies_raw, "ua": a.user_agent, "remark": account_remark(a), "country": a.country,
    }


@router.post("/order", response_model=ImportResult)
async def import_order(
    file: UploadFile,
    supplier_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    via: str = "file",  # "file" — віддати файл для ручного імпорту; "bridge" — автостворення профілів
    group: str | None = None,  # назва групи AdsPower (напр. "тест дашборд"); None → Ungrouped
    proxy_type: str | None = None,  # http|https|socks5 — спільний проксі для партії (режим bridge)
    proxy_host: str | None = None,
    proxy_port: str | None = None,
    proxy_user: str | None = None,
    proxy_password: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(can_write),
):
    if via not in ("file", "bridge"):
        raise HTTPException(422, "via має бути file або bridge")
    accounts = _parse(await _read(file))
    if via == "bridge" and not bridge_svc.status(db)["online"]:
        raise HTTPException(409, "Bridge офлайн — скористайтесь режимом «файл» або дочекайтесь підключення мосту")
    proxy = None
    if via == "bridge" and proxy_host:
        proxy = {"type": proxy_type or "http", "host": proxy_host, "port": proxy_port,
                 "user": proxy_user, "password": proxy_password}

    dupes = _existing_ids(db, [a.fb_user_id for a in accounts])
    created, codes, queued = 0, [], 0
    for a in (x for x in accounts if x.fb_user_id not in dupes):
        acc = acc_svc.create_account(db, actor_of(user), supplier_id=supplier_id, batch_id=batch_id, **a.db_fields())
        acc_svc.add_event(db, acc.id, "imported_from_order", actor_of(user),
                          payload={"fb_user_id": a.fb_user_id, "warnings": a.warnings})
        if via == "bridge":
            payload = _profile_payload(a)
            if proxy:
                payload["proxy"] = proxy  # проксі (з паролем) — секретним шляхом через WS, не в БД
            bridge_svc.enqueue_profile_full(db, acc.id, acc.code, a.fb_user_id, payload, actor_of(user), group=group)
            queued += 1
        created += 1
        codes.append(acc.code)
    db.commit()
    # Файл AdsPower повертаємо завжди (як fallback): у режимі bridge — на випадок, якщо частина профілів не створиться.
    # Секрети лише в цій відповіді/у пам'яті, на сервері не зберігаються (ТЗ §4).
    return ImportResult(
        created=created, skipped_duplicates=len(accounts) - created, codes=codes, queued_to_bridge=queued,
        adspower_file=to_adspower_file(accounts),
        filename=f"AdsPower_{file.filename.rsplit('.', 1)[0]}_no_proxy.txt" if file.filename else "AdsPower_import_no_proxy.txt",
    )
