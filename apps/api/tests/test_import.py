from __future__ import annotations
"""Імпорт order.txt → акаунти + файл AdsPower. Перевірка на реальному зразку з відео."""
import io

from app.integrations.order_parser import parse_order, to_adspower_file, _secret_from_2fa

ORDER = (
    "Natalia Yakovleva\tesfeiracoor@diariogospel.com\txLy5666sU6i\tesfeiracoor@diariogospel.com\tPX4bINlX5ks\t"
    "2001-06-16\t61584889775255\tMozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/143.0.0.0\t"
    "https://www.facebook.com/profile.php?id=61584889775255\tEAABsbCS1iHg\t"
    '[{"name":"c_user","value":"61584889775255","domain":".facebook.com"},{"name":"xs","value":"27:abc"}]\t'
    "https://drive.google.com/file/d/11o8/view\tUK\thttps://2fa.fb.tools/NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636\t"
    "00517481,05629369,15219673"
)


def upload(text, name="order_37751882.txt"):
    return {"file": (name, io.BytesIO(text.encode()), "text/plain")}


def test_2fa_secret_extraction():
    assert _secret_from_2fa("https://2fa.fb.tools/NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636") == "NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636"
    assert _secret_from_2fa("https://2fa.fb.tools/lower-case-bad") == ""
    assert _secret_from_2fa("") == ""


def test_parser_matches_adspower_format():
    accs = parse_order(ORDER)
    assert len(accs) == 1
    a = accs[0]
    assert a.fb_user_id == "61584889775255" and a.twofa_secret == "NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636"
    assert a.warnings == []  # c_user збігається з FB ID, cookies валідні
    f = to_adspower_file(accs)
    for line in ["name=Natalia Yakovleva", "platform=facebook.com", "username=esfeiracoor@diariogospel.com",
                 "password=xLy5666sU6i", "fakey=NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636", "proxytype=noproxy",
                 "ua=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/143.0.0.0"]:
        assert line in f, line
    assert "Пароль почты: PX4bINlX5ks" in f and "Резервные коды: 00517481" in f


def test_warnings_on_mismatch():
    bad = ORDER.replace('"value":"61584889775255","domain":".facebook.com"', '"value":"999","domain":".facebook.com"')
    a = parse_order(bad)[0]
    assert "c_user у cookies не збігається з FB ID" in a.warnings


def test_preview_and_import_flow(admin):
    p = admin.post("/api/import/order/preview", files=upload(ORDER)).json()
    assert p["total"] == 1 and p["new"] == 1 and p["rows"][0]["twofa_ok"] is True and p["rows"][0]["duplicate"] is False

    r = admin.post("/api/import/order", files=upload(ORDER)).json()
    assert r["created"] == 1 and r["codes"] == ["FB-0001"]
    assert r["filename"] == "AdsPower_order_37751882_no_proxy.txt"
    assert "fakey=NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636" in r["adspower_file"]

    # акаунт створено з несекретними полями; паролю/cookies в БД немає
    acc = admin.get("/api/accounts", params={"q": "61584889775255"}).json()["items"][0]
    full = admin.get(f"/api/accounts/{acc['id']}").json()
    assert full["fb_user_id"] == "61584889775255" and full["fb_login"] == "esfeiracoor@diariogospel.com"
    assert full["country"] == "UK"
    assert "password" not in full and "cookie" not in full  # секретів у моделі немає

    # повторний імпорт того самого файлу — дублікат за FB ID
    p2 = admin.post("/api/import/order/preview", files=upload(ORDER)).json()
    assert p2["duplicates"] == 1 and p2["rows"][0]["duplicate"] is True
    r2 = admin.post("/api/import/order", files=upload(ORDER)).json()
    assert r2["created"] == 0 and r2["skipped_duplicates"] == 1


