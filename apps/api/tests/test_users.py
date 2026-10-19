from __future__ import annotations
from tests.conftest import login


def test_admin_manages_users(admin):
    r = admin.post("/api/users", json={"username": "ivan", "name": "Іван", "role": "operator", "password": "longpass1"})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert admin.post("/api/users", json={"username": "ivan", "name": "X", "role": "viewer", "password": "longpass1"}).status_code == 409
    assert admin.post("/api/users", json={"username": "bob", "name": "B", "role": "viewer", "password": "short"}).status_code == 422
    assert len(admin.get("/api/users").json()) == 2

    op = login("ivan", "longpass1")
    assert op.get("/api/users").status_code == 403

    # деактивація: сесія і вхід закриваються
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}).status_code == 200
    assert op.get("/api/me").status_code == 401
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).post("/api/auth/login", json={"username": "ivan", "password": "longpass1"}).status_code == 401


def test_reset_2fa_and_password(admin):
    uid = admin.post("/api/users", json={"username": "ivan", "name": "І", "role": "viewer", "password": "longpass1"}).json()["id"]
    login("ivan", "longpass1")
    assert admin.get("/api/users").json()[1]["totp_enabled"] is True
    r = admin.patch(f"/api/users/{uid}", json={"reset_2fa": True, "password": "newpass123"}).json()
    assert r["totp_enabled"] is False
    login("ivan", "newpass123")  # знову налаштування 2FA з новим паролем


def test_cannot_remove_last_admin(admin):
    me = admin.get("/api/me").json()["id"]
    assert admin.patch(f"/api/users/{me}", json={"role": "viewer"}).status_code == 409
    assert admin.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 409
