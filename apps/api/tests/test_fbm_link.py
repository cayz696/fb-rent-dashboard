from __future__ import annotations
"""Звʼязок картки FBM з акаунтом по last4 (зі знімка в system_state)."""
from app.core.db import SessionLocal
from app.models import SystemState
from app.services import accounts as asvc

SNAP = {"cards": [
    {"card_id": "cardA", "last4": "2570", "name": "WebChapa Clover", "status": "VALID CARD", "spend": "183.78", "currency": "USD", "account_balance": "500.00"},
    {"card_id": "cardB", "last4": "2570", "name": "стара", "status": "PERMANENT BLOCKED BY CLIENT", "spend": "5", "currency": "USD", "account_balance": "0"},
    {"card_id": "cardC", "last4": "9999", "name": "Інша", "status": "VALID CARD", "spend": "10", "currency": "USD", "account_balance": "100"},
]}


def test_account_shows_linked_card(admin):
    with SessionLocal() as db:
        db.add(SystemState(key="fbm_cards_snapshot", value=SNAP))
        a = asvc.create_account(db, "seed"); a.card_last4 = "2570"
        db.commit(); aid = str(a.id)
    full = admin.get(f"/api/accounts/{aid}").json()
    # з двох карток 2570 обрали активну з більшим спендом
    assert full["card_fbm_id"] == "cardA" and full["card_status"] == "VALID CARD"
    assert full["card_spend"] == "183.78" and full["card_balance"] == "500.00" and full["card_name"] == "WebChapa Clover"


def test_account_without_last4_has_no_card(admin):
    with SessionLocal() as db:
        db.add(SystemState(key="fbm_cards_snapshot", value=SNAP))
        a = asvc.create_account(db, "seed")  # без card_last4
        db.commit(); aid = str(a.id)
    assert admin.get(f"/api/accounts/{aid}").json()["card_fbm_id"] is None


def test_list_includes_card(admin):
    with SessionLocal() as db:
        db.add(SystemState(key="fbm_cards_snapshot", value=SNAP))
        a = asvc.create_account(db, "seed"); a.card_last4 = "9999"
        db.commit()
    items = admin.get("/api/accounts").json()["items"]
    row = next(i for i in items if i["card_last4"] == "9999")
    assert row["card_name"] == "Інша" and row["card_spend"] == "10"
