from __future__ import annotations
"""Мапери FBM-pay на прикладах з офіційної доки. Без мережі."""
import httpx

from app.integrations.fbm import Fbm, FbmError, last4, map_card, map_code, map_payment

CARD = {"id": 11, "cardId": "MSIM3XSM9984KXIB", "name": "Прогрев24", "cardMask": "446253******2570",
        "paymentSystem": "visa", "statusName": "VALID CARD", "stateName": "Issued", "currency": "USD",
        "cardOwner": {"name": "Akiyama"}, "stats": {"spend": 183.78, "decline": 0},
        "account": {"iban": "GB23GUAV00993200161451", "name": "Account1", "balance": 429.98}}
PAYMENT = {"ID": 427833, "cardId": "PPG0ZS0MQ96I6KRZ", "cardNumber": "537383******3523",
           "accountIban": "GB23GUAV00993200161451", "dateTime": "2024-11-20T08:53:48.000000Z",
           "status": "Unhold", "type": "Debit", "merchantAmount": 12.5, "merchantCurrency": "EUR", "details": "Facebook Ads"}
CODE = {"cardId": "PPG0ZS0MQ96I6KRZ", "type": "3DS", "code": "82366", "createdAt": "2024-11-20T17:22:51.000000Z",
        "description": "Card: *******9999; Amount: 0 EUR; OTP:82366"}


def test_last4():
    assert last4("446253******2570") == "2570"
    assert last4("537383******3523") == "3523"
    assert last4(None) is None and last4("12") is None


def test_map_card():
    c = map_card(CARD)
    assert c.card_id == "MSIM3XSM9984KXIB" and c.last4 == "2570" and str(c.spend) == "183.78"
    assert c.currency == "USD" and c.owner == "Akiyama" and c.account_name == "Account1" and c.status == "VALID CARD"


def test_map_payment():
    p = map_payment({**PAYMENT, "details": "mcc=7311 ads"})
    assert p.last4 == "3523" and str(p.amount) == "12.5" and p.mcc == "7311"


def test_map_code_and_otp_fallback():
    assert map_code(CODE).code == "82366"
    # код тільки в описі
    assert map_code({"cardId": "x", "description": "… OTP: 55123", "type": "3DS"}).code == "55123"


def _fbm(handler):
    return Fbm("https://fbm-pay.com", "k", transport=httpx.MockTransport(handler))


def test_client_paginates_and_sends_key():
    seen = {}
    def h(req):
        seen["key"] = req.headers.get("x-api-key")
        page = int(dict(req.url.params).get("page", 1))
        # 2 сторінки по 1 картці
        return httpx.Response(200, json={"success": True, "data": [CARD], "meta": {"last_page": 2, "current_page": page}})
    cards = _fbm(h).cards()
    assert seen["key"] == "k" and len(cards) == 2  # обидві сторінки зібрані


def test_client_bad_key_raises():
    f = _fbm(lambda req: httpx.Response(403, json={"message": "forbidden"}))
    try:
        f.cards(); assert False
    except FbmError as e:
        assert "ключ" in str(e)
