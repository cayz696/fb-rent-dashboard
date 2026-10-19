from __future__ import annotations
"""Приймання MVP-1: акаунт проходить purchased → issued, кожен крок у журналі з автором; недозволений перехід → 409."""
from app.models import Role
from tests.conftest import login, make_user

CHAIN = ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]


def mk_account(c):
    sup = c.post("/api/suppliers", json={"name": "Atlas"}).json()
    return c.post("/api/accounts", json={"supplier_id": sup["id"], "purchase_cost": "45"}).json()


def test_full_lifecycle_with_journal(admin):
    acc = mk_account(admin)
    assert acc["code"] == "FB-0001" and acc["stage"] == "purchased"
    client = admin.post("/api/clients", json={"name": "Nord"}).json()

    for st in CHAIN:
        r = admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
        assert r.status_code == 200, r.text
        if st == "checking":
            assert r.json()["check_until"]
    r = admin.post(
        f"/api/accounts/{acc['id']}/transition",
        json={"to": "issued", "client_id": client["id"], "confirm_manual": True},
    )
    assert r.status_code == 200 and r.json()["stage"] == "issued" and r.json()["client_name"] == "Nord"

    events = admin.get(f"/api/accounts/{acc['id']}/events").json()
    changes = [e for e in events if e["type"] == "stage_change"]
    assert [e["to_stage"] for e in reversed(changes)] == CHAIN + ["issued"]
    assert all(e["actor_name"] == "Admin" for e in events)
    assert events[-1]["type"] == "created"


def test_illegal_transition_409(admin):
    acc = mk_account(admin)
    r = admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": "ready"})
    assert r.status_code == 409
    assert admin.get(f"/api/accounts/{acc['id']}").json()["stage"] == "purchased"
    assert len(admin.get(f"/api/accounts/{acc['id']}/events").json()) == 1  # лише created


def test_off_needs_reason_comment_and_returns_from_reserve(admin):
    acc = mk_account(admin)
    url = f"/api/accounts/{acc['id']}/transition"
    assert admin.post(url, json={"to": "off"}).status_code == 409
    assert admin.post(url, json={"to": "off", "off_reason": "reserve"}).status_code == 409
    assert admin.post(url, json={"to": "off", "off_reason": "reserve", "comment": "у запас"}).status_code == 200
    assert admin.post(url, json={"to": "ready"}).status_code == 200
    assert admin.post(url, json={"to": "off", "off_reason": "ban", "comment": "бан"}).status_code == 200
    assert admin.post(url, json={"to": "ready"}).status_code == 409


def test_issue_needs_client(admin):
    acc = mk_account(admin)
    url = f"/api/accounts/{acc['id']}/transition"
    for st in CHAIN:
        admin.post(url, json={"to": st})
    assert admin.post(url, json={"to": "issued", "confirm_manual": True}).status_code == 409


def test_operator_permissions(admin, operator):
    acc = mk_account(admin)
    a = operator.get(f"/api/accounts/{acc['id']}").json()
    assert a["purchase_cost"] is None  # фінанси приховані
    assert admin.get(f"/api/accounts/{acc['id']}").json()["purchase_cost"] == "45.00"
    assert operator.post(f"/api/accounts/{acc['id']}/transition", json={"to": "in_adspower"}).status_code == 200
    assert operator.post("/api/clients", json={"name": "X"}).status_code == 403
    body = {"supplier_id": acc["supplier_id"], "qty": 1, "unit_cost": 1}
    assert operator.post("/api/batches", json=body).status_code == 403


def test_viewer_read_only(admin):
    acc = mk_account(admin)
    make_user("view", Role.viewer)
    v = login("view")
    assert v.get("/api/accounts").json()["total"] == 1
    assert v.post(f"/api/accounts/{acc['id']}/transition", json={"to": "in_adspower"}).status_code == 403
    assert v.post("/api/accounts", json={}).status_code == 403


def test_operator_cannot_issue(admin, operator):
    acc = mk_account(admin)
    url = f"/api/accounts/{acc['id']}/transition"
    for st in CHAIN:
        admin.post(url, json={"to": st})
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    r = operator.post(url, json={"to": "issued", "client_id": cl["id"], "confirm_manual": True})
    assert r.status_code == 403


def test_batch_creates_accounts_and_sequential_codes(admin):
    sup = admin.post("/api/suppliers", json={"name": "Atlas"}).json()
    b = admin.post("/api/batches", json={"supplier_id": sup["id"], "qty": 3, "unit_cost": "10"}).json()
    assert b["accounts_total"] == 3
    codes = sorted(a["code"] for a in admin.get("/api/accounts").json()["items"])
    assert codes == ["FB-0001", "FB-0002", "FB-0003"]


def test_list_filters_and_search(admin):
    acc = mk_account(admin)
    admin.patch(f"/api/accounts/{acc['id']}", json={"ad_account_id": "act_777", "card_last4": "4242"})
    assert admin.patch(f"/api/accounts/{acc['id']}", json={"card_last4": "12345678"}).status_code == 422
    assert admin.get("/api/accounts", params={"q": "act_777"}).json()["total"] == 1
    assert admin.get("/api/accounts", params={"q": "nomatch"}).json()["total"] == 0
    assert admin.get("/api/accounts", params={"stage": "ready"}).json()["total"] == 0
    assert admin.get("/api/accounts", params={"stage": "purchased"}).json()["total"] == 1


def test_dashboard(admin):
    mk_account(admin)
    d = admin.get("/api/dashboard").json()
    assert d["funnel"]["purchased"] == 1 and d["pool_total"] == 1 and d["spend_today"] is None
    assert set(d["off_breakdown"]) == {"ban", "reserve", "paused", "returned", "written_off"}
