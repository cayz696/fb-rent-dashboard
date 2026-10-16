"""Приймання MVP-4: команда «Створити профіль» чекає в черзі, поки bridge офлайн, і виконується після підключення."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.main import app

settings.bridge_token = "bt"
HDR = {"Authorization": "Bearer bt"}


def mk_account(c):
    sup = c.post("/api/suppliers", json={"name": "S"}).json()
    return c.post("/api/accounts", json={"supplier_id": sup["id"]}).json()


def test_ws_rejects_bad_token():
    for h in ({}, {"Authorization": "Bearer nope"}):
        with pytest.raises(WebSocketDisconnect):
            with TestClient(app).websocket_connect("/api/bridge/ws", headers=h) as ws:
                ws.receive_json()


def test_offline_command_waits_then_executes(admin):
    acc = mk_account(admin)
    assert admin.get("/api/bridge/status").json() == {"online": False, "last_seen": None, "pending": 0}

    cmd = admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile").json()
    assert cmd["status"] == "pending" and cmd["args"]["name"] == acc["code"]
    assert admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile").status_code == 409  # дубль у черзі
    assert admin.get("/api/bridge/status").json()["pending"] == 1

    with TestClient(app).websocket_connect("/api/bridge/ws", headers=HDR) as ws:
        ws.send_json({"type": "hello"})
        msg = ws.receive_json()
        assert msg["type"] == "command" and msg["command"] == "create_profile" and msg["id"] == cmd["id"]
        ws.send_json({"type": "result", "id": msg["id"], "ok": True, "result": {"profile_id": "k77"}})
        # чекаємо, поки сервер обробить результат
        for _ in range(50):
            done = admin.get("/api/bridge/commands").json()[0]
            if done["status"] == "ok":
                break
            import time; time.sleep(0.1)

    assert done["status"] == "ok"
    a = admin.get(f"/api/accounts/{acc['id']}").json()
    assert a["adspower_profile_id"] == "k77" and a["stage"] == "in_adspower"
    ev = admin.get(f"/api/accounts/{acc['id']}/events").json()
    assert any(e["to_stage"] == "in_adspower" and e["actor"] == "bridge" for e in ev)
    assert admin.get("/api/bridge/status").json()["online"] is True
    assert admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile").status_code == 409  # профіль уже є


def test_error_result_logged_and_account_untouched(admin):
    acc = mk_account(admin)
    cmd = admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile").json()
    with TestClient(app).websocket_connect("/api/bridge/ws", headers=HDR) as ws:
        msg = ws.receive_json()
        ws.send_json({"type": "result", "id": msg["id"], "ok": False, "error": "AdsPower недоступний"})
        import time
        for _ in range(50):
            got = admin.get("/api/bridge/commands").json()[0]
            if got["status"] == "error":
                break
            time.sleep(0.1)
    assert got["status"] == "error" and got["result"]["error"] == "AdsPower недоступний"
    a = admin.get(f"/api/accounts/{acc['id']}").json()
    assert a["stage"] == "purchased" and a["adspower_profile_id"] is None
    assert any(e["type"] == "bridge_error" for e in admin.get(f"/api/accounts/{acc['id']}/events").json())
    # після помилки можна поставити команду знову
    assert admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile").status_code == 201


def test_sent_without_result_is_requeued_on_reconnect(admin):
    acc = mk_account(admin)
    admin.post(f"/api/accounts/{acc['id']}/adspower/create-profile")
    with TestClient(app).websocket_connect("/api/bridge/ws", headers=HDR) as ws:
        first = ws.receive_json()  # отримали, але «впали» без відповіді
    with TestClient(app).websocket_connect("/api/bridge/ws", headers=HDR) as ws:
        again = ws.receive_json()
    assert again["id"] == first["id"]


def test_open_close_need_profile_and_roles(admin, operator):
    acc = mk_account(admin)
    assert admin.post(f"/api/accounts/{acc['id']}/adspower/open").status_code == 409  # немає профілю
    assert admin.post(f"/api/accounts/{acc['id']}/adspower/hack").status_code == 404
    admin.patch(f"/api/accounts/{acc['id']}", json={"adspower_profile_id": "k1"})
    c = operator.post(f"/api/accounts/{acc['id']}/adspower/open")
    assert c.status_code == 201 and c.json()["command"] == "open_profile"
    assert operator.post(f"/api/bridge/commands/{c.json()['id']}/cancel").json()["status"] == "error"
    assert operator.post(f"/api/bridge/commands/{c.json()['id']}/cancel").status_code == 409


def test_whitelist_enforced_in_service(admin):
    from app.core.db import SessionLocal
    from app.services import bridge as svc
    with SessionLocal() as db:
        with pytest.raises(svc.BridgeError):
            svc.enqueue(db, "rm_rf", {}, "x")
        with pytest.raises(svc.BridgeError):
            svc.enqueue(db, "open_profile", {}, "x")


def test_offline_signal_after_15_min(admin):
    from datetime import datetime, timedelta, timezone
    from app.core.db import SessionLocal
    from app.models import SystemState
    with SessionLocal() as db:
        db.add(SystemState(key="bridge_last_seen", value={"at": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()}))
        db.commit()
    assert any(s["type"] == "bridge_offline" for s in admin.get("/api/signals").json())


def test_stage_change_queues_adspower_group_move(admin):
    acc = mk_account(admin)
    admin.patch(f"/api/accounts/{acc['id']}", json={"adspower_profile_id": "k999"})
    for st in ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking"]:
        admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    # перехід у ready → має поставити команду переносу в групу «Готовий»
    r = admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": "ready"})
    assert r.status_code == 200
    cmds = admin.get("/api/bridge/commands").json()
    move = next((c for c in cmds if c["command"] == "update_profile_group"), None)
    assert move and move["args"]["group"] == "Готовий" and move["args"]["profile_id"] == "k999"
    assert admin.get(f"/api/accounts/{acc['id']}").json()["adspower_group"] == "Готовий"


def test_no_group_move_without_profile(admin):
    acc = mk_account(admin)  # без adspower_profile_id
    for st in ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]:
        admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    assert not any(c["command"] == "update_profile_group" for c in admin.get("/api/bridge/commands").json())
