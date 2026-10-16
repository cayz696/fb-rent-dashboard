from app.core.db import SessionLocal
from app.models import SystemState
from app.services.buyers_sync import parse_card_identity


def test_parse_card_identity():
    assert parse_card_identity("WebAX4 CPA Samurai Team 298") == ("WebAX", "CPA Samurai Team 298")
    assert parse_card_identity("WebMicky187-3 CPA Samurai Team") == ("WebMicky187", "CPA Samurai Team 298")
    assert parse_card_identity("Lema6 CloverGroup") == ("Lema", "Clover Group 297")
    assert parse_card_identity("SYN3 T5") == ("SYN", "T5")


def test_buyers_parse_dedup_priority_and_reconciliation(admin):
    # Seed FBM cards snapshot with 2 buyers and 2 accounts (one < $1000)
    with SessionLocal() as db:
        db.add(SystemState(
            key="fbm_cards_snapshot",
            value={
                "at": "2026-10-16T10:00:00Z",
                "cards": [
                    {
                        "card_id": "c1",
                        "name": "WebAX1 CPA Samurai Team 298",
                        "last4": "1111",
                        "spend": "1200.00",
                        "status": "Active",
                        "owner": "Account1_US",
                        "account_name": "Account1_US",
                        "account_balance": "1794.59",
                    },
                    {
                        "card_id": "c2",
                        "name": "WebAX2 CPA Samurai Team 298",
                        "last4": "2222",
                        "spend": "800.00",
                        "status": "Active",
                        "owner": "Account1_US",
                        "account_name": "Account1_US",
                        "account_balance": "1794.59",
                    },
                    {
                        "card_id": "c3",
                        "name": "Lema1 CloverGroup",
                        "last4": "3333",
                        "spend": "500.00",
                        "status": "Active",
                        "owner": "Account1",
                        "account_name": "Account1",
                        "account_balance": "792.14",
                    },
                ],
            },
        ))
        db.commit()

    # 1. Parse FBM cards & record initial spend snapshot
    r = admin.post("/api/buyers/parse-fbm")
    assert r.status_code == 200
    data = r.json()
    assert data["buyers_created"] == 2
    assert data["teams_created"] == 2

    snap = admin.post("/api/buyers/snapshot-spend").json()
    assert snap["cards_logged"] == 3

    # 2. Re-parse FBM cards -> 0 duplicates created
    r2 = admin.post("/api/buyers/parse-fbm")
    assert r2.status_code == 200
    assert r2.json()["buyers_created"] == 0

    # 3. Manual duplicate buyer creation returns 409
    r_dup = admin.post("/api/buyers", json={"name": "webax"})
    assert r_dup.status_code == 409

    # 4. Priority toggle lifts buyer to top
    buyers = admin.get("/api/buyers/overview").json()["buyers"]
    lema = next(b for b in buyers if b["name"] == "Lema")
    r_prio = admin.patch(f"/api/buyers/{lema['id']}", json={"is_priority": True})
    assert r_prio.status_code == 200
    buyers_after = admin.get("/api/buyers/overview").json()["buyers"]
    assert buyers_after[0]["name"] == "Lema"
    assert buyers_after[0]["is_priority"] is True

    # 5. Buyer detail card with date filters & separate FBM account balance
    detail = admin.get(f"/api/buyers/{lema['id']}?date_from=2026-10-01&date_to=2026-10-31").json()
    assert detail["name"] == "Lema"
    assert float(detail["lifetime_spend_fbm"]) == 500.0
    assert len(detail["fbm_accounts"]) == 2

    # 6. Reconciliation matches ($2500 == $2500)
    rec = admin.post("/api/buyers/reconcile").json()
    assert rec["status"] == "ok"
    assert float(rec["diff_amount"]) == 0.0

    # 7. Simulate FBM card spend change without recording -> reconciliation detects discrepancy
    with SessionLocal() as db:
        st = db.get(SystemState, "fbm_cards_snapshot")
        val = dict(st.value)
        cards = list(val["cards"])
        cards[0] = {**cards[0], "spend": "1350.00"}
        val["cards"] = cards
        st.value = val
        db.commit()

    rec2 = admin.post("/api/buyers/reconcile").json()
    assert rec2["status"] == "discrepancy"
    assert float(rec2["diff_amount"]) == 150.0

    # 8. Signals include low_balance (< $1000 on Account1) and fbm_discrepancy
    signals = admin.get("/api/signals").json()
    sig_types = {s["type"] for s in signals}
    assert "low_balance" in sig_types
    assert "fbm_discrepancy" in sig_types


def test_team_sheet_csv_sync_and_low_team_balance_signal(admin):
    # Create a team and sync CSV matching the user's screenshot format
    t = admin.post("/api/buyers/teams", json={"name": "CPA Samurai Team 298", "fee_percent": 7.0}).json()
    csv_text = "\n".join([
        ",,Комс 7%,$1 057,07,,1/10,2/10",
        "w,\"$450,00\",Спенд пополнено,\"$15 101,07\",T1,,",
        "Юзер,ID аккаунта,Спенд потрачено,\"$12 771,59\",35,150,325",
        "\"\",,,,,,",
        "WebAX,,,,10,100,250",
        "WebMicky187,,,,5,50,75",
    ])
    sync_res = admin.post(f"/api/buyers/teams/{t['id']}/sync-sheet", json={"csv_content": csv_text})
    assert sync_res.status_code == 200
    body = sync_res.json()
    assert float(body["sheet_balance"]) == 450.0
    assert float(body["topup_total"]) == 15101.07
    assert float(body["spend_total_sheet"]) == 12771.59
    assert body["buyers_synced"] == 2

    # Since team sheet_balance is $450 (< $1000), a team_low_balance signal should fire
    signals = admin.get("/api/signals").json()
    assert any(s["type"] == "team_low_balance" and "CPA Samurai Team 298" in s["message"] for s in signals)

    # Export CSV works
    exp = admin.get(f"/api/buyers/teams/{t['id']}/export-csv")
    assert exp.status_code == 200
    assert "WebAX" in exp.text


def test_user_allowed_sections_and_reports_break_even(admin):
    # 1. Create limited user account with allowed_sections
    r_u = admin.post("/api/users", json={
        "username": "buyer_view",
        "name": "Buyer Viewer",
        "role": "viewer",
        "password": "password123",
        "allowed_sections": ["buyers", "cards"],
    })
    assert r_u.status_code == 201
    u_data = r_u.json()
    assert u_data["allowed_sections"] == ["buyers", "cards"]

    # Update allowed_sections
    r_patch = admin.patch(f"/api/users/{u_data['id']}", json={"allowed_sections": ["buyers", "reports"]})
    assert r_patch.status_code == 200
    assert r_patch.json()["allowed_sections"] == ["buyers", "reports"]

    # 2. Reports & Break-even calculation
    cat = admin.post("/api/reports/categories", json={"name": "Проксі тест", "color": "#10b981"}).json()
    exp = admin.post("/api/reports/expenses", json={
        "category_id": cat["id"],
        "description": "Місячні резидентські проксі",
        "amount": 700.0,
        "spent_at": "2026-10-16",
    })
    assert exp.status_code == 201

    rep = admin.get("/api/reports/summary?fee_percent=7&date_from=2026-10-01&date_to=2026-10-31").json()
    assert float(rep["total_expenses"]) == 700.0
    # At 7% fee, $700 expenses requires $10,000 spend to break even
    assert float(rep["breakeven"]["spend_needed"]) == 10000.0

    # 3. System status endpoint
    st = admin.get("/api/system/status")
    assert st.status_code == 200
    assert "commit" in st.json()
