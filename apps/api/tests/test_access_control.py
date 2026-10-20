from app.models import Role
from app.services.buyers_sync import build_google_csv_url, validate_google_url
from tests.conftest import login, make_user


def test_viewer_cannot_read_reports_or_3ds(admin):
    make_user("view", Role.viewer)
    v = login("view")
    assert v.get("/api/reports/summary").status_code == 403
    assert v.get("/api/fbm/cards/card-1/codes").status_code == 403
    assert v.get("/api/finance").status_code == 403
    assert admin.get("/api/reports/categories").status_code == 200


def test_limited_sections_block_other_routes(admin):
    admin.post("/api/users", json={
        "username": "buyer_view",
        "name": "Buyer Viewer",
        "role": "viewer",
        "password": "password123",
        "allowed_sections": ["buyers", "cards"],
    })
    u = login("buyer_view", "password123")
    assert u.get("/api/buyers/overview").status_code == 200
    assert u.get("/api/fbm/cards").status_code == 200
    assert u.get("/api/accounts").status_code == 403
    assert u.get("/api/reports/summary").status_code == 403
    assert u.get("/api/fbm/cards/card-1/codes").status_code == 403


def test_explicit_reports_section_can_read_summary(admin):
    admin.post("/api/users", json={
        "username": "rep",
        "name": "Rep",
        "role": "viewer",
        "password": "password123",
        "allowed_sections": ["reports"],
    })
    u = login("rep", "password123")
    assert u.get("/api/reports/summary").status_code == 200
    assert u.post("/api/reports/categories", json={"name": "X", "color": "#fff"}).status_code == 403


def test_operator_can_open_3ds_route(operator):
    # Ключ FBM не заданий у тестах — доходимо до обробника, а не до відмови розділу.
    assert operator.get("/api/fbm/cards/card-1/codes").status_code == 503


def test_github_update_is_disabled(admin):
    assert admin.post("/api/system/github-update").status_code == 410
    assert admin.post("/api/system/github-remote", json={"remote_url": "https://evil.example/x.git"}).status_code == 410
    assert admin.get("/api/system/status").status_code == 200


def test_sheet_url_allowlist(admin):
    ok = admin.post("/api/buyers/teams", json={
        "name": "Sheets OK",
        "sheet_url": "https://docs.google.com/spreadsheets/d/abc123_XYZ/edit#gid=3",
        "sheet_webhook_url": "https://script.google.com/macros/s/abc/exec",
    })
    assert ok.status_code == 201
    bad = admin.post("/api/buyers/teams", json={
        "name": "Sheets bad",
        "sheet_url": "http://127.0.0.1:8010/api/health",
    })
    assert bad.status_code == 400
    hooked = admin.post("/api/buyers/teams", json={
        "name": "Hook bad",
        "sheet_webhook_url": "https://example.com/hook",
    })
    assert hooked.status_code == 400


def test_csv_url_rejects_raw_fallback():
    url = build_google_csv_url("https://docs.google.com/spreadsheets/d/abc123/edit?gid=7")
    assert url == "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=7"
    try:
        build_google_csv_url("https://evil.example/spreadsheets/d/abc")
        assert False, "має відхилити чужий хост"
    except ValueError:
        pass
    assert validate_google_url("", "sheet") is None
    assert validate_google_url("https://script.google.com/macros/s/x/exec", "webhook")
