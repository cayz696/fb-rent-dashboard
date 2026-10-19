from __future__ import annotations
CHAIN = ["in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready"]


def ready_accounts(c, n):
    sup = c.post("/api/suppliers", json={"name": "S"}).json()
    c.post("/api/batches", json={"supplier_id": sup["id"], "qty": n, "unit_cost": "5"})
    accs = sorted(c.get("/api/accounts").json()["items"], key=lambda a: a["code"])
    for a in accs:
        for st in CHAIN:
            assert c.post(f"/api/accounts/{a['id']}/transition", json={"to": st}).status_code == 200
    return accs


def mk_request(c, client_id, qty=2, limit=None):
    return c.post("/api/requests", json={"client_id": client_id, "raw_text": "треба кабінети", "qty": qty, "limit": limit}).json()


def test_request_propose_oldest_ready_and_approve(admin):
    accs = ready_accounts(admin, 3)
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    r = mk_request(admin, cl["id"], 2, "250")
    assert r["status"] == "proposed"
    assert [p["code"] for p in r["proposed"]] == ["FB-0001", "FB-0002"]  # найстаріші за ready_at

    r2 = mk_request(admin, cl["id"], 2)  # FB-0001/2 зарезервовані → лише один вільний
    assert [p["code"] for p in r2["proposed"]] == ["FB-0003"] and r2["parsed"]["shortage"] == 1

    done = admin.post(f"/api/requests/{r['id']}/approve").json()
    assert done["status"] == "done" and done["approved_by_name"] == "Admin"
    for a in accs[:2]:
        got = admin.get(f"/api/accounts/{a['id']}").json()
        assert got["stage"] == "issued" and got["client_name"] == "Nord" and got["spend_limit"] == "250.00"
        ev = next(e for e in admin.get(f"/api/accounts/{a['id']}/events").json() if e["to_stage"] == "issued")
        assert ev["payload"]["request_id"] == r["id"]
    assert admin.post(f"/api/requests/{r['id']}/approve").status_code == 409  # вже закрита


def test_approve_is_atomic_when_account_changed(admin):
    accs = ready_accounts(admin, 2)
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    r = mk_request(admin, cl["id"], 2)
    admin.post(f"/api/accounts/{accs[1]['id']}/transition", json={"to": "off", "off_reason": "ban", "comment": "бан"})
    assert admin.post(f"/api/requests/{r['id']}/approve").status_code == 409
    assert admin.get(f"/api/accounts/{accs[0]['id']}").json()["stage"] == "ready"  # відкат
    assert admin.get(f"/api/requests/{r['id']}").json()["status"] == "proposed"


def test_change_reject_and_permissions(admin, operator):
    accs = ready_accounts(admin, 3)
    cl = admin.post("/api/clients", json={"name": "Nord"}).json()
    r = mk_request(operator, cl["id"], 1)  # operator створює
    assert operator.post(f"/api/requests/{r['id']}/approve").status_code == 403
    assert operator.post(f"/api/requests/{r['id']}/reject").status_code == 403
    ch = operator.put(f"/api/requests/{r['id']}/accounts", json={"account_ids": [accs[2]["id"]]}).json()
    assert [p["code"] for p in ch["proposed"]] == ["FB-0003"]
    assert operator.put(f"/api/requests/{r['id']}/accounts", json={"account_ids": [accs[0]["id"], "00000000-0000-0000-0000-000000000000"]}).status_code == 409
    assert admin.post(f"/api/requests/{r['id']}/reject").json()["status"] == "rejected"
    assert admin.get("/api/dashboard").json()["requests_queue"] == 0
