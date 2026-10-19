from __future__ import annotations
from tests.conftest import login, make_user


def test_requires_login(client):
    assert client.get("/api/accounts").status_code == 401
    assert client.get("/api/me").status_code == 401


def test_wrong_password(client):
    make_user()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401


def test_no_session_without_2fa(client):
    make_user()
    r = client.post("/api/auth/login", json={"username": "admin", "password": "pw12345"})
    assert r.json()["step"] == "totp_setup"
    assert client.get("/api/me").status_code == 401  # пароля недостатньо


def test_first_login_setup_then_second_login_requires_code():
    make_user()
    c = login("admin")
    assert c.get("/api/me").json()["role"] == "admin"
    c2 = login("admin")  # тепер step = totp_required
    assert c2.get("/api/me").status_code == 200


def test_wrong_totp(client):
    make_user()
    pre = client.post("/api/auth/login", json={"username": "admin", "password": "pw12345"}).json()["pre_token"]
    client.post("/api/auth/2fa/setup", params={"pre_token": pre})
    r = client.post("/api/auth/2fa/verify", json={"pre_token": pre, "code": "000000"})
    assert r.status_code == 401
    assert client.get("/api/me").status_code == 401


def test_pre_token_not_a_session(client):
    make_user()
    pre = client.post("/api/auth/login", json={"username": "admin", "password": "pw12345"}).json()["pre_token"]
    client.cookies.set("fbr_session", pre)
    assert client.get("/api/me").status_code == 401


def test_login_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


def test_logout(admin):
    admin.post("/api/auth/logout")
    assert admin.get("/api/me").status_code == 401
