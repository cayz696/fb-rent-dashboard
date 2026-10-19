from __future__ import annotations
"""Фінанси: нарахування % від спенду, оплати, баланс, маржа. Доступ лише admin."""
from app.core.config import settings

CHAIN = ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]


def _set_fbm_spend(mapping: dict):
    """mapping: {last4: spend}. Кладе знімок FBM у system_state."""
    from app.core.db import SessionLocal
    from app.models import SystemState
    cards = [{"card_id": f"c{l}", "last4": l, "name": "card", "status": "VALID CARD", "spend": str(v), "currency": "USD", "account_balance": "0"} for l, v in mapping.items()]
    with SessionLocal() as db:
        st = db.get(SystemState, "fbm_cards_snapshot")
        if st: st.value = {"cards": cards}
        else: db.add(SystemState(key="fbm_cards_snapshot", value={"cards": cards}))
        db.commit()


def issue(c, client_id, last4, cost="45"):
    sup = c.post("/api/suppliers", json={"name": "S"}).json()
    acc = c.post("/api/accounts", json={"supplier_id": sup["id"], "purchase_cost": cost}).json()
    c.patch(f"/api/accounts/{acc['id']}", json={"card_last4": last4})
    for st in CHAIN:
        c.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    c.post(f"/api/accounts/{acc['id']}/transition", json={"to": "issued", "client_id": client_id, "confirm_manual": True})
    return acc


def test_accrual_payment_balance(admin):
    cl = admin.post("/api/clients", json={"name": "Nord", "fee_percent": "20", "balance": "100"}).json()
    a1 = issue(admin, cl["id"], "1001")
    a2 = issue(admin, cl["id"], "1002")
    _set_fbm_spend({"1001": 1000, "1002": 500})

    r = admin.get(f"/api/finance/clients/{cl['id']}").json()
    assert r["spend_total"] == "1500.00" and r["accrued"] == "300.00"  # 20% від 1500
    # баланс = 100 (початковий) + 0 оплат − 300 = -200
    assert r["initial_balance"] == "100.00" and r["balance"] == "-200.00"
    assert {a["code"]: a["accrued"] for a in r["accounts"]} == {a1["code"]: "200.00", a2["code"]: "100.00"}

    admin.post(f"/api/finance/clients/{cl['id']}/payments", json={"amount": "500", "note": "передоплата"})
    r2 = admin.get(f"/api/finance/clients/{cl['id']}").json()
    assert r2["paid"] == "500.00" and r2["balance"] == "300.00"  # 100 + 500 − 300
    # у картці клієнта поточний баланс теж оновився
    assert admin.get(f"/api/clients/{cl['id']}").json()["current_balance"] == "300.00"


def test_correction_and_zero_rejected(admin):
    cl = admin.post("/api/clients", json={"name": "Vega"}).json()
    admin.post(f"/api/finance/clients/{cl['id']}/payments", json={"amount": "200"})
    admin.post(f"/api/finance/clients/{cl['id']}/payments", json={"amount": "-50", "note": "коригування"})
    assert admin.get(f"/api/finance/clients/{cl['id']}").json()["paid"] == "150.00"
    assert admin.post(f"/api/finance/clients/{cl['id']}/payments", json={"amount": "0"}).status_code == 422
    assert len(admin.get(f"/api/finance/clients/{cl['id']}/payments").json()) == 2


def test_no_fee_means_zero_accrued(admin):
    cl = admin.post("/api/clients", json={"name": "Free"}).json()  # fee_percent не задано
    issue(admin, cl["id"], "9009")
    _set_fbm_spend({"9009": 999})
    r = admin.get(f"/api/finance/clients/{cl['id']}").json()
    assert r["spend_total"] == "999.00" and r["accrued"] == "0.00"


def test_overview_and_margin(admin):
    cl = admin.post("/api/clients", json={"name": "Nord", "fee_percent": "30"}).json()
    issue(admin, cl["id"], "2001", cost="40")
    off = issue(admin, cl["id"], "2002", cost="60")
    _set_fbm_spend({"2001": 1000})
    admin.post(f"/api/accounts/{off['id']}/transition", json={"to": "off", "off_reason": "ban", "comment": "бан"})

    o = admin.get("/api/finance").json()
    assert o["total_accrued"] == "300.00"  # 30% від 1000 (act_2 у off, спенд не рахуємо)
    assert o["written_off_cost"] == "60.00" and o["margin"] == "240.00"  # 300 − 60
    assert o["clover_connected"] is True
    row = next(c for c in o["clients"] if c["client_name"] == "Nord")
    assert row["accrued"] == "300.00" and row["accounts_active"] == 1


def test_finance_admin_only(admin, operator):
    cl = admin.post("/api/clients", json={"name": "X"}).json()
    assert operator.get("/api/finance").status_code == 403
    assert operator.get(f"/api/finance/clients/{cl['id']}").status_code == 403
    assert operator.post(f"/api/finance/clients/{cl['id']}/payments", json={"amount": "10"}).status_code == 403


# ---- продаж (sold) ----
def sell_setup(c, cost="40"):
    sup = c.post("/api/suppliers", json={"name": "S"}).json()
    acc = c.post("/api/accounts", json={"supplier_id": sup["id"], "purchase_cost": cost}).json()
    for st in CHAIN:
        c.post(f"/api/accounts/{acc['id']}/transition", json={"to": st})
    return acc  # на ready


def test_sell_requires_buyer_and_price(admin):
    acc = sell_setup(admin)
    url = f"/api/accounts/{acc['id']}/transition"
    assert admin.post(url, json={"to": "sold"}).status_code == 409
    assert admin.post(url, json={"to": "sold", "sold_to": "Buyer"}).status_code == 409
    r = admin.post(url, json={"to": "sold", "sold_to": "Buyer X", "sale_price": "120"})
    assert r.status_code == 200 and r.json()["stage"] == "sold"
    got = admin.get(f"/api/accounts/{acc['id']}").json()
    assert got["sold_to"] == "Buyer X" and got["sale_price"] == "120.00" and got["sold_at"]
    # sold термінальний
    assert admin.post(url, json={"to": "ready"}).status_code == 409
    assert admin.post(url, json={"to": "off", "off_reason": "ban", "comment": "x"}).status_code == 409


def test_sold_frees_client(admin):
    acc = sell_setup(admin)
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": "issued", "client_id": cl["id"], "confirm_manual": True})
    r = admin.post(f"/api/accounts/{acc['id']}/transition", json={"to": "sold", "sold_to": "Buyer", "sale_price": "200"})
    assert r.status_code == 200 and r.json()["client_id"] is None


def test_sold_only_admin(admin, operator):
    acc = sell_setup(admin)
    assert operator.post(f"/api/accounts/{acc['id']}/transition", json={"to": "sold", "sold_to": "B", "sale_price": "10"}).status_code == 403


def test_finance_sales_revenue(admin):
    a1 = sell_setup(admin, cost="40")
    admin.post(f"/api/accounts/{a1['id']}/transition", json={"to": "sold", "sold_to": "Buyer1", "sale_price": "150"})
    o = admin.get("/api/finance").json()
    assert o["sales_revenue"] == "150.00" and o["sales_count"] == 1
    # маржа включає виручку продажу мінус собівартість: 150 - 40 = 110 (оренди нема)
    assert o["margin"] == "110.00"
