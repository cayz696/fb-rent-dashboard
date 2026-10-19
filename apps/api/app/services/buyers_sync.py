"""Сервіс юзерів (баєрів), команд, фіксації спенду по картках FBM кожні 3–4 год,
добової звірки з FBM Cards та синхронізації з Google-таблицями команд."""
import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.fbm import Fbm, FbmError
from app.models import (
    Buyer,
    BuyerDailySpend,
    CardSpendLog,
    FbmReconciliation,
    SystemState,
    Team,
)
from app.services.spend import today_kyiv

SNAPSHOT_KEY = "fbm_cards_snapshot"
TRACKER_STATE_KEY = "fbm_spend_tracker_state"

# Відомі патерни команд у назвах карток FBM
TEAM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bCPA\s+Samurai(?:\s+Team(?:\s+298)?)?\b", re.I), "CPA Samurai Team 298"),
    (re.compile(r"\bBudget\s+Samurai(?:\s+Team(?:\s+300)?)?\b", re.I), "Budget Samurai Team 300"),
    (re.compile(r"\bSamurai\s+Team\b", re.I), "CPA Samurai Team 298"),
    (re.compile(r"\bClover\s*Group(?:\s*\(?297\)?)?(?:\s*New)?\b", re.I), "Clover Group 297"),
    (re.compile(r"\bR2D100\b", re.I), "R2D100"),
    (re.compile(r"\bT5\b", re.I), "T5"),
]

# Службові/прогрівні картки, які не є баєрами
IGNORE_CARD_PATTERNS = re.compile(r"^(прогрев|тест|test|warmup|продажа)\b", re.I)

# Спеціальні аліаси з карток FBM → канонічне ім'я в таблиці команди
BUYER_ALIASES: dict[str, str] = {
    "webgraf": "Graf",
    "graftest": "Graf",
}