def test_import_event_logged(admin):
    admin.post("/api/import/order", files=upload(ORDER))
    acc = admin.get("/api/accounts", params={"q": "Natalia"}).json()
    # пошук по імені не працює — шукаємо по логіну
    acc = admin.get("/api/accounts", params={"q": "esfeiracoor"}).json()["items"][0]
    ev = admin.get(f"/api/accounts/{acc['id']}/events").json()
    assert any(e["type"] == "imported_from_order" for e in ev)


def test_bad_file_rejected(admin):
    assert admin.post("/api/import/order/preview", files=upload("замало\tполів")).status_code == 422
    assert admin.post("/api/import/order/preview", files=upload("")).status_code == 422


def test_viewer_cannot_import(admin):
    from tests.conftest import login, make_user
    from app.models import Role
    make_user("v", Role.viewer)
    v = login("v")
    assert v.post("/api/import/order/preview", files=upload(ORDER)).status_code == 403


# ---- повний автозавод через bridge (створення профілів AdsPower з cookies) ----
def _ws():
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.main import app
    settings.bridge_token = "bt"
    return TestClient(app).websocket_connect("/api/bridge/ws", headers={"Authorization": "Bearer bt"})


def test_import_via_bridge_requires_online(admin):
    # bridge офлайн → 409, файловий режим працює
    assert admin.post("/api/import/order?via=bridge", files=upload(ORDER)).status_code == 409
    assert admin.post("/api/import/order?via=file", files=upload(ORDER)).json()["created"] == 1


def _wait_online(admin):
    import time
    for _ in range(50):
        if admin.get("/api/bridge/status").json()["online"]:
            return
        time.sleep(0.1)
    raise AssertionError("bridge не став онлайн")


def test_import_via_bridge_creates_profile_and_advances(admin):
    import time
    with _ws() as ws:
        ws.send_json({"type": "hello"})
        _wait_online(admin)
        r = admin.post("/api/import/order?via=bridge", files=upload(ORDER)).json()
        assert r["created"] == 1 and r["queued_to_bridge"] == 1
        # bridge отримує команду з секретами в полі profile (не в args, не в БД)
        msg = ws.receive_json()
        assert msg["command"] == "create_profile_full"
        assert "password" not in msg["args"] and "cookie" not in msg["args"]  # у args лише несекретне
        assert msg["profile"]["password"] == "xLy5666sU6i"
        assert msg["profile"]["fakey"] == "NNYOCNO2WH4A3PWOVOP7MMJFKEXX2636"
        assert '"c_user"' in msg["profile"]["cookie"]
        ws.send_json({"type": "result", "id": msg["id"], "ok": True, "result": {"profile_id": "ap_900"}})
        for _ in range(50):
            done = admin.get("/api/bridge/commands").json()[0]
            if done["status"] == "ok":
                break
            time.sleep(0.1)
    assert done["status"] == "ok"
    # у БД команди — лише несекретні args, жодних cookie/password
    assert "password" not in done["args"] and "cookie" not in done["args"]
    acc = admin.get("/api/accounts", params={"q": "61584889775255"}).json()["items"][0]
    full = admin.get(f"/api/accounts/{acc['id']}").json()
    assert full["adspower_profile_id"] == "ap_900" and full["stage"] == "in_adspower"


def test_secret_lost_marks_command_error(admin):
    # команда в черзі, але payload зник із пам'яті (імітуємо перезапуск) → помилка, акаунт не чіпається
    from app.services import bridge as bsvc
    admin.post("/api/import/order?via=file", files=upload(ORDER))  # створює акаунт без bridge
    # напряму поставимо create_profile_full і очистимо памʼять
    from app.core.db import SessionLocal
    from app.models import Account
    with SessionLocal() as db:
        a = db.query(Account).first()
        cmd = bsvc.enqueue_profile_full(db, a.id, a.code, a.fb_user_id, {"password": "x"}, "tester")
        db.commit()
    bsvc._pending_payloads.clear()
    import time
    with _ws() as ws:
        for _ in range(50):
            got = admin.get("/api/bridge/commands").json()[0]
            if got["status"] == "error":
                break
            time.sleep(0.1)
    assert got["status"] == "error" and "повторіть імпорт" in got["result"]["error"]
