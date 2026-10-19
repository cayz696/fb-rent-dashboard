from __future__ import annotations
"""Фінанси: спенд по клієнтах, нарахування за умовами (% від спенду), собівартість, маржа, баланс.

Модель нарахувань (за замовчуванням, поки власник не уточнив умови — ТЗ §12):
- Клієнт платить нам `fee_percent` % від власного спенду. Немає відсотка → нарахування 0 (лише інформативний спенд).
- Нараховане клієнту = сума spend_total його виданих/повернутих кабінетів × fee_percent%.
- Баланс клієнта = початковий залишок (`clients.balance`) + усі оплати − нараховане.
- Собівартість пулу = сума purchase_cost. Маржа = нараховане з усіх клієнтів − собівартість виданих кабінетів.

Спенд береться з **FBM** — картки акаунта (по card_last4), поле stats.spend. Це сукупний спенд по картці.
(Період/місяць — окремо, коли підтягнемо payments по датах.)
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Client, ClientPayment, SpendSnapshot, Stage
from app.services import fbm_link as fbm_link_svc

Q = Decimal("0.01")
# кабінети, спенд яких «належить» клієнту (він ними користувався)
CLIENT_STAGES = (Stage.issued, Stage.returned)


def _spend_total_by_account(db: Session, accounts: list[Account]) -> dict:
    """{account.id: спенд} з FBM-картки акаунта (по card_last4)."""
    cards = fbm_link_svc.account_cards(accounts, db)
    return {aid: Decimal(c["spend"]) for aid, c in cards.items() if c.get("spend")}


def client_report(db: Session, client: Client) -> dict:
    accounts = db.scalars(select(Account).where(Account.client_id == client.id)).all()
    relevant = [a for a in accounts if a.stage in CLIENT_STAGES]
    spend_by_acc = _spend_total_by_account(db, relevant)
    spend = sum(spend_by_acc.values(), Decimal(0))
    fee_pct = client.fee_percent or Decimal(0)
    accrued = (spend * fee_pct / 100).quantize(Q)
    paid = db.scalar(select(func.coalesce(func.sum(ClientPayment.amount), 0)).where(ClientPayment.client_id == client.id)) or Decimal(0)
    balance = (Decimal(client.balance or 0) + Decimal(paid) - accrued).quantize(Q)
    return {
        "client_id": client.id, "client_name": client.name, "fee_percent": fee_pct,
        "accounts_active": sum(1 for a in accounts if a.stage == Stage.issued),
        "spend_total": spend.quantize(Q), "accrued": accrued,
        "initial_balance": Decimal(client.balance or 0).quantize(Q), "paid": Decimal(paid).quantize(Q),
        "balance": balance,
        "accounts": [
            {"id": a.id, "code": a.code, "stage": a.stage,
             "spend_total": spend_by_acc.get(a.id, Decimal(0)).quantize(Q),
             "accrued": (spend_by_acc.get(a.id, Decimal(0)) * fee_pct / 100).quantize(Q)}
            for a in sorted(relevant, key=lambda x: x.code)
        ],
    }


def overview(db: Session) -> dict:
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    rows = [client_report(db, c) for c in clients]
    total_accrued = sum((r["accrued"] for r in rows), Decimal(0))
    total_spend = sum((r["spend_total"] for r in rows), Decimal(0))

    # собівартість виданих/повернутих кабінетів (гроші, що «в роботі» у клієнтів)
    issued_cost = db.scalar(
        select(func.coalesce(func.sum(Account.purchase_cost), 0)).where(Account.stage.in_(CLIENT_STAGES))
    ) or Decimal(0)
    pool_cost = db.scalar(
        select(func.coalesce(func.sum(Account.purchase_cost), 0)).where(Account.stage != Stage.off)
    ) or Decimal(0)
    written_off_cost = db.scalar(
        select(func.coalesce(func.sum(Account.purchase_cost), 0)).where(Account.stage == Stage.off)
    ) or Decimal(0)
    sales_revenue = db.scalar(
        select(func.coalesce(func.sum(Account.sale_price), 0)).where(Account.stage == Stage.sold)
    ) or Decimal(0)
    sales_count = db.scalar(
        select(func.count()).select_from(Account).where(Account.stage == Stage.sold)
    ) or 0
    sold_cost = db.scalar(
        select(func.coalesce(func.sum(Account.purchase_cost), 0)).where(Account.stage == Stage.sold)
    ) or Decimal(0)

    return {
        "clients": [
            {k: r[k] for k in ("client_id", "client_name", "fee_percent", "accounts_active", "spend_total", "accrued", "balance")}
            for r in rows
        ],
        "total_spend": total_spend.quantize(Q),
        "total_accrued": total_accrued.quantize(Q),
        "issued_cost": Decimal(issued_cost).quantize(Q),
        "pool_cost": Decimal(pool_cost).quantize(Q),
        "written_off_cost": Decimal(written_off_cost).quantize(Q),
        "sales_revenue": Decimal(sales_revenue).quantize(Q),
        "sales_count": sales_count,
        # маржа: комісія з оренди + (виручка продажів − їх собівартість) − собівартість списаних
        "margin": (total_accrued + Decimal(sales_revenue) - Decimal(sold_cost) - Decimal(written_off_cost)).quantize(Q),
        "clover_connected": db.get(__import__("app.models", fromlist=["SystemState"]).SystemState, "fbm_cards_snapshot") is not None,
    }
