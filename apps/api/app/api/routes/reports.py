"""Розділ «Звітність» (Отчетность): категорії витрат, облік витрат, формула відсотка,
розрахунок прибутку, графік та Точка прибутку (Break-even point)."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import can_write, current_user
from app.core.db import get_db
from app.models import (
    Account,
    Batch,
    BuyerDailySpend,
    Expense,
    ExpenseCategory,
    Stage,
    SystemState,
    User,
)
from app.services import buyers_sync
from app.services.spend import today_kyiv

router = APIRouter(prefix="/api/reports", tags=["reports"])

DEFAULT_CATEGORIES = [
    ("Закупівля акаунтів (Фарм/Автореги)", "#f59e0b"),
    ("Проксі", "#38bdf8"),
    ("Антидетект / Сервіси", "#a855f7"),
    ("Комісії платіжок / Картки", "#ec4899"),
    ("Зарплати / Команда", "#10b981"),
    ("Інші витрати", "#6b7280"),
]


def _ensure_default_categories(db: Session) -> list[ExpenseCategory]:
    cats = db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.created_at.asc())).all()
    if not cats:
        for name, color in DEFAULT_CATEGORIES:
            db.add(ExpenseCategory(name=name, color=color))
        db.commit()
        cats = db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.created_at.asc())).all()
    return cats


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = "#f59e0b"


class ExpenseIn(BaseModel):
    category_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    spent_at: date | None = None
    description: str | None = None


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _: User = Depends(current_user)):
    cats = _ensure_default_categories(db)
    return [{"id": str(c.id), "name": c.name, "color": c.color} for c in cats]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), _: User = Depends(can_write)):
    clean = body.name.strip()
    if db.scalar(select(ExpenseCategory).where(func.lower(ExpenseCategory.name) == clean.lower())):
        raise HTTPException(409, "Категорія з такою назвою вже існує")
    c = ExpenseCategory(name=clean, color=body.color)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": str(c.id), "name": c.name, "color": c.color}


@router.delete("/categories/{cat_id}", status_code=204)
def delete_category(cat_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    c = db.get(ExpenseCategory, cat_id)
    if not c:
        raise HTTPException(404, "Категорію не знайдено")
    has_exp = db.scalar(select(func.count()).select_from(Expense).where(Expense.category_id == cat_id)) or 0
    if has_exp > 0:
        raise HTTPException(409, "Не можна видалити категорію, у якій вже є записані витрати")
    db.delete(c)
    db.commit()


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn, db: Session = Depends(get_db), me: User = Depends(can_write)):
    cat = db.get(ExpenseCategory, body.category_id)
    if not cat:
        raise HTTPException(404, "Категорію не знайдено")
    exp = Expense(
        category_id=body.category_id,
        amount=body.amount.quantize(Decimal("0.01")),
        spent_at=body.spent_at or today_kyiv(),
        description=body.description,
        created_by=me.name or me.username,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return {
        "id": str(exp.id),
        "category_id": str(exp.category_id),
        "category_name": cat.name,
        "category_color": cat.color,
        "amount": exp.amount,
        "spent_at": exp.spent_at.isoformat(),
        "description": exp.description,
        "created_by": exp.created_by,
    }


@router.delete("/expenses/{exp_id}", status_code=204)
def delete_expense(exp_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(can_write)):
    exp = db.get(Expense, exp_id)
    if not exp:
        raise HTTPException(404, "Запис витрати не знайдено")
    db.delete(exp)
    db.commit()


@router.get("/summary")
def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    fee_percent: Decimal = Query(Decimal("7.00"), ge=0, le=100),
    include_batches_cost: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    cats = _ensure_default_categories(db)
    cats_map = {c.id: c for c in cats}

    today = today_kyiv()
    d_to = date_to or today
    d_from = date_from or d_to.replace(day=1)

    # 1. Витрати за період
    exps = db.scalars(
        select(Expense)
        .where(Expense.spent_at >= d_from, Expense.spent_at <= d_to)
        .order_by(Expense.spent_at.desc(), Expense.created_at.desc())
    ).all()

    manual_expenses_total = Decimal("0")
    by_cat_totals: dict[uuid.UUID, Decimal] = {c.id: Decimal("0") for c in cats}
    exp_by_day: dict[date, Decimal] = {}

    expense_items = []
    for e in exps:
        amt = e.amount or Decimal("0")
        manual_expenses_total += amt
        by_cat_totals[e.category_id] = by_cat_totals.get(e.category_id, Decimal("0")) + amt
        exp_by_day[e.spent_at] = exp_by_day.get(e.spent_at, Decimal("0")) + amt
        c = cats_map.get(e.category_id)
        expense_items.append({
            "id": str(e.id),
            "category_id": str(e.category_id),
            "category_name": c.name if c else "Інше",
            "category_color": c.color if c else "#6b7280",
            "amount": amt.quantize(Decimal("0.01")),
            "spent_at": e.spent_at.isoformat(),
            "description": e.description,
            "created_by": e.created_by,
        })

    # Опціонально додаємо закупівлі партій за період
    batches_cost = Decimal("0")
    if include_batches_cost:
        batches = db.scalars(
            select(Batch).where(Batch.bought_at >= d_from, Batch.bought_at <= d_to)
        ).all()
        for b in batches:
            bc = (Decimal(str(b.qty)) * (b.unit_cost or Decimal("0"))).quantize(Decimal("0.01"))
            batches_cost += bc
            exp_by_day[b.bought_at] = exp_by_day.get(b.bought_at, Decimal("0")) + bc

    total_expenses = (manual_expenses_total + batches_cost).quantize(Decimal("0.01"))

    # 2. Спенд за період (з BuyerDailySpend; якщо за період ще немає поденних записів — беремо сумарний спенд карток FBM)
    daily_rows = db.scalars(
        select(BuyerDailySpend).where(BuyerDailySpend.date >= d_from, BuyerDailySpend.date <= d_to)
    ).all()
    spend_by_day: dict[date, Decimal] = {}
    for r in daily_rows:
        eff = r.spend_fbm if (r.spend_fbm and r.spend_fbm > Decimal("0")) else (r.spend_sheet or Decimal("0"))
        spend_by_day[r.date] = spend_by_day.get(r.date, Decimal("0")) + eff

    total_spend = sum(spend_by_day.values(), Decimal("0"))
    if total_spend == Decimal("0") and d_from <= today <= d_to:
        # Fallback на загальний спенд зі знімка FBM, щоб графік і калькулятор одразу працювали на реальних $119k+
        cards = buyers_sync._get_snapshot_cards(db)
        snap_total = sum((buyers_sync.parse_money(c.get("spend")) or Decimal("0") for c in cards), Decimal("0"))
        if snap_total > Decimal("0"):
            total_spend = snap_total
            spend_by_day[today] = snap_total

    total_spend = total_spend.quantize(Decimal("0.01"))

    # 3. Продажі акаунтів за період
    sold_accs = db.scalars(
        select(Account).where(Account.stage == Stage.sold, Account.sale_price.is_not(None))
    ).all()
    sales_revenue = Decimal("0")
    sales_by_day: dict[date, Decimal] = {}
    for a in sold_accs:
        s_dt = a.sold_at.date() if a.sold_at else a.created_at.date()
        if d_from <= s_dt <= d_to:
            sp = a.sale_price or Decimal("0")
            sales_revenue += sp
            sales_by_day[s_dt] = sales_by_day.get(s_dt, Decimal("0")) + sp

    sales_revenue = sales_revenue.quantize(Decimal("0.01"))
    commission_revenue = (total_spend * fee_percent / Decimal("100")).quantize(Decimal("0.01"))
    total_revenue = (commission_revenue + sales_revenue).quantize(Decimal("0.01"))
    net_profit = (total_revenue - total_expenses).quantize(Decimal("0.01"))

    roi_percent = (
        ((net_profit / total_expenses) * Decimal("100")).quantize(Decimal("0.1"))
        if total_expenses > Decimal("0")
        else Decimal("100.0")
    )

    # 4. Точка прибутку (Break-even point)
    # Скільки спенду потрібно, щоб комісія (% від спенду) + продажі повністю покрили total_expenses
    remaining_to_cover = max(Decimal("0"), total_expenses - sales_revenue)
    if fee_percent > Decimal("0"):
        breakeven_spend_needed = (remaining_to_cover / (fee_percent / Decimal("100"))).quantize(Decimal("0.01"))
    else:
        breakeven_spend_needed = Decimal("0.00")

    if total_expenses > Decimal("0"):
        breakeven_progress_pct = min(
            Decimal("100.0"),
            ((total_revenue / total_expenses) * Decimal("100")).quantize(Decimal("0.1")),
        )
    else:
        breakeven_progress_pct = Decimal("100.0") if total_revenue > Decimal("0") else Decimal("0.0")

    # 5. Поденний графік + пошук дати виходу в точку беззбитковості
    daily_chart = []
    cum_rev = Decimal("0")
    cum_exp = Decimal("0")
    breakeven_date: str | None = None

    cur = d_from
    while cur <= d_to:
        d_sp = spend_by_day.get(cur, Decimal("0")).quantize(Decimal("0.01"))
        d_rev = ((d_sp * fee_percent / Decimal("100")) + sales_by_day.get(cur, Decimal("0"))).quantize(Decimal("0.01"))
        d_exp = exp_by_day.get(cur, Decimal("0")).quantize(Decimal("0.01"))
        cum_rev += d_rev
        cum_exp += d_exp
        if breakeven_date is None and total_expenses > Decimal("0") and cum_rev >= total_expenses:
            breakeven_date = cur.isoformat()
        daily_chart.append({
            "date": cur.isoformat(),
            "spend": d_sp,
            "revenue": d_rev,
            "expenses": d_exp,
            "cumulative_revenue": cum_rev.quantize(Decimal("0.01")),
            "cumulative_expenses": cum_exp.quantize(Decimal("0.01")),
            "cumulative_profit": (cum_rev - cum_exp).quantize(Decimal("0.01")),
        })
        cur += timedelta(days=1)

    category_breakdown = []
    if include_batches_cost and batches_cost > Decimal("0"):
        pct = ((batches_cost / total_expenses) * Decimal("100")).quantize(Decimal("0.1")) if total_expenses > 0 else Decimal("0")
        category_breakdown.append({
            "category_id": "batches_auto",
            "name": "Партії акаунтів (авто з реєстру)",
            "color": "#eab308",
            "amount": batches_cost,
            "percent": pct,
        })

    for c in cats:
        amt = by_cat_totals.get(c.id, Decimal("0")).quantize(Decimal("0.01"))
        pct = ((amt / total_expenses) * Decimal("100")).quantize(Decimal("0.1")) if total_expenses > 0 else Decimal("0")
        category_breakdown.append({
            "category_id": str(c.id),
            "name": c.name,
            "color": c.color,
            "amount": amt,
            "percent": pct,
        })

    category_breakdown.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "fee_percent": fee_percent,
        "include_batches_cost": include_batches_cost,
        "total_spend": total_spend,
        "commission_revenue": commission_revenue,
        "sales_revenue": sales_revenue,
        "total_revenue": total_revenue,
        "manual_expenses": manual_expenses_total.quantize(Decimal("0.01")),
        "batches_cost": batches_cost,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "breakeven": {
            "spend_needed": breakeven_spend_needed,
            "spend_current": total_spend,
            "spend_remaining": max(Decimal("0.00"), breakeven_spend_needed - total_spend),
            "revenue_needed": total_expenses,
            "revenue_current": total_revenue,
            "progress_pct": breakeven_progress_pct,
            "is_profitable": total_revenue >= total_expenses,
            "surplus_or_deficit": net_profit,
            "reached_at_date": breakeven_date,
        },
        "by_category": category_breakdown,
        "daily_chart": daily_chart,
        "expenses": expense_items,
        "categories": [{"id": str(c.id), "name": c.name, "color": c.color} for c in cats],
    }
