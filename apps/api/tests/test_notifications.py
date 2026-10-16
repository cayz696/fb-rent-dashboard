"""Сповіщення: агрегація заявок, сигналів, помилок bridge."""
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.models import BridgeCommand, CommandStatus

CHAIN = ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]


def test_empty(admin):
    assert admin.get("/api/notifications").json() == {"count": 0, "items": []}


def test_open_request_appears(admin):
    sup = admin.post("/api/suppliers", json={"name": "S"}).json()
    admin.post("/api/batches", json={"supplier_id": sup["id"], "qty": 1, "unit_cost": "5"})
    acc = admin.get("/api/accounts").json()["items"][0]
    for st in CHAIN:
        admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    admin.post("/api/requests", json={"client_id": cl["id"], "raw_text": "треба 1 кабінет", "qty": 1})
    n = admin.get("/api/notifications").json()
    req = [i for i in n["items"] if i["type"] == "request"]
    assert len(req) == 1 and "Nord" in req[0]["title"] and req[0]["link"] == "/requests"


def test_bridge_error_appears(admin):
    with SessionLocal() as db:
        db.add(BridgeCommand(command="create_profile", args={}, status=CommandStatus.error,
                             result={"error": "AdsPower недоступний"}, created_by="x",
                             done_at=datetime.now(timezone.utc)))
        db.commit()
    n = admin.get("/api/notifications").json()
    be = [i for i in n["items"] if i["type"] == "bridge_error"]
    assert len(be) == 1 and "недоступний" in be[0]["message"] and be[0]["severity"] == "danger"


def test_old_bridge_error_excluded(admin):
    with SessionLocal() as db:
        db.add(BridgeCommand(command="create_profile", args={}, status=CommandStatus.error,
                             result={"error": "old"}, created_by="x",
                             done_at=datetime.now(timezone.utc) - timedelta(hours=30)))
        db.commit()
    assert not [i for i in admin.get("/api/notifications").json()["items"] if i["type"] == "bridge_error"]


def test_requires_login(client):
    assert client.get("/api/notifications").status_code == 401
