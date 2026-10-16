from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.db import SessionLocal
from app.integrations.clover_mapper import extract_records, map_record
from app.models import SpendSnapshot
from app.services.spend import today_kyiv

settings.clover_spend_secret = "s3cret"
H = {"X-Clover-Secret": "s3cret"}
CHAIN = ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]


def issued_account(c, ad_id="act_123"):
    sup = c.post("/api/suppliers", json={"name": "S"}).json()
    acc = c.post("/api/accounts", json={"supplier_id": sup["id"]}).json()
    c.patch(f"/api/accounts/{acc['id']}", json={"ad_account_id": ad_id})
    cl = c.post("/api/clients", json={"name": "Nord"}).json()
    for st in CHAIN:
        c.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    c.post(f"/api/accounts/{acc['id']}/transition", json={"to": "issued", "client_id": cl["id"], "confirm_manual": True})
    return acc


def test_mapper_shapes():
    assert len(extract_records([{"id": 1}, {"id": 2}])) == 2
    assert len(extract_records({"data": [{"a": 1}]})) == 1
    assert len(extract_records({"ad_account_id": "1"})) == 1
    m = map_record({"Ad Account ID": "act_555", "Spend Today": "$1,234.50", "Issues": "3", "limit": 250})
    assert (m.ad_account_id, str(m.spend_today), m.ads_issues, str(m.spend_limit)) == ("555", "1234.50", 3, "250")


def test_auth_required(client):
    assert client.post("/api/clover/spend", json=[]).status_code == 401
    assert client.post("/api/clover/spend", headers={"X-Clover-Secret": "bad"}, json=[]).status_code == 401
    assert client.post("/api/clover/spend?token=s3cret", json=[]).status_code == 200


def test_ingest_matches_and_shows_in_account(admin):
    acc = issued_account(admin, "act_123")
    r = admin.post("/api/clover/spend", headers=H, json={"data": [
        {"ad_account_id": "123", "spend_today": 2.74, "spend_total": 1284, "spend_limit": 136, "ads_active": 17, "ads_issues": 4},
        {"ad_account_id": "999", "spend_today": 1},
    ]}).json()
    assert (r["stored"], r["matched"], r["unmatched"]) == (2, 1, 1)
    a = admin.get(f"/api/accounts/{acc['id']}").json()
    assert (a["spend_today"], a["spend_total"], a["ads_active"], a["ads_issues"], a["spend_limit"]) == ("2.74", "1284.00", 17, 4, "136.00")
    d = admin.get("/api/dashboard").json()
    assert d["spend_today"] is not None and d["signals_count"] >= 1
    sig = admin.get("/api/signals").json()
    assert any(s["type"] == "ads_issues" and s["account_id"] == acc["id"] for s in sig)
    assert admin.get("/api/accounts", params={"signal": "true"}).json()["total"] == 1


def test_unknown_payload_kept_raw(admin):
    admin.post("/api/clover/spend", headers=H, json={"weird": "shape"})
    with SessionLocal() as db:
        assert db.query(SpendSnapshot).count() == 1


def test_unmatched_link_and_backfill(admin):
    admin.post("/api/clover/spend", headers=H, json=[{"ad_account_id": "act_777", "spend_today": 5}])
    un = admin.get("/api/clover/unmatched").json()
    assert un[0]["ad_account_id"] == "777"
    sup = admin.post("/api/suppliers", json={"name": "S"}).json()
    acc = admin.post("/api/accounts", json={"supplier_id": sup["id"]}).json()
    assert admin.post("/api/clover/link", json={"ad_account_id": "act_777", "account_id": acc["id"]}).status_code == 200
    assert admin.get("/api/clover/unmatched").json() == []
    assert admin.get(f"/api/accounts/{acc['id']}").json()["spend_today"] == "5.00"
    other = admin.post("/api/accounts", json={"supplier_id": sup["id"]}).json()
    assert admin.post("/api/clover/link", json={"ad_account_id": "777", "account_id": other["id"]}).status_code == 409


def test_spend_series_and_zero_spend_signal(admin):
    acc = issued_account(admin, "act_42")
    y = today_kyiv() - timedelta(days=1)
    with SessionLocal() as db:
        db.add(SpendSnapshot(ad_account_id="42", account_id=acc["id"], date=y, spend_today=25))
        db.commit()
    admin.post("/api/clover/spend", headers=H, json=[{"ad_account_id": "42", "spend_today": 0, "ads_issues": 0}])
    series = admin.get(f"/api/accounts/{acc['id']}/spend", params={"days": 7}).json()
    assert len(series) == 7 and series[-2]["spend"] == "25.00" and series[-1]["spend"] == "0.00" and series[0]["spend"] is None
    assert any(s["type"] == "zero_spend" for s in admin.get("/api/signals").json())


def test_stale_signal(admin):
    with SessionLocal() as db:
        db.add(SpendSnapshot(ad_account_id="1", date=today_kyiv(), received_at=datetime.now(timezone.utc) - timedelta(hours=3)))
        db.commit()
    assert any(s["type"] == "clover_stale" for s in admin.get("/api/signals").json())
    assert admin.get("/api/clover/status").json()["stale"] is True
