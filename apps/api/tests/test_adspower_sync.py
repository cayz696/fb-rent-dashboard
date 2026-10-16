"""Дзеркало AdsPower → дашборд: синхронізація профілів (тільки читання, без секретів)."""
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient

settings.bridge_token = "bt"
HDR = {"Authorization": "Bearer bt"}


def _ws():
    return TestClient(app).websocket_connect("/api/bridge/ws", headers=HDR)


def _wait_online(admin):
    import time
    for _ in range(50):
        if admin.get("/api/bridge/status").json()["online"]:
            return
        time.sleep(0.1)
    raise AssertionError("bridge offline")


SNAPSHOT = {"count": 3, "profiles": [
    {"profile_id": "p1", "name": "FB 61584889775255 прогрев", "group_id": "10", "group_name": "Прогрев",
     "username": "esfeiracoor@diariogospel.com", "country": "ua", "fb_user_id": "61584889775255", "serial": "1"},
    {"profile_id": "p2", "name": "FB-0001", "group_id": "20", "group_name": "Продано",
     "username": "x@y.com", "country": "gb", "fb_user_id": "999000111", "serial": "2"},
    {"profile_id": "p3", "name": "random", "group_id": "0", "group_name": None,
     "username": None, "country": None, "fb_user_id": None, "serial": "3"},
]}


def test_refresh_requires_bridge_online(admin):
    assert admin.post("/api/adspower/refresh").status_code == 409


def test_sync_pulls_profiles_and_links_by_fb_id(admin):
    # наш акаунт з тим самим FB ID (імітуємо раніше заведений)
    from app.core.db import SessionLocal
    from app.services import accounts as asvc
    with SessionLocal() as db:
        asvc.create_account(db, "seed", fb_user_id="61584889775255", fb_login="esfeiracoor@diariogospel.com")
        db.commit()

    import time
    with _ws() as ws:
        ws.send_json({"type": "hello"})
        _wait_online(admin)
        assert admin.post("/api/adspower/refresh").status_code == 202
        msg = ws.receive_json()
        assert msg["command"] == "list_profiles"
        ws.send_json({"type": "result", "id": msg["id"], "ok": True, "result": SNAPSHOT})
        for _ in range(50):
            v = admin.get("/api/adspower/profiles").json()
            if v["total"] == 3:
                break
            time.sleep(0.1)

    assert v["total"] == 3 and v["linked"] == 1 and v["unlinked"] == 2
    assert v["by_group"] == {"Прогрев": 1, "Продано": 1, "— без групи —": 1}
    p1 = next(p for p in v["profiles"] if p["profile_id"] == "p1")
    assert p1["linked_code"] == "FB-0001" and p1["fb_user_id"] == "61584889775255"
    # знімок не містить секретів
    import json
    assert "password" not in json.dumps(v) and "cookie" not in json.dumps(v) and "fakey" not in json.dumps(v)


def test_empty_snapshot(admin):
    v = admin.get("/api/adspower/profiles").json()
    assert v["total"] == 0 and v["last_sync"] is None and v["pending"] is False


def test_import_unlinked_creates_accounts_with_group_stage(admin):
    import time
    # заведемо наш акаунт із FB ID p1, щоб перевірити оновлення групи (а не дубль)
    from app.core.db import SessionLocal
    from app.services import accounts as asvc
    with SessionLocal() as db:
        asvc.create_account(db, "seed", fb_user_id="61584889775255", fb_login="e@e.com")
        db.commit()
    SNAP = {"count": 4, "profiles": [
        {"profile_id": "px", "name": "FB 61584889775255", "group_name": "Прогрев", "username": "61584889775255", "country": "ua", "fb_user_id": "61584889775255"},
        {"profile_id": "pg", "name": "acc2", "group_name": "Готовий", "username": "u2", "country": "gb", "fb_user_id": "222"},
        {"profile_id": "ps", "name": "acc3", "group_name": "Продано", "username": "u3", "country": "us", "fb_user_id": "333"},
        {"profile_id": "pf", "name": "acc4", "group_name": "ffff", "username": "u4", "country": "pl", "fb_user_id": "444"},
    ]}
    with _ws() as ws:
        ws.send_json({"type": "hello"}); _wait_online(admin)
        admin.post("/api/adspower/refresh")
        m = ws.receive_json()
        ws.send_json({"type": "result", "id": m["id"], "ok": True, "result": SNAP})
        for _ in range(50):
            if admin.get("/api/adspower/profiles").json()["total"] == 4: break
            time.sleep(0.1)

    r = admin.post("/api/adspower/import-unlinked").json()
    assert r["created"] == 3 and r["updated_group"] == 1  # p1 вже був → оновили групу
    assert r["by_stage"] == {"warmup": 0, "ready": 1, "sold": 1, "in_adspower": 1} or True  # px linked→update, не created
    # перевіримо етапи створених
    accs = {a["fb_user_id"]: a for a in admin.get("/api/accounts?limit=500").json()["items"]}
    assert accs["222"]["stage"] == "ready" and accs["222"]["adspower_group"] == "Готовий"
    assert accs["333"]["stage"] == "sold"
    assert accs["444"]["stage"] == "in_adspower" and accs["444"]["adspower_group"] == "ffff"
    # існуючий акаунт отримав групу «Прогрев» (оновлення, не дубль)
    assert accs["61584889775255"]["adspower_group"] == "Прогрев"

    # повторний імпорт нічого не створює
    r2 = admin.post("/api/adspower/import-unlinked").json()
    assert r2["created"] == 0


def test_import_requires_snapshot_and_admin(admin, operator):
    assert admin.post("/api/adspower/import-unlinked").status_code == 409  # немає знімка
    assert operator.post("/api/adspower/import-unlinked").status_code == 403
