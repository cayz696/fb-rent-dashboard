"""Ендпоінти FBM: знімок карток, зв'язок по last4, доступ. Мокаємо FBM-клієнт (без мережі)."""
import app.api.routes.fbm as fbm_route
from app.integrations.fbm import FbmCard, FbmCode


class FakeFbm:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def cards(self):
        from decimal import Decimal as D
        return [
            FbmCard(card_id="c1", name="WebChapa Clover Group", last4="2570", payment_system="visa", status="VALID CARD", state="Issued", spend=D("183.78"), decline=None, currency="USD", owner="Akiyama", account_iban="GB1", account_name="Account1", account_balance=D("500")),
            FbmCard(card_id="c2", name="Budget Samurai", last4="8295", payment_system="mc", status="PERMANENT BLOCKED BY CLIENT", state=None, spend=D("2"), decline=None, currency="USD", owner="Kvitka", account_iban="GB1", account_name="Account1", account_balance=D("500")),
        ]
    def codes(self, card_id, type_="3DS", per_page=20):
        return [FbmCode(card_id, "82366", "3DS", None, "OTP:82366")]


def _patch(monkey_key=True):
    from app.core.config import settings
    settings.fbm_api_key = "k" if monkey_key else ""
    fbm_route._client = lambda: FakeFbm()


def test_refresh_and_cards_with_linkage(admin):
    _patch()
    # заведемо акаунт із card_last4=2570, щоб перевірити зв'язок
    from app.core.db import SessionLocal
    from app.services import accounts as asvc
    with SessionLocal() as db:
        a = asvc.create_account(db, "seed")
        a.card_last4 = "2570"
        db.commit()

    assert admin.post("/api/fbm/refresh").json()["total"] == 2
    v = admin.get("/api/fbm/cards").json()
    assert v["total"] == 2 and v["total_spend"] == "185.78"
    assert v["by_status"] == {"VALID CARD": 1, "PERMANENT BLOCKED BY CLIENT": 1}
    top = v["cards"][0]  # відсортовано за спендом
    assert top["last4"] == "2570" and top["spend"] == "183.78" and top["linked_code"] is not None
    assert v["cards"][1]["linked_code"] is None


def test_codes_live(admin):
    _patch()
    codes = admin.get("/api/fbm/cards/c1/codes").json()
    assert codes[0]["code"] == "82366" and codes[0]["type"] == "3DS"


def test_not_configured(admin):
    _patch(monkey_key=False)
    from app.core.config import settings
    # відновимо справжній _client, щоб перевірити 503
    import importlib, app.api.routes.fbm as fr
    importlib.reload(fr)
    settings.fbm_api_key = ""
    assert admin.post("/api/fbm/refresh").status_code == 503


def test_requires_login(client):
    assert client.get("/api/fbm/cards").status_code == 401