def parse_money(val: str | float | int | Decimal | None) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"))
    s = str(val).strip()
    if not s or s == "—":
        return None
    # Прибираємо $, пробіли, нерозривні пробіли, замінюємо кому на крапку
    s = re.sub(r"[$€₴\s\u00a0]", "", s)
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_card_identity(
    card_name: str | None,
    existing_buyers: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Виділяє (buyer_name, team_name) із назви картки FBM.
    Наприклад:
      'WebAX4 CPA Samurai Team 298' -> ('WebAX', 'CPA Samurai Team 298')
      'WebMicky187-3 CPA Samurai Team' -> ('WebMicky187', 'CPA Samurai Team 298')
      'Web100HP CPA Samurai Team 298' -> ('Web100HP', 'CPA Samurai Team 298')
      'HelpArt5 Clover Group (297)' -> ('HelpArt', 'Clover Group 297')
      'WebGraf3 Samurai Team' -> ('Graf', 'CPA Samurai Team 298')
    """
    if not card_name:
        return None, None
    raw = card_name.strip()
    if not raw or IGNORE_CARD_PATTERNS.search(raw):
        return None, None

    team_name: str | None = None
    cleaned = raw
    for pat, canonical_team in TEAM_PATTERNS:
        m = pat.search(cleaned)
        if m:
            team_name = canonical_team
            cleaned = (cleaned[: m.start()] + " " + cleaned[m.end() :]).strip()
            break

    # Прибираємо зайві хвости типу 'New', '(297)', '298', '300'
    cleaned = re.sub(r"\b(New|297|298|300)\b|\(\d+\)", "", cleaned, flags=re.I).strip()
    if not cleaned or IGNORE_CARD_PATTERNS.search(cleaned):
        return None, team_name

    # Якщо префікс містить 'Sofa | Help Lema8' або 'Alex WebYatin5' або 'KV - Kvitka'
    if "|" in cleaned:
        parts = [p.strip() for p in cleaned.split("|") if p.strip()]
        token = parts[-1].replace("Help ", "Help")
    elif " - " in cleaned:
        parts = [p.strip() for p in cleaned.split(" - ") if p.strip()]
        token = parts[-1]
    else:
        tokens = cleaned.split()
        if len(tokens) >= 2 and tokens[0].lower() in ("help", "alex"):
            token = "".join(tokens[:2]) if tokens[0].lower() == "help" else tokens[1]
        else:
            token = tokens[0]

    # Перевіряємо збіг із вже існуючими баєрами (щоб Web100HP або WebMicky187 не обрізались)
    if existing_buyers:
        tl = token.lower()
        for low_name, orig_name in sorted(existing_buyers.items(), key=lambda x: -len(x[0])):
            if tl == low_name or tl.startswith(low_name):
                rest = tl[len(low_name) :]
                if not rest or re.fullmatch(r"[-_]?\d{1,2}", rest):
                    return orig_name, team_name

    # Відрізаємо суфікс номера картки: напр. '-3' у 'WebMicky187-3' або '4' у 'WebAX4'
    if re.search(r"-\d+$", token):
        base = re.sub(r"-\d+$", "", token)
    elif re.search(r"(?<=[A-Za-z])\d{1,2}$", token) and not token.upper().endswith("100HP") and len(token) > 2:
        base = re.sub(r"\d{1,2}$", "", token)
    else:
        base = token

    alias = BUYER_ALIASES.get(base.lower())
    if alias:
        base = alias

    if existing_buyers and base.lower() in existing_buyers:
        base = existing_buyers[base.lower()]

    return base.strip() or None, team_name


def _get_snapshot_cards(db: Session) -> list[dict]:
    st = db.get(SystemState, SNAPSHOT_KEY)
    if not st or not isinstance(st.value, dict):
        return []
    return st.value.get("cards") or []


def get_fbm_account_balances(db: Session) -> list[dict]:
    """Повертає баланси рахунків (кабінетів) FBM з актуального знімка карток."""
    cards = _get_snapshot_cards(db)
    by_acc: dict[str, dict] = {}
    for c in cards:
        acc_name = c.get("account_name") or "Основний рахунок"
        bal = parse_money(c.get("account_balance"))
        spend = parse_money(c.get("spend")) or Decimal("0")
        curr = c.get("currency") or "USD"
        if acc_name not in by_acc:
            by_acc[acc_name] = {
                "account_name": acc_name,
                "balance": bal,
                "currency": curr,
                "cards_count": 0,
                "total_spend": Decimal("0"),
                "low_balance": bal is not None and bal < Decimal("1000"),
                "negative_balance": bal is not None and bal < Decimal("0"),
            }
        by_acc[acc_name]["cards_count"] += 1
        by_acc[acc_name]["total_spend"] += spend
        if by_acc[acc_name]["balance"] is None and bal is not None:
            by_acc[acc_name]["balance"] = bal
            by_acc[acc_name]["low_balance"] = bal < Decimal("1000")
            by_acc[acc_name]["negative_balance"] = bal < Decimal("0")
    return sorted(by_acc.values(), key=lambda x: x["account_name"])


def sync_buyers_from_fbm(db: Session) -> dict:
    """Парсить нових юзерів та команди з кабінету карток FBM з перевіркою дублів."""
    cards = _get_snapshot_cards(db)
    teams_by_low: dict[str, Team] = {
        t.name.lower(): t for t in db.scalars(select(Team)).all()
    }
    buyers_by_low: dict[str, Buyer] = {
        b.name.lower(): b for b in db.scalars(select(Buyer)).all()
    }

    teams_created = 0
    buyers_created = 0
    buyers_updated = 0

    for c in cards:
        existing_map = {k: v.name for k, v in buyers_by_low.items()}
        buyer_name, team_name = parse_card_identity(c.get("name"), existing_map)
        team_obj: Team | None = None
        if team_name:
            t_low = team_name.lower()
            team_obj = teams_by_low.get(t_low)
            if not team_obj:
                team_obj = Team(name=team_name, fee_percent=Decimal("7.00"))
                db.add(team_obj)
                db.flush()
                teams_by_low[t_low] = team_obj
                teams_created += 1

        if buyer_name:
            b_low = buyer_name.lower()
            buyer_obj = buyers_by_low.get(b_low)
            owner = (c.get("owner") or "").strip() or None
            if not buyer_obj:
                buyer_obj = Buyer(
                    name=buyer_name,
                    team_id=team_obj.id if team_obj else None,
                    fbm_owner=owner,
                    is_priority=False,
                )
                db.add(buyer_obj)
                db.flush()
                buyers_by_low[b_low] = buyer_obj
                buyers_created += 1
            else:
                changed = False
                if team_obj and not buyer_obj.team_id:
                    buyer_obj.team_id = team_obj.id
                    changed = True
                if owner and not buyer_obj.fbm_owner:
                    buyer_obj.fbm_owner = owner
                    changed = True
                if changed:
                    buyers_updated += 1

    db.commit()
    return {
        "teams_created": teams_created,
        "buyers_created": buyers_created,
        "buyers_updated": buyers_updated,
        "total_teams": len(teams_by_low),
        "total_buyers": len(buyers_by_low),
    }


def sync_spends_from_fbm_payments(db: Session, days: int = 7) -> dict:
    """Підтягує точні транзакції з FBM Payments за останні N днів і розподіляє їх по датах."""
    if not settings.fbm_api_key:
        return {"synced_records": 0}

    cutoff_date = today_kyiv() - timedelta(days=days)
    buyers_by_low = {b.name.lower(): b for b in db.scalars(select(Buyer)).all()}
    existing_map = {k: v.name for k, v in buyers_by_low.items()}

    with Fbm(settings.fbm_api_url, settings.fbm_api_key, proxy=settings.fbm_proxy or None) as f:
        cards = f.cards()
        cards_map = {c.card_id: c for c in cards}

        by_b_dt: dict[tuple[uuid.UUID, date], Decimal] = {}
        page = 1
        stop = False
        while not stop and page <= 50:
            res = f._raw("/api/client-api/payments", {"perPage": 100, "page": page})
            items = res.get("data") if isinstance(res, dict) else res
            if not items:
                break
            for it in items:
                dt_str = it.get("dateTime") or ""
                if not dt_str:
                    continue
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
                if dt < cutoff_date:
                    stop = True
                    break
                amt = parse_money(it.get("merchantAmount") or it.get("accountAmount")) or Decimal("0")
                cid = str(it.get("cardId") or "")
                card = cards_map.get(cid)
                c_name = card.name if card else ""
                b_name, _ = parse_card_identity(c_name, existing_map)
                if b_name:
                    b_obj = buyers_by_low.get(b_name.lower())
                    if b_obj:
                        key = (b_obj.id, dt)
                        by_b_dt[key] = by_b_dt.get(key, Decimal("0")) + amt
            page += 1

    updated = 0
    for (b_id, dt), val in by_b_dt.items():
        daily = db.scalar(
            select(BuyerDailySpend).where(
                BuyerDailySpend.buyer_id == b_id,
                BuyerDailySpend.date == dt,
            )
        )
        if not daily:
            daily = BuyerDailySpend(buyer_id=b_id, date=dt, spend_fbm=val)
            db.add(daily)
        else:
            daily.spend_fbm = val
        updated += 1

    db.commit()
    return {"synced_records": updated, "pages_checked": page - 1}


def record_card_spends(db: Session, refresh_fbm: bool = False) -> dict:
    """Фіксує поточний спенд по всіх картках FBM у базу (кожні 3–4 год або вручну).
    Зберігає CardSpendLog та оновлює поденний спенд у BuyerDailySpend."""
    now = datetime.now(timezone.utc)
    today = today_kyiv()

    if refresh_fbm and settings.fbm_api_key:
        try:
            with Fbm(settings.fbm_api_url, settings.fbm_api_key, proxy=settings.fbm_proxy or None) as f:
                live_cards = f.cards()
            rows = [
                {
                    "card_id": c.card_id,
                    "last4": c.last4,
                    "name": c.name,
                    "status": c.status,
                    "payment_system": c.payment_system,
                    "spend": str(c.spend) if c.spend is not None else None,
                    "currency": c.currency,
                    "owner": c.owner,
                    "account_name": c.account_name,
                    "account_balance": str(c.account_balance) if c.account_balance is not None else None,
                }
                for c in live_cards
            ]
            payload = {"at": now.isoformat(), "total": len(rows), "cards": rows}
            st = db.get(SystemState, SNAPSHOT_KEY)
            if st:
                st.value = payload
            else:
                db.add(SystemState(key=SNAPSHOT_KEY, value=payload))
            db.flush()
        except FbmError as e:
            raise ValueError(f"Помилка FBM Cards: {e}") from e

    # Спочатку синхронізуємо юзерів та команди з карток
    sync_buyers_from_fbm(db)

    # При оновленні FBM також звіряємо точні транзакції по календарних датах
    if refresh_fbm and settings.fbm_api_key:
        try:
            sync_spends_from_fbm_payments(db, days=7)
        except Exception:
            pass

    cards = _get_snapshot_cards(db)
    buyers_by_low: dict[str, Buyer] = {
        b.name.lower(): b for b in db.scalars(select(Buyer)).all()
    }
    existing_map = {k: v.name for k, v in buyers_by_low.items()}

    # Останній зафіксований кумулятивний спенд по кожній картці
    subq = (
        select(
            CardSpendLog.card_id,
            func.max(CardSpendLog.id).label("max_id"),
        )
        .group_by(CardSpendLog.card_id)
        .subquery()
    )
    prev_logs: dict[str, CardSpendLog] = {
        row.card_id: row
        for row in db.scalars(
            select(CardSpendLog).join(subq, CardSpendLog.id == subq.c.max_id)
        ).all()
    }

    logged_count = 0
    total_delta = Decimal("0")
    buyer_deltas: dict[ tuple, Decimal ] = {}

    for c in cards:
        cid = str(c.get("card_id") or "")
        if not cid:
            continue
        cur_spend = parse_money(c.get("spend")) or Decimal("0")
        acc_bal = parse_money(c.get("account_balance"))
        buyer_name, _ = parse_card_identity(c.get("name"), existing_map)
        buyer = buyers_by_low.get(buyer_name.lower()) if buyer_name else None

        prev = prev_logs.get(cid)
        if prev is None:
            # Перша фіксація картки: записуємо базовий рівень spend_cumulative
            delta = Decimal("0")
        else:
            diff = cur_spend - (prev.spend_cumulative or Decimal("0"))
            delta = diff if diff > Decimal("0") else Decimal("0")

        log_entry = CardSpendLog(
            card_id=cid,
            last4=c.get("last4"),
            card_name=c.get("name"),
            buyer_id=buyer.id if buyer else None,
            team_id=buyer.team_id if buyer else None,
            account_name=c.get("account_name"),
            account_balance=acc_bal,
            spend_cumulative=cur_spend,
            spend_delta=delta,
            date=today,
            recorded_at=now,
        )
        db.add(log_entry)
        logged_count += 1
        total_delta += delta

        if buyer:
            key = (buyer.id, today)
            buyer_deltas[key] = buyer_deltas.get(key, Decimal("0")) + delta

    for (b_id, dt), d_val in buyer_deltas.items():
        daily = db.scalar(
            select(BuyerDailySpend).where(
                BuyerDailySpend.buyer_id == b_id,
                BuyerDailySpend.date == dt,
            )
        )
        if not daily:
            daily = BuyerDailySpend(buyer_id=b_id, date=dt, spend_fbm=d_val)
            db.add(daily)
        else:
            daily.spend_fbm = (daily.spend_fbm or Decimal("0")) + d_val

    tracker_state = {
        "last_recorded_at": now.isoformat(),
        "cards_logged": logged_count,
        "total_delta": str(total_delta),
    }
    st_tr = db.get(SystemState, TRACKER_STATE_KEY)
    if st_tr:
        st_tr.value = tracker_state
    else:
        db.add(SystemState(key=TRACKER_STATE_KEY, value=tracker_state))

    db.commit()
    return {
        "recorded_at": now.isoformat(),
        "cards_logged": logged_count,
        "total_delta": total_delta,
    }


def reconcile_fbm_spend(db: Session, fetch_live: bool = False) -> FbmReconciliation:
    """Добова звірка: порівнює зафіксовані суми в базі з кабінетом FBM Cards.
    Якщо є розбіжність — фіксує її та піднімає сповіщення."""
    now = datetime.now(timezone.utc)
    if fetch_live and settings.fbm_api_key:
        try:
            with Fbm(settings.fbm_api_url, settings.fbm_api_key, proxy=settings.fbm_proxy or None) as f:
                live = f.cards()
            fbm_cards = [
                {
                    "card_id": c.card_id,
                    "last4": c.last4,
                    "name": c.name,
                    "spend": str(c.spend or Decimal("0")),
                }
                for c in live
            ]
        except FbmError:
            fbm_cards = _get_snapshot_cards(db)
    else:
        fbm_cards = _get_snapshot_cards(db)

    # Останні значення в CardSpendLog
    subq = (
        select(
            CardSpendLog.card_id,
            func.max(CardSpendLog.id).label("max_id"),
        )
        .group_by(CardSpendLog.card_id)
        .subquery()
    )
    latest_logs: dict[str, CardSpendLog] = {
        row.card_id: row
        for row in db.scalars(
            select(CardSpendLog).join(subq, CardSpendLog.id == subq.c.max_id)
        ).all()
    }

    db_total = Decimal("0")
    fbm_total = Decimal("0")
    discrepancies: list[dict] = []

    for c in fbm_cards:
        cid = str(c.get("card_id") or "")
        fbm_sp = parse_money(c.get("spend")) or Decimal("0")
        fbm_total += fbm_sp
        log = latest_logs.get(cid)
        db_sp = (log.spend_cumulative if log else None)
        if db_sp is None:
            # Якщо картка ще жодного разу не фіксувалась, а на ній є спенд
            if fbm_sp > Decimal("0"):
                discrepancies.append({
                    "card_id": cid,
                    "last4": c.get("last4"),
                    "card_name": c.get("name"),
                    "db_spend": "0.00",
                    "fbm_spend": str(fbm_sp),
                    "diff": str(fbm_sp),
                    "reason": "Картка не зафіксована в БД",
                })
        else:
            db_total += db_sp
            diff = fbm_sp - db_sp
            if abs(diff) >= Decimal("0.01"):
                discrepancies.append({
                    "card_id": cid,
                    "last4": c.get("last4"),
                    "card_name": c.get("name"),
                    "db_spend": str(db_sp),
                    "fbm_spend": str(fbm_sp),
                    "diff": str(diff),
                    "reason": "Розбіжність суми з кабінетом FBM",
                })

    total_diff = fbm_total - db_total
    status = "discrepancy" if discrepancies else "ok"
    rec = FbmReconciliation(
        checked_at=now,
        status=status,
        db_total_spend=db_total.quantize(Decimal("0.01")),
        fbm_total_spend=fbm_total.quantize(Decimal("0.01")),
        diff_amount=total_diff.quantize(Decimal("0.01")),
        discrepancies=discrepancies,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def build_google_csv_url(sheet_url: str, gid: str | None = None) -> str:
    """Перетворює стандартне посилання Google Sheets на пряме посилання експорту CSV."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        return sheet_url
    doc_id = m.group(1)
    if not gid:
        g_match = re.search(r"[#&?]gid=(\d+)", sheet_url)
        gid = g_match.group(1) if g_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"


def parse_sheet_date(label: str, ref_year: int | None = None) -> date | None:
    """Парсить заголовки дат із таблиці типу '1/10', '02/10', '10.10', '2026-10-05'."""
    s = label.strip()
    if not s:
        return None
    yr = ref_year or today_kyiv().year
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", s)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            yr = int(m.group(3))
            if yr < 100:
                yr += 2000
        try:
            return date(yr, month, day)
        except ValueError:
            return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def sync_team_sheet_csv(db: Session, team: Team, csv_content: str) -> dict:
    """Парсить CSV таблиці команди (формат як на скріншоті власника):
    - Витягує баланс команди (B3), Спенд пополнено (D3), Спенд потрачено (D4), Комс % (C1)
    - Витягує всіх юзерів у стовпці A без дублів та їхній спенд по датах (стовпці F+)."""
    reader = list(csv.reader(io.StringIO(csv_content)))
    if not reader:
        return {"buyers_synced": 0, "days_synced": 0}

    # 1. Шукаємо комісію, баланс, поповнено, витрачено та рядок із датами
    date_cols: dict[int, date] = {}
    t1_col: int | None = None
    header_row_idx = -1

    for r_idx, row in enumerate(reader[:10]):
        for c_idx, cell in enumerate(row):
            c_str = cell.strip()
            # Комісія, напр. 'Комс 7%'
            m_fee = re.search(r"комс\s*(\d+(?:[.,]\d+)?)\s*%", c_str, re.I)
            if m_fee:
                fee = parse_money(m_fee.group(1))
                if fee is not None:
                    team.fee_percent = fee

            # Спенд пополнено
            if re.search(r"спенд\s+пополнено", c_str, re.I) and c_idx + 1 < len(row):
                topup = parse_money(row[c_idx + 1])
                if topup is not None:
                    team.topup_total = topup
                # Зліва від 'Спенд пополнено' у стовпці B лежить баланс команди ($2 283,48)
                if c_idx >= 1:
                    bal = parse_money(row[c_idx - 1])
                    if bal is not None:
                        team.sheet_balance = bal

            # Спенд потрачено
            if re.search(r"спенд\s+потрачено", c_str, re.I) and c_idx + 1 < len(row):
                sp_tot = parse_money(row[c_idx + 1])
                if sp_tot is not None:
                    team.spend_total_sheet = sp_tot

            if c_str.upper() == "T1":
                t1_col = c_idx

            dt = parse_sheet_date(c_str)
            if dt:
                date_cols[c_idx] = dt
                header_row_idx = max(header_row_idx, r_idx)

    # Якщо баланс був у B1 або B2 або B3
    if team.sheet_balance is None:
        for r_idx in range(min(4, len(reader))):
            if len(reader[r_idx]) > 1:
                cand = parse_money(reader[r_idx][1])
                if cand is not None:
                    team.sheet_balance = cand
                    break

    buyers_by_low: dict[str, Buyer] = {
        b.name.lower(): b for b in db.scalars(select(Buyer)).all()
    }

    start_row = max(header_row_idx + 1, 4) if header_row_idx >= 0 else 4
    buyers_synced = 0
    days_synced = 0

    for row in reader[start_row:]:
        if not row:
            continue
        b_name = row[0].strip()
        if not b_name or b_name.lower() in ("юзер", "user", "w", "разом", "итого", "total"):
            continue
        b_low = b_name.lower()
        buyer = buyers_by_low.get(b_low)
        if not buyer:
            buyer = Buyer(name=b_name, team_id=team.id, is_priority=False)
            db.add(buyer)
            db.flush()
            buyers_by_low[b_low] = buyer
        else:
            if not buyer.team_id:
                buyer.team_id = team.id

        if t1_col is not None and t1_col < len(row):
            raw_cnt = row[t1_col].strip()
            if raw_cnt.isdigit():
                buyer.accounts_count = int(raw_cnt)

        buyers_synced += 1

        for c_idx, dt in date_cols.items():
            if c_idx >= len(row):
                continue
            val = parse_money(row[c_idx])
            if val is None:
                continue
            daily = db.scalar(
                select(BuyerDailySpend).where(
                    BuyerDailySpend.buyer_id == buyer.id,
                    BuyerDailySpend.date == dt,
                )
            )
            if not daily:
                daily = BuyerDailySpend(
                    buyer_id=buyer.id,
                    date=dt,
                    spend_fbm=val,
                    spend_sheet=val,
                )
                db.add(daily)
            else:
                daily.spend_sheet = val
                if not daily.spend_fbm or daily.spend_fbm == Decimal("0"):
                    daily.spend_fbm = val
            days_synced += 1

    team.last_sheet_sync = datetime.now(timezone.utc)
    db.commit()
    return {
        "buyers_synced": buyers_synced,
        "days_synced": days_synced,
        "sheet_balance": team.sheet_balance,
        "topup_total": team.topup_total,
        "spend_total_sheet": team.spend_total_sheet,
    }


def fetch_and_sync_team_sheet(db: Session, team: Team) -> dict:
    if not team.sheet_url:
        raise ValueError("У команди не вказано посилання на таблицю (sheet_url)")
    csv_url = build_google_csv_url(team.sheet_url, team.sheet_gid)
    try:
        r = httpx.get(csv_url, follow_redirects=True, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ValueError(f"Не вдалося прочитати таблицю: {e}") from e
    return sync_team_sheet_csv(db, team, r.text)


def push_team_spends_to_sheet(db: Session, team: Team, days: int = 31) -> dict:
    """Автоматично записує актуальні дані спенду юзерів команди в Google-таблицю
    через Google Apps Script Webhook або сервісний акаунт Google."""
    buyers = db.scalars(
        select(Buyer).where(Buyer.team_id == team.id).order_by(Buyer.is_priority.desc(), Buyer.name.asc())
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

    date_labels = [f"{d.day}/{d.month}" for d in dates]
    payload = {
        "action": "update_spends",
        "team_name": team.name,
        "date_today": f"{today.day}/{today.month}",
        "dates": date_labels,
        "fee_percent": str(team.fee_percent),
        "buyers": [
            {
                "name": b.name,
                "accounts_count": b.accounts_count or 0,
                "spend_today": str(by_b_dt.get((b.id, today), Decimal("0.00"))),
                "spends": {
                    f"{d.day}/{d.month}": str(by_b_dt.get((b.id, d), Decimal("0.00")))
                    for d in dates
                },
            }
            for b in buyers
        ],
    }

    if team.sheet_webhook_url:
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                res = client.post(team.sheet_webhook_url, json=payload)
                res.raise_for_status()
                data = res.json() if "application/json" in res.headers.get("content-type", "") else {"raw": res.text}
            team.last_sheet_sync = datetime.now(timezone.utc)
            db.commit()
            return {"ok": True, "method": "webhook", "buyers_count": len(buyers), "response": data}
        except Exception as e:
            raise ValueError(f"Помилка запису через Webhook: {e}") from e

    raise ValueError(
        "У команди не вказано Webhook URL для запису в Google-таблицю. "
        "Вкажіть Google Apps Script Webhook URL у налаштуваннях команди."
    )

