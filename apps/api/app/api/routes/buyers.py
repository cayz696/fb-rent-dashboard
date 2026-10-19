from __future__ import annotations
"""Маршрути для Юзерів (Баєрів), Команд, Google-таблиць, фіксації спенду кожні 3–4 год та добової звірки з FBM."""
import csv
import io
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import can_write, current_user
from app.core.db import get_db
from app.models import (
    Buyer,
    BuyerDailySpend,
    CardSpendLog,
    FbmReconciliation,
    SystemState,
    Team,
    User,
)
from app.services import buyers_sync
from app.services.spend import today_kyiv

router = APIRouter(prefix="/api/buyers", tags=["buyers"])


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    sheet_url: str | None = None
    sheet_gid: str | None = None
    sheet_webhook_url: str | None = None
    sheet_balance: Decimal | None = None
    fee_percent: Decimal = Decimal("7.00")
    notes: str | None = None


class TeamPatch(BaseModel):
    name: str | None = None
    sheet_url: str | None = None
    sheet_gid: str | None = None
    sheet_webhook_url: str | None = None
    sheet_balance: Decimal | None = None
    topup_total: Decimal | None = None
    spend_total_sheet: Decimal | None = None
    fee_percent: Decimal | None = None
    notes: str | None = None


class TeamSheetSyncIn(BaseModel):
    csv_content: str | None = None


class BuyerIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    team_id: uuid.UUID | None = None
    is_priority: bool = False
    fbm_owner: str | None = None
    accounts_count: int | None = None
    notes: str | None = None


class BuyerPatch(BaseModel):
    name: str | None = None
    team_id: uuid.UUID | None = None
    is_priority: bool | None = None
    fbm_owner: str | None = None
    accounts_count: int | None = None
    notes: str | None = None


def _map_cards_by_buyer(db: Session) -> tuple[dict[uuid.UUID, list[dict]], dict[uuid.UUID, Decimal]]:
    """Зіставляє картки з актуального знімка FBM із юзерами в БД."""
    cards = buyers_sync._get_snapshot_cards(db)
    buyers = db.scalars(select(Buyer)).all()
    buyers_by_low = {b.name.lower(): b for b in buyers}
    existing_map = {k: v.name for k, v in buyers_by_low.items()}

    by_buyer: dict[uuid.UUID, list[dict]] = {b.id: [] for b in buyers}
    spend_by_buyer: dict[uuid.UUID, Decimal] = {b.id: Decimal("0") for b in buyers}

    for c in cards:
        b_name, _ = buyers_sync.parse_card_identity(c.get("name"), existing_map)
        if not b_name:
            continue
        b_obj = buyers_by_low.get(b_name.lower())
        if not b_obj:
            continue
        sp = buyers_sync.parse_money(c.get("spend")) or Decimal("0")
        bal = buyers_sync.parse_money(c.get("account_balance"))
        by_buyer[b_obj.id].append({
            "card_id": str(c.get("card_id") or ""),
            "last4": c.get("last4"),
            "name": c.get("name"),
            "status": c.get("status"),
            "spend": sp,
            "owner": c.get("owner"),
            "account_name": c.get("account_name"),
            "account_balance": bal,
            "currency": c.get("currency") or "USD",
        })
        spend_by_buyer[b_obj.id] += sp

    for b_id in by_buyer:
        by_buyer[b_id].sort(key=lambda x: x["spend"], reverse=True)

    return by_buyer, spend_by_buyer


