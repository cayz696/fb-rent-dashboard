import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://fbrent:fbrent@localhost:5440/fbrent_test"

import psycopg
import pyotp
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


@pytest.fixture(scope="session", autouse=True)
def _db():
    with psycopg.connect("postgresql://fbrent:fbrent@localhost:5440/postgres", autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS fbrent_test WITH (FORCE)")
        c.execute("CREATE DATABASE fbrent_test")
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean():
    from app.main import _hits
    from app.services.bridge import _pending_payloads
    _hits.clear()
    _pending_payloads.clear()
    yield
    with engine.begin() as c:
        c.execute(text(
            "TRUNCATE account_events, requests, spend_snapshots, accounts, batches, suppliers, clients, users, "
            "bridge_commands, system_state, client_payments, teams, buyers, card_spend_logs, "
            "buyer_daily_spends, fbm_reconciliations, expense_categories, expenses RESTART IDENTITY CASCADE"
        ))
        c.execute(text("ALTER SEQUENCE account_code_seq RESTART WITH 1"))


@pytest.fixture
def client():
    return TestClient(app)


def make_user(username="admin", role=Role.admin, pw="pw12345"):
    with SessionLocal() as db:
        db.add(User(username=username, name=username.title(), role=role, password_hash=hash_password(pw)))
        db.commit()


def login(username="admin", pw="pw12345"):
    """Повний вхід (з налаштуванням 2FA при першому вході) → авторизований TestClient."""
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": pw})
    assert r.status_code == 200, r.text
    pre = r.json()["pre_token"]
    if r.json()["step"] == "totp_setup":
        secret = c.post("/api/auth/2fa/setup", params={"pre_token": pre}).json()["secret"]
    else:
        with SessionLocal() as db:
            secret = db.query(User).filter_by(username=username).one().totp_secret
    r = c.post("/api/auth/2fa/verify", json={"pre_token": pre, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin():
    make_user("admin", Role.admin)
    return login("admin")


@pytest.fixture
def operator():
    make_user("op", Role.operator)
    return login("op")
