from __future__ import annotations
"""Дані спенду з Clover: прийом, зіставлення з акаунтами, вибірки для UI."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clover_mapper import extract_records, map_record, normalize_ad_account_id
from app.models import Account, SpendSnapshot
from app.services import accounts as acc_svc

STALE_HOURS = 2


def today_kyiv() -> date:
    return datetime.now(ZoneInfo(settings.app_tz)).date()


def norm_col():
    """SQL-вираз для нормалізованого ad_account_id акаунта (без 'act_', нижній регістр)."""
    return func.regexp_replace(func.lower(func.trim(Account.ad_account_id)), r"^act[_\-\s]?", "")


def find_account(db: Session, ad_id: str) -> Account | None:
    return db.scalar(select(Account).where(Account.ad_account_id.is_not(None), norm_col() == ad_id))


def ingest(db: Session, payload: Any) -> dict:
    """Зберігає кожен запис як снепшот, зіставляє з акаунтом за ad_account_id. Незіставлені лишаються з account_id=NULL."""
    records = extract_records(payload)
    now = datetime.now(timezone.utc)
    stored = matched = unmatched = skipped = 0
    for rec in records:
        m = map_record(rec)
        if not m.ad_account_id:
            skipped += 1
            continue
        acc = find_account(db, m.ad_account_id)
        snap_date = m.date or now.astimezone(ZoneInfo(settings.app_tz)).date()
        db.add(SpendSnapshot(
            ad_account_id=m.ad_account_id, account_id=acc.id if acc else None, date=snap_date,
            spend_today=m.spend_today, spend_total=m.spend_total, spend_limit=m.spend_limit,
            ads_active=m.ads_active, ads_issues=m.ads_issues, status_raw=m.status_raw, raw=m.raw,
        ))
        stored += 1
        if acc:
            matched += 1
            changes = {}
            if m.spend_limit is not None and acc.spend_limit != m.spend_limit:
                changes["spend_limit"] = m.spend_limit
            if m.timezone and acc.timezone != m.timezone:
                changes["timezone"] = m.timezone
            if changes:
                acc_svc.update_account(db, acc, "clover", changes)
        else:
            unmatched += 1
    if not records:  # невідома форма: не втрачаємо дані
        db.add(SpendSnapshot(ad_account_id="?", date=now.date(), raw={"payload": payload} if not isinstance(payload, dict) else payload))
    return {"records": len(records), "stored": stored, "matched": matched, "unmatched": unmatched, "skipped": skipped}


def backfill(db: Session, acc: Account) -> int:
    """Прив'язує раніше незіставлені снепшоти до акаунта після зміни його ad_account_id."""
    ad = normalize_ad_account_id(acc.ad_account_id)
    if not ad:
        return 0
    rows = db.scalars(select(SpendSnapshot).where(SpendSnapshot.account_id.is_(None), SpendSnapshot.ad_account_id == ad)).all()
    for r in rows:
        r.account_id = acc.id
    return len(rows)


def latest_by_ad(db: Session, ad_ids: list[str] | None = None) -> dict[str, SpendSnapshot]:
    stmt = select(SpendSnapshot).ext(distinct_on(SpendSnapshot.ad_account_id)).where(SpendSnapshot.ad_account_id != "?").order_by(
        SpendSnapshot.ad_account_id, SpendSnapshot.received_at.desc(), SpendSnapshot.id.desc()
    )
    if ad_ids is not None:
        if not ad_ids:
            return {}
        stmt = stmt.where(SpendSnapshot.ad_account_id.in_(ad_ids))
    return {s.ad_account_id: s for s in db.scalars(stmt)}


def snapshot_view(accounts: list[Account], db: Session) -> dict:
    """{account.id: {spend_today, spend_total, ads_active, ads_issues}} для списків."""
    ids = {a.id: normalize_ad_account_id(a.ad_account_id) for a in accounts if a.ad_account_id}
    snaps = latest_by_ad(db, list({v for v in ids.values() if v}))
    today = today_kyiv()
    out = {}
    for aid, ad in ids.items():
        s = snaps.get(ad) if ad else None
        if s:
            out[aid] = {
                "spend_today": s.spend_today if s.date == today else None,
                "spend_total": s.spend_total, "ads_active": s.ads_active, "ads_issues": s.ads_issues,
            }
    return out


def daily_series(db: Session, ad_id: str, days: int) -> list[dict]:
    """Спенд по днях: останній снепшот кожної дати; пропущені дні = null."""
    today = today_kyiv()
    start = today - timedelta(days=days - 1)
    rows = db.scalars(
        select(SpendSnapshot).ext(distinct_on(SpendSnapshot.date)).where(SpendSnapshot.ad_account_id == ad_id, SpendSnapshot.date >= start)
        .order_by(SpendSnapshot.date, SpendSnapshot.received_at.desc(), SpendSnapshot.id.desc())
    ).all()
    by_date = {r.date: r.spend_today for r in rows}
    return [{"date": (start + timedelta(days=i)).isoformat(), "spend": by_date.get(start + timedelta(days=i))} for i in range(days)]


def spend_today_total(db: Session) -> Decimal | None:
    today = today_kyiv()
    snaps = [s for s in latest_by_ad(db).values() if s.account_id and s.date == today and s.spend_today is not None]
    return sum((s.spend_today for s in snaps), Decimal(0)) if snaps else None


def last_received(db: Session) -> datetime | None:
    return db.scalar(select(func.max(SpendSnapshot.received_at)))
