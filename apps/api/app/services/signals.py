from __future__ import annotations
"""Сигнали (розділ 8 ТЗ). Обчислюються на льоту при запиті (дешево на нашому масштабі);
окрема фонова задача кожні 15 хв знадобиться, коли сигнали почнуть надсилатись у Telegram."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Account, FbmReconciliation, SpendSnapshot, Stage, Team
from app.schemas.api import SignalOut
from app.services import bridge as bridge_svc
from app.services import buyers_sync
from app.services import spend as spend_svc
from app.services.state_machine import CHECK_WARN_MINUTES

ZERO_SPEND_YESTERDAY_MIN = Decimal(10)
LOW_BALANCE_THRESHOLD = Decimal(1000)


def check_ending_filter():
    horizon = datetime.now(timezone.utc) + timedelta(minutes=CHECK_WARN_MINUTES)
    return and_(Account.stage == Stage.checking, Account.check_until.is_not(None), Account.check_until <= horizon)


def compute(db: Session) -> list[SignalOut]:
    now = datetime.now(timezone.utc)
    out: list[SignalOut] = []

    for a in db.scalars(select(Account).where(check_ending_filter()).order_by(Account.check_until)):
        out.append(SignalOut(
            type="check_ending", severity="warning", account_id=a.id, code=a.code,
            message="Перевірка 24г завершена" if a.check_until <= now else "Перевірка 24г завершується",
        ))

    issued = db.scalars(select(Account).where(Account.stage == Stage.issued, Account.ad_account_id.is_not(None))).all()
    if issued:
        view = spend_svc.snapshot_view(issued, db)
        today = spend_svc.today_kyiv()
        for a in issued:
            v = view.get(a.id)
            if not v:
                continue
            if v["ads_issues"] and v["ads_issues"] > 0:
                out.append(SignalOut(type="ads_issues", severity="danger", account_id=a.id, code=a.code,
                                     message=f"Проблемні оголошення: {v['ads_issues']}"))
            if v["spend_today"] is not None and v["spend_today"] == 0:
                ad = spend_svc.normalize_ad_account_id(a.ad_account_id)
                yesterday = next((p["spend"] for p in spend_svc.daily_series(db, ad, 2) if p["date"] == (today - timedelta(days=1)).isoformat()), None)
                if yesterday is not None and yesterday > ZERO_SPEND_YESTERDAY_MIN:
                    out.append(SignalOut(type="zero_spend", severity="warning", account_id=a.id, code=a.code,
                                         message=f"Нульовий спенд сьогодні (вчора ${yesterday})"))

    # Перевірка балансів кабінетів FBM (< $1000 або < $0)
    for acc_bal in buyers_sync.get_fbm_account_balances(db):
        bal = acc_bal["balance"]
        if bal is not None:
            if bal < Decimal("0"):
                out.append(SignalOut(
                    type="low_balance", severity="danger", account_id=None, code=acc_bal["account_name"],
                    message=f"Мінусовий баланс кабінету FBM {acc_bal['account_name']}: ${bal}",
                ))
            elif bal < LOW_BALANCE_THRESHOLD:
                out.append(SignalOut(
                    type="low_balance", severity="warning", account_id=None, code=acc_bal["account_name"],
                    message=f"Баланс кабінету FBM {acc_bal['account_name']} менше $1000: ${bal}",
                ))

    # Перевірка балансів команд із таблиць (< $1000 або < $0)
    for team in db.scalars(select(Team).where(Team.sheet_balance.is_not(None))).all():
        bal = team.sheet_balance
        if bal is not None:
            if bal < Decimal("0"):
                out.append(SignalOut(
                    type="team_low_balance", severity="danger", account_id=None, code=team.name,
                    message=f"Мінусовий баланс команди «{team.name}»: ${bal}",
                ))
            elif bal < LOW_BALANCE_THRESHOLD:
                out.append(SignalOut(
                    type="team_low_balance", severity="warning", account_id=None, code=team.name,
                    message=f"Баланс команди «{team.name}» менше $1000: ${bal}",
                ))

    # Перевірка добової звірки розбіжностей дашборд ↔ FBM Cards
    last_rec = db.scalar(select(FbmReconciliation).order_by(FbmReconciliation.checked_at.desc()).limit(1))
    if last_rec and last_rec.status == "discrepancy":
        cnt = len(last_rec.discrepancies or [])
        out.append(SignalOut(
            type="fbm_discrepancy", severity="danger", account_id=None, code="FBM Звірка",
            message=f"Розбіжність сум із FBM Cards: {cnt} карток (різниця ${last_rec.diff_amount})",
        ))

    last = spend_svc.last_received(db)
    if last and now - last > timedelta(hours=spend_svc.STALE_HOURS):
        hours = int((now - last).total_seconds() // 3600)
        out.append(SignalOut(type="clover_stale", severity="danger", account_id=None, code=None,
                             message=f"Clover не надсилав дані {hours} год"))
    gap = bridge_svc.offline_too_long(db)
    if gap:
        pending = bridge_svc.pending_count(db)
        tail = f" — {pending} команд у черзі" if pending else ""
        out.append(SignalOut(type="bridge_offline", severity="warning" if not pending else "danger", account_id=None, code=None,
                             message=f"Bridge офлайн {int(gap.total_seconds() // 60)} хв{tail}"))
    return out


def account_ids(db: Session) -> set:
    return {s.account_id for s in compute(db) if s.account_id}