@router.get("/overview")
def overview(
    sort_by: str = Query("spend_total", pattern="^(spend_total|spend_today|name|cards_count)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    team_id: uuid.UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    # Якщо юзерів ще немає, але є картки FBM — парсимо автоматично при першому відкритті
    if (db.scalar(select(func.count()).select_from(Buyer)) or 0) == 0:
        if buyers_sync._get_snapshot_cards(db):
            buyers_sync.sync_buyers_from_fbm(db)

    teams = db.scalars(select(Team).order_by(Team.name)).all()
    teams_map = {t.id: t for t in teams}
    buyers = db.scalars(select(Buyer)).all()

    cards_by_buyer, fbm_spend_by_buyer = _map_cards_by_buyer(db)
    today = today_kyiv()
    month_start = today.replace(day=1)

    # Спенд за сьогодні та за поточний місяць із BuyerDailySpend
    today_rows = db.execute(
        select(BuyerDailySpend.buyer_id, func.coalesce(BuyerDailySpend.spend_fbm, 0))
        .where(BuyerDailySpend.date == today)
    ).all()
    today_map: dict[uuid.UUID, Decimal] = {r[0]: Decimal(str(r[1])) for r in today_rows}

    month_rows = db.execute(
        select(
            BuyerDailySpend.buyer_id,
            func.sum(func.coalesce(BuyerDailySpend.spend_fbm, 0)),
            func.sum(func.coalesce(BuyerDailySpend.spend_sheet, 0)),
        )
        .where(BuyerDailySpend.date >= month_start)
        .group_by(BuyerDailySpend.buyer_id)
    ).all()
    month_fbm_map: dict[uuid.UUID, Decimal] = {r[0]: Decimal(str(r[1] or 0)) for r in month_rows}
    month_sheet_map: dict[uuid.UUID, Decimal] = {r[0]: Decimal(str(r[2] or 0)) for r in month_rows}

    buyer_items = []
    team_fbm_totals: dict[uuid.UUID, Decimal] = {t.id: Decimal("0") for t in teams}
    team_buyer_counts: dict[uuid.UUID, int] = {t.id: 0 for t in teams}

    for b in buyers:
        b_cards = cards_by_buyer.get(b.id, [])
        sp_fbm = fbm_spend_by_buyer.get(b.id, Decimal("0"))
        sp_sheet = month_sheet_map.get(b.id, Decimal("0"))
        sp_total = sp_fbm if sp_fbm > Decimal("0") else sp_sheet
        sp_today = today_map.get(b.id, Decimal("0"))
        sp_month = month_fbm_map.get(b.id, Decimal("0")) or sp_total

        if b.team_id and b.team_id in team_fbm_totals:
            team_fbm_totals[b.team_id] += sp_total
            team_buyer_counts[b.team_id] += 1

        if team_id and b.team_id != team_id:
            continue
        if q:
            ql = q.lower()
            t_name = teams_map[b.team_id].name.lower() if b.team_id and b.team_id in teams_map else ""
            card_match = any(
                (c.get("last4") or "").lower().find(ql) >= 0 or (c.get("name") or "").lower().find(ql) >= 0
                for c in b_cards
            )
            if ql not in b.name.lower() and ql not in t_name and ql not in (b.fbm_owner or "").lower() and not card_match:
                continue

        buyer_items.append({
            "id": str(b.id),
            "name": b.name,
            "team_id": str(b.team_id) if b.team_id else None,
            "team_name": teams_map[b.team_id].name if b.team_id and b.team_id in teams_map else None,
            "is_priority": b.is_priority,
            "fbm_owner": b.fbm_owner,
            "accounts_count": b.accounts_count or len(b_cards),
            "cards_count": len(b_cards),
            "spend_today": sp_today.quantize(Decimal("0.01")),
            "spend_month": sp_month.quantize(Decimal("0.01")),
            "spend_total": sp_total.quantize(Decimal("0.01")),
            "spend_sheet": sp_sheet.quantize(Decimal("0.01")),
            "notes": b.notes,
            "cards": b_cards,
        })

    reverse = sort_dir == "desc"
    if sort_by == "name":
        buyer_items.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    elif sort_by == "spend_today":
        buyer_items.sort(key=lambda x: (x["spend_today"], x["spend_total"]), reverse=reverse)
    elif sort_by == "cards_count":
        buyer_items.sort(key=lambda x: (x["cards_count"], x["spend_total"]), reverse=reverse)
    else:
        buyer_items.sort(key=lambda x: x["spend_total"], reverse=reverse)

    # Пріоритетні юзери (is_priority=True) ЗАВЖДИ піднімаються наверх списку!
    buyer_items.sort(key=lambda x: not x["is_priority"])

    team_items = []
    for t in teams:
        bal = t.sheet_balance
        team_items.append({
            "id": str(t.id),
            "name": t.name,
            "sheet_url": t.sheet_url,
            "sheet_gid": t.sheet_gid,
            "sheet_webhook_url": t.sheet_webhook_url,
            "sheet_balance": bal,
            "topup_total": t.topup_total,
            "spend_total_sheet": t.spend_total_sheet,
            "spend_total_fbm": team_fbm_totals.get(t.id, Decimal("0")).quantize(Decimal("0.01")),
            "fee_percent": t.fee_percent,
            "buyers_count": team_buyer_counts.get(t.id, 0),
            "last_sheet_sync": t.last_sheet_sync,
            "low_balance": bal is not None and bal < Decimal("1000"),
            "negative_balance": bal is not None and bal < Decimal("0"),
            "notes": t.notes,
        })

    st_tr = db.get(SystemState, buyers_sync.TRACKER_STATE_KEY)
    last_rec = db.scalar(select(FbmReconciliation).order_by(FbmReconciliation.checked_at.desc()).limit(1))

    return {
        "fbm_accounts": buyers_sync.get_fbm_account_balances(db),
        "teams": team_items,
        "buyers": buyer_items,
        "tracker": st_tr.value if st_tr else None,
        "reconciliation": {
            "id": str(last_rec.id),
            "checked_at": last_rec.checked_at,
            "status": last_rec.status,
            "db_total_spend": last_rec.db_total_spend,
            "fbm_total_spend": last_rec.fbm_total_spend,
            "diff_amount": last_rec.diff_amount,
            "discrepancies": last_rec.discrepancies,
        }
        if last_rec
        else None,
    }


@router.post("/parse-fbm")
def parse_fbm(db: Session = Depends(get_db), _: User = Depends(can_write)):
    return buyers_sync.sync_buyers_from_fbm(db)


@router.post("/snapshot-spend")
def snapshot_spend(refresh_fbm: bool = False, db: Session = Depends(get_db), _: User = Depends(can_write)):
    try:
        return buyers_sync.record_card_spends(db, refresh_fbm=refresh_fbm)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/reconcile")
def reconcile(fetch_live: bool = False, db: Session = Depends(get_db), _: User = Depends(can_write)):
    rec = buyers_sync.reconcile_fbm_spend(db, fetch_live=fetch_live)
    return {
        "id": str(rec.id),
        "checked_at": rec.checked_at,
        "status": rec.status,
        "db_total_spend": rec.db_total_spend,
        "fbm_total_spend": rec.fbm_total_spend,
        "diff_amount": rec.diff_amount,
        "discrepancies": rec.discrepancies,
    }


@router.post("", status_code=201)
def create_buyer(body: BuyerIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    clean_name = body.name.strip()
    existing = db.scalar(select(Buyer).where(func.lower(Buyer.name) == clean_name.lower()))
    if existing:
        raise HTTPException(409, f"Юзер «{existing.name}» вже існує (дублікати заборонені)")
    b = Buyer(
        name=clean_name,
        team_id=body.team_id,
        is_priority=body.is_priority,
        fbm_owner=body.fbm_owner,
        accounts_count=body.accounts_count,
        notes=body.notes,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return {"id": str(b.id), "name": b.name, "is_priority": b.is_priority}


@router.patch("/{buyer_id}")
def patch_buyer(buyer_id: uuid.UUID, body: BuyerPatch, db: Session = Depends(get_db), _: User = Depends(can_write)):
    b = db.get(Buyer, buyer_id)
    if not b:
        raise HTTPException(404, "Юзера не знайдено")
    if body.name is not None:
        clean_name = body.name.strip()
        dup = db.scalar(select(Buyer).where(func.lower(Buyer.name) == clean_name.lower(), Buyer.id != buyer_id))
        if dup:
            raise HTTPException(409, f"Юзер «{dup.name}» вже існує")
        b.name = clean_name
    if "team_id" in body.model_fields_set:
        b.team_id = body.team_id
    if body.is_priority is not None:
        b.is_priority = body.is_priority
    if "fbm_owner" in body.model_fields_set:
        b.fbm_owner = body.fbm_owner
    if "accounts_count" in body.model_fields_set:
        b.accounts_count = body.accounts_count
    if "notes" in body.model_fields_set:
        b.notes = body.notes
    db.commit()
    return {"id": str(b.id), "name": b.name, "is_priority": b.is_priority, "team_id": str(b.team_id) if b.team_id else None}


@router.delete("/{buyer_id}", status_code=204)
def delete_buyer(buyer_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    b = db.get(Buyer, buyer_id)
    if not b:
        raise HTTPException(404, "Юзера не знайдено")
    db.execute(delete(BuyerDailySpend).where(BuyerDailySpend.buyer_id == buyer_id))
    db.execute(delete(CardSpendLog).where(CardSpendLog.buyer_id == buyer_id))
    db.delete(b)
    db.commit()


@router.get("/{buyer_id}")
def get_buyer_detail(
    buyer_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    b = db.get(Buyer, buyer_id)
    if not b:
        raise HTTPException(404, "Юзера не знайдено")

    today = today_kyiv()
    d_to = date_to or today
    d_from = date_from or (d_to - timedelta(days=13))

    cards_by_buyer, fbm_spend_by_buyer = _map_cards_by_buyer(db)
    b_cards = cards_by_buyer.get(b.id, [])
    lifetime_fbm = fbm_spend_by_buyer.get(b.id, Decimal("0"))

    # Поденні записи за вибраний період
    rows = db.scalars(
        select(BuyerDailySpend)
        .where(
            BuyerDailySpend.buyer_id == b.id,
            BuyerDailySpend.date >= d_from,
            BuyerDailySpend.date <= d_to,
        )
        .order_by(BuyerDailySpend.date.asc())
    ).all()
    by_dt = {r.date: r for r in rows}

    daily_series = []
    period_fbm = Decimal("0")
    period_sheet = Decimal("0")
    cur = d_from
    while cur <= d_to:
        r = by_dt.get(cur)
        s_fbm = (r.spend_fbm if r and r.spend_fbm is not None else Decimal("0")).quantize(Decimal("0.01"))
        s_sh = (r.spend_sheet if r and r.spend_sheet is not None else None)
        eff = s_fbm if s_fbm > Decimal("0") else (s_sh or Decimal("0"))
        period_fbm += eff
        if s_sh is not None:
            period_sheet += s_sh
        daily_series.append({
            "date": cur.isoformat(),
            "spend_fbm": s_fbm,
            "spend_sheet": s_sh.quantize(Decimal("0.01")) if s_sh is not None else None,
            "spend": eff.quantize(Decimal("0.01")),
        })
        cur += timedelta(days=1)

    # period_fbm є точною сумою спенду за обраний період із таблиці BuyerDailySpend (дельта FBM)

    recent_logs = db.scalars(
        select(CardSpendLog)
        .where(CardSpendLog.buyer_id == b.id)
        .order_by(CardSpendLog.recorded_at.desc())
        .limit(40)
    ).all()

    team = db.get(Team, b.team_id) if b.team_id else None

    return {
        "id": str(b.id),
        "name": b.name,
        "team_id": str(b.team_id) if b.team_id else None,
        "team_name": team.name if team else None,
        "team_sheet_balance": team.sheet_balance if team else None,
        "is_priority": b.is_priority,
        "fbm_owner": b.fbm_owner,
        "accounts_count": b.accounts_count or len(b_cards),
        "notes": b.notes,
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "period_spend": period_fbm.quantize(Decimal("0.01")),
        "period_spend_sheet": period_sheet.quantize(Decimal("0.01")),
        "lifetime_spend_fbm": lifetime_fbm.quantize(Decimal("0.01")),
        "cards": b_cards,
        "fbm_accounts": buyers_sync.get_fbm_account_balances(db),
        "daily_series": daily_series,
        "recent_logs": [
            {
                "id": lg.id,
                "card_id": lg.card_id,
                "last4": lg.last4,
                "card_name": lg.card_name,
                "spend_cumulative": lg.spend_cumulative,
                "spend_delta": lg.spend_delta,
                "account_name": lg.account_name,
                "account_balance": lg.account_balance,
                "recorded_at": lg.recorded_at,
            }
            for lg in recent_logs
        ],
    }


# ---- Команди та їхні Google-таблиці ----

@router.post("/teams", status_code=201)
def create_team(body: TeamIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    clean = body.name.strip()
    if db.scalar(select(Team).where(func.lower(Team.name) == clean.lower())):
        raise HTTPException(409, "Команда з такою назвою вже існує")
    t = Team(
        name=clean,
        sheet_url=body.sheet_url,
        sheet_gid=body.sheet_gid,
        sheet_webhook_url=body.sheet_webhook_url,
        sheet_balance=body.sheet_balance,
        fee_percent=body.fee_percent,
        notes=body.notes,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": str(t.id), "name": t.name}


@router.patch("/teams/{team_id}")
def patch_team(team_id: uuid.UUID, body: TeamPatch, db: Session = Depends(get_db), _: User = Depends(can_write)):
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "Команду не знайдено")
    if body.name is not None:
        t.name = body.name.strip()
    if "sheet_url" in body.model_fields_set:
        t.sheet_url = body.sheet_url
    if "sheet_gid" in body.model_fields_set:
        t.sheet_gid = body.sheet_gid
    if "sheet_webhook_url" in body.model_fields_set:
        t.sheet_webhook_url = body.sheet_webhook_url
    if "sheet_balance" in body.model_fields_set:
        t.sheet_balance = body.sheet_balance
    if "topup_total" in body.model_fields_set:
        t.topup_total = body.topup_total
    if "spend_total_sheet" in body.model_fields_set:
        t.spend_total_sheet = body.spend_total_sheet
    if body.fee_percent is not None:
        t.fee_percent = body.fee_percent
    if "notes" in body.model_fields_set:
        t.notes = body.notes
    db.commit()
    return {"id": str(t.id), "name": t.name, "sheet_balance": t.sheet_balance, "sheet_webhook_url": t.sheet_webhook_url}


@router.post("/teams/{team_id}/sync-sheet")
def sync_team_sheet(
    team_id: uuid.UUID,
    body: TeamSheetSyncIn | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(can_write),
):
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "Команду не знайдено")
    try:
        if body and body.csv_content:
            return buyers_sync.sync_team_sheet_csv(db, t, body.csv_content)
        return buyers_sync.fetch_and_sync_team_sheet(db, t)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/teams/{team_id}/push-sheet")
def push_team_sheet(
    team_id: uuid.UUID,
    days: int = Query(31, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(can_write),
):
    """Автоматично записує актуальні дані спенду в Google-таблицю команди."""
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "Команду не знайдено")
    try:
        return buyers_sync.push_team_spends_to_sheet(db, t, days=days)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/teams/{team_id}/export-csv", response_class=PlainTextResponse)
def export_team_sheet_csv(
    team_id: uuid.UUID,
    days: int = Query(14, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    """Генерує таблицю спенду по юзерах команди у форматі Google-таблиці власника (для дублювання даних кожні 3–4 год)."""
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "Команду не знайдено")

    buyers = db.scalars(
        select(Buyer).where(Buyer.team_id == team_id).order_by(Buyer.is_priority.desc(), Buyer.name.asc())
    ).all()
    today = today_kyiv()
    dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    rows_db = db.scalars(
        select(BuyerDailySpend).where(
            BuyerDailySpend.buyer_id.in_([b.id for b in buyers] or [uuid.uuid4()]),
            BuyerDailySpend.date >= dates[0],
        )
    ).all()
    by_b_dt: dict[tuple[uuid.UUID, date], Decimal] = {}
    for r in rows_db:
        val = r.spend_fbm if (r.spend_fbm and r.spend_fbm > Decimal("0")) else (r.spend_sheet or Decimal("0"))
        by_b_dt[(r.buyer_id, r.date)] = val

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["", "", f"Комс {t.fee_percent}%", "0", "", *[f"{d.day}/{d.month}" for d in dates]])
    w.writerow(["w", f"${t.sheet_balance or Decimal('0.00')}", "Спенд пополнено", f"${t.topup_total or Decimal('0.00')}", "T1", *["" for _ in dates]])

    day_totals = [
        sum((by_b_dt.get((b.id, d), Decimal("0")) for b in buyers), Decimal("0"))
        for d in dates
    ]
    total_spent = sum(day_totals, Decimal("0"))
    total_accs = sum((b.accounts_count or 0) for b in buyers)
    w.writerow(["Юзер", "ID аккаунта", "Спенд потрачено", f"${total_spent}", str(total_accs), *[f"${dt}" for dt in day_totals]])

    for b in buyers:
        w.writerow([
            b.name,
            "",
            "",
            "",
            str(b.accounts_count or ""),
            *[str(by_b_dt.get((b.id, d), Decimal("0.00"))) for d in dates],
        ])

    return buf.getvalue()
