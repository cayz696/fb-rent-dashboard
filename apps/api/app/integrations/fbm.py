from __future__ import annotations
"""Клієнт FBM-pay (картки, спенд, 3DS) + мапери. Авторизація — заголовок X-API-Key.

Реальні особливості API (звірено з живим): Laravel-пагінація (meta.last_page, page=), perPage ≤ 100,
обгортка {success, data, meta}; спенд по картці — у card.stats.spend; транзакції — /payments (mcc 7311 = реклама).

§4: повний номер (cards/{id}/credentials) НЕ запитуємо і НЕ зберігаємо; працюємо з маскою. 3DS — транзитно.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

MAX_PER_PAGE = 100


class FbmError(Exception):
    pass


def last4(mask: str | None) -> str | None:
    if not mask:
        return None
    d = re.findall(r"\d", mask)
    return "".join(d[-4:]) if len(d) >= 4 else None


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


_Q = Decimal("0.01")


def _money(v: Any) -> Decimal | None:
    d = _dec(v)
    return d.quantize(_Q) if d is not None else None


def _dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class FbmCard:
    card_id: str
    name: str | None
    last4: str | None
    payment_system: str | None
    status: str | None            # statusName (VALID CARD / …)
    state: str | None
    spend: Decimal | None         # stats.spend — витрачено по картці
    decline: Decimal | None
    currency: str | None
    owner: str | None             # cardOwner.name (баер)
    account_iban: str | None
    account_name: str | None
    account_balance: Decimal | None
    raw: dict = field(default_factory=dict)


def map_card(c: dict) -> FbmCard:
    acc = c.get("account") or {}
    stats = c.get("stats") or {}
    owner = c.get("cardOwner") or {}
    return FbmCard(
        card_id=str(c.get("cardId") or c.get("id")), name=c.get("name"), last4=last4(c.get("cardMask")),
        payment_system=c.get("paymentSystem"), status=c.get("statusName"), state=c.get("stateName"),
        spend=_money(stats.get("spend")), decline=_money(stats.get("decline")), currency=c.get("currency"),
        owner=owner.get("name"), account_iban=acc.get("iban"), account_name=acc.get("name"),
        account_balance=_money(acc.get("balance")), raw=c,
    )


@dataclass
class FbmPayment:
    txn_id: str
    last4: str | None
    at: datetime | None
    status: str | None
    type: str | None
    amount: Decimal | None
    currency: str | None
    mcc: str | None
    details: str | None


def map_payment(p: dict) -> FbmPayment:
    details = p.get("details")
    mcc = p.get("mcc")
    if not mcc and details:
        m = re.search(r"mcc=?(\d{3,4})", str(details))
        mcc = m.group(1) if m else None
    return FbmPayment(
        txn_id=str(p.get("ID") or p.get("id")), last4=last4(p.get("cardNumber")), at=_dt(p.get("dateTime")),
        status=p.get("status"), type=p.get("type"), amount=_dec(p.get("merchantAmount")),
        currency=p.get("merchantCurrency") or p.get("accountCurrency"), mcc=str(mcc) if mcc else None, details=details,
    )


@dataclass
class FbmCode:
    card_id: str | None
    code: str | None
    type: str | None
    at: datetime | None
    description: str | None


def map_code(c: dict) -> FbmCode:
    code = c.get("code")
    if not code and c.get("description"):
        m = re.search(r"OTP:?\s*(\d{4,8})", str(c["description"]))
        code = m.group(1) if m else None
    return FbmCode(card_id=str(c.get("cardId")) if c.get("cardId") else None, code=code,
                   type=c.get("type"), at=_dt(c.get("createdAt")), description=c.get("description"))


class Fbm:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        kwargs = {}
        if proxy and proxy.strip():
            kwargs["proxy"] = proxy.strip()
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=30,
            transport=transport,
            **kwargs,
        )

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _raw(self, path: str, params: dict) -> dict:
        try:
            r = self._http.get(path, params=params)
        except httpx.HTTPError as e:
            raise FbmError(f"FBM недоступний: {e}") from e
        if r.status_code in (401, 403):
            raise FbmError("FBM: невірний або недостатній ключ (X-API-Key)")
        try:
            return r.json()
        except ValueError:
            raise FbmError(f"FBM: неочікувана відповідь (HTTP {r.status_code})")

    def _page(self, path: str, params: dict | None = None, per_page: int = 100) -> list[dict]:
        """Одна сторінка списку (success/data)."""
        d = self._raw(path, {**(params or {}), "perPage": min(per_page, MAX_PER_PAGE)})
        if isinstance(d, dict) and d.get("success") is False:
            raise FbmError("FBM: запит відхилено (перевірте параметри/ліміт сторінки)")
        data = d.get("data") if isinstance(d, dict) else d
        return [x for x in (data or []) if isinstance(x, dict)]

    def _all(self, path: str, params: dict | None = None, max_items: int = 5000) -> list[dict]:
        """Усі сторінки (Laravel meta.last_page)."""
        out: list[dict] = []
        page = 1
        while True:
            d = self._raw(path, {**(params or {}), "perPage": MAX_PER_PAGE, "page": page})
            if isinstance(d, dict) and d.get("success") is False:
                if page == 1:
                    raise FbmError("FBM: запит відхилено")
                break
            items = [x for x in (d.get("data") or []) if isinstance(x, dict)]
            out += items
            last = (d.get("meta") or {}).get("last_page") or 1
            if page >= last or len(out) >= max_items or not items:
                break
            page += 1
        return out[:max_items]

    def cards(self, **params) -> list[FbmCard]:
        return [map_card(c) for c in self._all("/api/client-api/cards", params)]

    def card_payments(self, card_id: str, per_page: int = 50) -> list[FbmPayment]:
        return [map_payment(p) for p in self._page("/api/client-api/payments", {"cardId": card_id}, per_page)]

    def codes(self, card_id: str, type_: str = "otp", per_page: int = 20) -> list[FbmCode]:
        return [map_code(c) for c in self._page(f"/api/client-api/cards/{card_id}/codes/{type_}", {}, per_page)]

    def ping(self) -> int:
        """Повертає к-сть счетів; кидає FbmError при поганому ключі."""
        return len(self._page("/api/client-api/accounts", {}, 100))
