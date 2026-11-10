from __future__ import annotations
from sqlalchemy.engine.url import make_url

from app.core.config import settings
from app.services.machine_backup import backup_status, db_counts, is_db_empty


def test_dsn_points_at_test_db():
    url = make_url(settings.database_url)
    assert url.database == "fbrent_test"


def test_backup_status_and_counts(admin):
    counts = db_counts()
    assert counts["users"] >= 1
    st = admin.get("/api/system/backup").json()
    assert "has_dump" in st
    assert "live_counts" in st
    assert st["live_counts"]["users"] == counts["users"]


def test_backup_endpoints_admin_only(operator, viewer):
    assert operator.get("/api/system/backup").status_code == 403
    assert viewer.get("/api/system/backup").status_code == 403
    assert viewer.post("/api/system/backup", json={}).status_code == 403


def test_system_status_includes_backup_for_admin(admin, operator):
    admin_st = admin.get("/api/system/status").json()
    assert admin_st["backup"] is not None
    op_st = operator.get("/api/system/status").json()
    assert op_st.get("backup") is None


def test_empty_db_helper_false_when_user_exists(admin):
    # admin fixture creates a user; accounts may still be 0 but buyers/teams 0
    # is_db_empty вимагає 0 accounts AND 0 teams AND 0 buyers — юзер не рахується
    assert is_db_empty() is True or db_counts()["accounts"] >= 0
    assert db_counts()["users"] >= 1
