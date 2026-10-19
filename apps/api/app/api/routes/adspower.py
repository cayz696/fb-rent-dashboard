from __future__ import annotations
"""Дзеркало AdsPower у дашборді: тягнемо список профілів через bridge (тільки читання),
зіставляємо з нашими акаунтами. Секрети з AdsPower не зберігаємо (ТЗ §4)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_of, admin_only, can_write, current_user
from app.core.db import get_db
from app.models import Account, Stage, User
from app.services import accounts as acc_svc
from app.services import bridge as bridge_svc


def stage_for_group(group_name: str | None) -> Stage:
    """Мапінг групи AdsPower → етап (ТЗ v2). Неоднозначні/робочі групи → in_adspower (профіль існує)."""
    g = (group_name or "").lower()
    if "прогрев" in g or "прогрів" in g:
        return Stage.warmup
    if "готов" in g:
        return Stage.ready
    if "продан" in g:
        return Stage.sold
    return Stage.in_adspower

router = APIRouter(prefix="/api/adspower", tags=["adspower"])


class SyncProfile(BaseModel):
    profile_id: str | None
    serial: str | None = None
    name: str | None
    group_name: str | None
    username: str | None
    country: str | None = None
    fb_user_id: str | None
    linked_code: str | None = None     # код нашого акаунта, якщо зіставлено
    linked_stage: str | None = None


class SyncView(BaseModel):
    last_sync: datetime | None
    total: int
    linked: int
    unlinked: int
    by_group: dict[str, int]
    profiles: list[SyncProfile]
    pending: bool                      # команда синхронізації ще в черзі/виконується


@router.post("/refresh", status_code=202)
def refresh(db: Session = Depends(get_db), user: User = Depends(can_write)):
    if not bridge_svc.status(db)["online"]:
        raise HTTPException(409, "Bridge офлайн — синхронізація неможлива")
    bridge_svc.enqueue_list_profiles(db, actor_of(user))
    db.commit()
    return {"queued": True}


def _pending_sync(db: Session) -> bool:
    from app.models import BridgeCommand, CommandStatus
    return bool(db.scalar(
        select(BridgeCommand.id).where(
            BridgeCommand.command == "list_profiles",
            BridgeCommand.status.in_((CommandStatus.pending, CommandStatus.sent)),
        ).limit(1)
    ))


@router.get("/profiles", response_model=SyncView)
def profiles(db: Session = Depends(get_db), _: User = Depends(current_user)):
    snap = bridge_svc.profiles_snapshot(db)
    rows = (snap or {}).get("profiles", [])
    # індекси наших акаунтів для зіставлення
    accounts = db.scalars(select(Account)).all()
    by_profile = {a.adspower_profile_id: a for a in accounts if a.adspower_profile_id}
    by_fb = {a.fb_user_id: a for a in accounts if a.fb_user_id}

    out: list[SyncProfile] = []
    by_group: dict[str, int] = {}
    linked = 0
    for r in rows:
        acc = by_profile.get(r.get("profile_id")) or by_fb.get(r.get("fb_user_id"))
        if acc:
            linked += 1
        g = r.get("group_name") or "— без групи —"
        by_group[g] = by_group.get(g, 0) + 1
        out.append(SyncProfile(
            profile_id=r.get("profile_id"), serial=r.get("serial"), name=r.get("name"),
            group_name=r.get("group_name"), username=r.get("username"), country=r.get("country"),
            fb_user_id=r.get("fb_user_id"),
            linked_code=acc.code if acc else None, linked_stage=acc.stage.value if acc else None,
        ))
    out.sort(key=lambda p: (p.group_name or "", p.name or ""))
    last = None
    if snap and snap.get("at"):
        last = datetime.fromisoformat(snap["at"])
    return SyncView(
        last_sync=last, total=len(out), linked=linked, unlinked=len(out) - linked,
        by_group=dict(sorted(by_group.items(), key=lambda x: -x[1])),
        profiles=out, pending=_pending_sync(db),
    )


class ImportResult(BaseModel):
    created: int
    updated_group: int
    skipped: int
    by_stage: dict[str, int]


@router.post("/import-unlinked", response_model=ImportResult)
def import_unlinked(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Створює акаунти дашборда для профілів AdsPower, що ще не зіставлені.
    Етап — з групи (мапінг); реальна група зберігається в adspower_group. Повторюваний (дублі пропускає)."""
    snap = bridge_svc.profiles_snapshot(db)
    if not snap:
        raise HTTPException(409, "Спершу синхронізуйте профілі (кнопка «Синхронізувати»)")
    rows = snap.get("profiles", [])
    accounts = db.scalars(select(Account)).all()
    by_profile = {a.adspower_profile_id: a for a in accounts if a.adspower_profile_id}
    by_fb = {a.fb_user_id: a for a in accounts if a.fb_user_id}

    created = updated = skipped = 0
    by_stage: dict[str, int] = {}
    for r in rows:
        pid, fb = r.get("profile_id"), r.get("fb_user_id")
        existing = by_profile.get(pid) or (by_fb.get(fb) if fb else None)
        if existing:
            # освіжаємо дзеркальні поля (група/профіль), етап не чіпаємо
            changes = {}
            if not existing.adspower_profile_id and pid:
                changes["adspower_profile_id"] = pid
            if existing.adspower_group != r.get("group_name"):
                changes["adspower_group"] = r.get("group_name")
            if changes:
                acc_svc.update_account(db, existing, actor_of(user), changes)
                updated += 1
            else:
                skipped += 1
            continue
        stage = stage_for_group(r.get("group_name"))
        acc = acc_svc.create_account(
            db, actor_of(user), fb_user_id=fb, fb_login=r.get("username"), country=(r.get("country") or None),
            adspower_profile_id=pid, adspower_group=r.get("group_name"),
        )
        acc.stage = stage  # історичний імпорт: ставимо етап напряму (не через transition)
        acc_svc.add_event(db, acc.id, "imported_from_adspower", actor_of(user),
                          to_stage=stage, payload={"group": r.get("group_name"), "profile_id": pid})
        created += 1
        by_stage[stage.value] = by_stage.get(stage.value, 0) + 1
    db.commit()
    return ImportResult(created=created, updated_group=updated, skipped=skipped, by_stage=by_stage)
