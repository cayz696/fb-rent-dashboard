"""Мапер Clover Spend Export → структурні поля.

Формат payload від Clover ПОКИ НЕВІДОМИЙ (ТЗ §6.1, §12). Тому це v0: терпимий до різних назв полів і форм
(список, {"data": [...]}, одиничний запис). Сирий запис завжди зберігається в spend_snapshots.raw, тож після
отримання реального прикладу мапер уточнюється й старі дані можна перезчитати.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

LIST_KEYS = ("data", "accounts", "items", "rows", "result", "results", "records", "adaccounts")

ALIASES: dict[str, tuple[str, ...]] = {
    "ad_account_id": ("adaccountid", "actid", "accountid", "cabinetid", "adaccount", "fbaccountid", "id"),
    "spend_today": ("spendtoday", "todayspend", "spendday", "dailyspend", "todaysspend", "spend"),
    "spend_total": ("spendtotal", "totalspend", "lifetimespend", "amountspent", "spendlifetime", "total"),
    "spend_limit": ("spendlimit", "limit", "accountlimit", "spendcap", "dailylimit"),
    "ads_active": ("adsactive", "activeads", "activeadscount", "adsrunning"),
    "ads_issues": ("adsissues", "issues", "adsdisapproved", "disapprovedads", "issuesads", "adswithissues", "rejectedads"),
    "status_raw": ("status", "accountstatus", "state"),
    "timezone": ("timezone", "tz", "timezonename"),
    "date": ("date", "day", "reportdate", "statdate"),
}


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def normalize_ad_account_id(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    s = re.sub(r"^act[_\-\s]?", "", s)
    return s or None


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = re.sub(r"[^0-9.,\-]", "", str(v)).replace(",", "")
    try:
        return Decimal(s) if s not in ("", "-", ".") else None
    except InvalidOperation:
        return None


def _int(v: Any) -> int | None:
    d = _dec(v)
    return int(d) if d is not None else None


def _date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        return None


@dataclass
class Mapped:
    ad_account_id: str | None
    spend_today: Decimal | None
    spend_total: Decimal | None
    spend_limit: Decimal | None
    ads_active: int | None
    ads_issues: int | None
    status_raw: str | None
    timezone: str | None
    date: date | None
    raw: dict


def extract_records(payload: Any) -> list[dict]:
    """Дістає список записів з довільної форми payload."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k, v in payload.items():
            if _norm_key(k) in LIST_KEYS and isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        if any(_norm_key(k) in ALIASES["ad_account_id"] for k in payload):
            return [payload]
    return []


def map_record(rec: dict) -> Mapped:
    by_key = {_norm_key(k): v for k, v in rec.items()}

    def pick(field: str):
        for alias in ALIASES[field]:
            if alias in by_key and by_key[alias] not in (None, ""):
                return by_key[alias]
        return None

    return Mapped(
        ad_account_id=normalize_ad_account_id(pick("ad_account_id")),
        spend_today=_dec(pick("spend_today")),
        spend_total=_dec(pick("spend_total")),
        spend_limit=_dec(pick("spend_limit")),
        ads_active=_int(pick("ads_active")),
        ads_issues=_int(pick("ads_issues")),
        status_raw=(str(pick("status_raw")) if pick("status_raw") is not None else None),
        timezone=(str(pick("timezone")) if pick("timezone") is not None else None),
        date=_date(pick("date")),
        raw=rec,
    )
