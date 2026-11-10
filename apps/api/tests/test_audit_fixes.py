from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import SystemState, TelegramGroup, TelegramMessageLog
from app.services import telegram_tasks
from tests.test_fbm_routes import _patch


def test_reports_do_not_use_lifetime_fbm_as_today(admin):
    with SessionLocal() as db:
        db.add(SystemState(
            key="fbm_cards_snapshot",
            value={"at": "2026-11-06T10:00:00Z", "cards": [
                {"card_id": "c1", "spend": "119000.00", "last4": "1111", "name": "Huge"},
            ]},
        ))
        db.commit()
    rep = admin.get("/api/reports/summary?fee_percent=7&date_from=2026-11-01&date_to=2026-11-30").json()
    assert float(rep["total_spend"]) == 0.0
    assert all(float(d["spend"]) == 0.0 for d in rep["daily_chart"])


def test_reports_forbidden_for_default_viewer(viewer):
    assert viewer.get("/api/reports/summary").status_code == 403


def test_reports_allowed_when_section_granted(admin):
    r = admin.post("/api/users", json={
        "username": "repview", "name": "Rep", "role": "viewer",
        "password": "password123", "allowed_sections": ["reports", "dashboard"],
    })
    assert r.status_code == 201
    from tests.conftest import login
    limited = login("repview", "password123")
    assert limited.get("/api/reports/summary").status_code == 200
    assert limited.get("/api/finance").status_code == 403
    assert limited.get("/api/users").status_code == 403


def test_finance_forbidden_for_operator(operator):
    assert operator.get("/api/finance").status_code == 403


def test_fbm_codes_forbidden_for_viewer(viewer):
    _patch()
    assert viewer.get("/api/fbm/cards/c1/codes").status_code == 403


def test_tasks_overview_does_not_leak_api_key_and_does_not_seed_demo(admin):
    saved = admin.put("/api/tasks/ai-config", json={"api_key": "sk-live-secret-key-9999", "provider": "openai"}).json()
    assert "api_key" not in saved
    assert saved["has_api_key"] is True
    ov = admin.get("/api/tasks/overview").json()
    assert "api_key" not in ov["ai_config"]
    assert ov["ai_config"]["has_api_key"] is True
    assert ov["groups"] == []


def test_telegram_ingest_auto_creates_task_when_allowed(admin):
    with SessionLocal() as db:
        g = TelegramGroup(
            chat_id=-100111,
            title="Ops",
            is_monitored=True,
            auto_create_tasks=True,
        )
        db.add(g)
        db.commit()
        db.refresh(g)
        res = telegram_tasks.ingest_message(
            db, g,
            raw_text="Терміново дайте 5 аків США з лімітом 250$ під запуск",
            sender_username="WebLumi",
            sender_name="Igor",
            allow_auto_task=True,
        )
        assert res.get("task_created") is True
        assert res.get("task_id")


def test_live_ingest_ignores_chat_that_is_not_monitored(admin):
    with SessionLocal() as db:
        db.add(TelegramGroup(chat_id=-100222, title="Off", is_monitored=False, auto_create_tasks=True))
        db.commit()
    res = telegram_tasks.ingest_new_telegram_message(-100222, 7, "нове повідомлення")
    assert res.get("skipped") is True
    with SessionLocal() as db:
        assert db.scalar(select(TelegramMessageLog.id).where(TelegramMessageLog.chat_id == -100222)) is None


def test_message_stays_in_stream_when_ai_fails(admin, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.services.task_ai_parser.analyze_telegram_message", boom)
    with SessionLocal() as db:
        g = TelegramGroup(chat_id=-100333, title="Ops live", is_monitored=True, auto_create_tasks=True)
        db.add(g)
        db.commit()
        db.refresh(g)
        res = telegram_tasks.ingest_message(db, g, "привіт, це нове", message_id=9, sender_name="Buyer", allow_auto_task=True)
    assert res["task_created"] is False
    with SessionLocal() as db:
        row = db.scalar(select(TelegramMessageLog).where(TelegramMessageLog.chat_id == -100333, TelegramMessageLog.message_id == 9))
        assert row is not None
        assert row.raw_text == "привіт, це нове"
    _patch()
    from app.services import accounts as asvc
    with SessionLocal() as db:
        a = asvc.create_account(db, "seed")
        a.card_last4 = "2570"
        db.commit()
        aid = str(a.id)
    admin.post("/api/fbm/refresh")
    before = admin.get(f"/api/accounts/{aid}").json()
    assert before["card_last4"] == "2570"
    assert before.get("card_fbm_id")
    patched = admin.patch(f"/api/accounts/{aid}", json={"notes": "after patch"}).json()
    assert patched["card_fbm_id"] == before["card_fbm_id"]
    assert patched["card_last4"] == "2570"
