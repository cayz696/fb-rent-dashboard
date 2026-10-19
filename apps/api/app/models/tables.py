from typing import Optional, List, Dict, Any
from __future__ import annotations
"""Усі таблиці з розділу 4 ТЗ. Заборонено зберігати повні номери карт, паролі, cookies, TOTP-секрети акаунтів FB."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Identity, Integer, Numeric,
    Sequence, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import CommandStatus, OffReason, RequestStatus, Role, Stage

account_code_seq = Sequence("account_code_seq")


def pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.viewer)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    allowed_sections: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = ts()


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(128))
    contact: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[uuid.UUID] = pk()
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    qty: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    bought_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    supplier: Mapped[Supplier] = relationship()


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(128))
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    telegram_usernames: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    terms: Mapped[Optional[str]] = mapped_column(Text)
    bm_id: Mapped[Optional[str]] = mapped_column(String(64))  # Business Manager ID клієнта (для розшарювання доступу)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # початковий залишок; поточний баланс = він + оплати − нараховане
    fee_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # % від спенду, який клієнт платить нам
    status: Mapped[str] = mapped_column(String(32), default="active")
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = pk()
    code: Mapped[str] = mapped_column(
        String(16), unique=True,
        server_default=text("'FB-' || lpad(nextval('account_code_seq')::text, 4, '0')"),
    )
    stage: Mapped[Stage] = mapped_column(Enum(Stage, name="stage"), default=Stage.purchased, index=True)
    off_reason: Mapped[Optional[OffReason]] = mapped_column(Enum(OffReason, name="off_reason"))
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("suppliers.id"))
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("batches.id"))
    purchase_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("clients.id"))
    adspower_profile_id: Mapped[Optional[str]] = mapped_column(Text)
    ad_account_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
    fb_user_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # 615... (публічний id, не секрет)
    fb_login: Mapped[Optional[str]] = mapped_column(Text)                        # пошта-логін (ідентифікатор)
    fb_link: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[Optional[str]] = mapped_column(String(8))
    adspower_group: Mapped[Optional[str]] = mapped_column(Text)  # поточна група в AdsPower (дзеркало)
    bm_label: Mapped[Optional[str]] = mapped_column(Text)
    card_last4: Mapped[Optional[str]] = mapped_column(String(4))
    timezone: Mapped[Optional[str]] = mapped_column(Text)
    spend_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    check_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sold_to: Mapped[Optional[str]] = mapped_column(Text)
    sale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier: Mapped[Optional[Supplier]] = relationship()
    client: Mapped[Optional[Client]] = relationship()
    batch: Mapped[Optional[Batch]] = relationship()


class AccountEvent(Base):
    """Журнал: тільки вставка."""
    __tablename__ = "account_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    type: Mapped[str] = mapped_column(String(48))
    from_stage: Mapped[Optional[Stage]] = mapped_column(Enum(Stage, name="stage"))
    to_stage: Mapped[Optional[Stage]] = mapped_column(Enum(Stage, name="stage"))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor: Mapped[str] = mapped_column(String(64))  # user_id | clover | bridge | agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("clients.id"))
    raw_text: Mapped[str] = mapped_column(Text)
    message_link: Mapped[Optional[str]] = mapped_column(Text)
    parsed: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus, name="request_status"), default=RequestStatus.new)
    proposed_account_ids: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = ts()


class SpendSnapshot(Base):
    __tablename__ = "spend_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ad_account_id: Mapped[str] = mapped_column(Text, index=True)
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("accounts.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    spend_today: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    spend_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    spend_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    ads_active: Mapped[Optional[int]] = mapped_column(Integer)
    ads_issues: Mapped[Optional[int]] = mapped_column(Integer)
    status_raw: Mapped[Optional[str]] = mapped_column(Text)
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BridgeCommand(Base):
    __tablename__ = "bridge_commands"
    id: Mapped[uuid.UUID] = pk()
    command: Mapped[str] = mapped_column(String(48))
    args: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[CommandStatus] = mapped_column(Enum(CommandStatus, name="command_status"), default=CommandStatus.pending)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SystemState(Base):
    """Ключ-значення для службового стану (напр. останній сигнал від bridge)."""
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ClientPayment(Base):
    """Оплати клієнтів (передоплата, коригування). Записи не видаляються: помилка виправляється від'ємним записом."""
    __tablename__ = "client_payments"
    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class Team(Base):
    """Команда баєрів та її прив'язана Google-таблиця."""
    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    sheet_url: Mapped[Optional[str]] = mapped_column(Text)
    sheet_gid: Mapped[Optional[str]] = mapped_column(String(32))
    sheet_webhook_url: Mapped[Optional[str]] = mapped_column(Text)
    sheet_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    topup_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    spend_total_sheet: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("7.00"), server_default=text("7.00"))
    last_sheet_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts()


class Buyer(Base):
    """Юзер (баєр) без дублів, прив'язаний до команди та карток FBM."""
    __tablename__ = "buyers"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("teams.id"), index=True)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    fbm_owner: Mapped[Optional[str]] = mapped_column(String(128))
    accounts_count: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts()

    team: Mapped[Optional[Team]] = relationship()


class CardSpendLog(Base):
    """Історія фіксацій спенду по картках FBM кожні 3–4 години."""
    __tablename__ = "card_spend_logs"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    card_id: Mapped[str] = mapped_column(String(64), index=True)
    last4: Mapped[Optional[str]] = mapped_column(String(8))
    card_name: Mapped[Optional[str]] = mapped_column(Text)
    buyer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("buyers.id"), index=True)
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("teams.id"), index=True)
    account_name: Mapped[Optional[str]] = mapped_column(String(64))
    account_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    spend_cumulative: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    spend_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    date: Mapped[date] = mapped_column(Date, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BuyerDailySpend(Base):
    """Поденний спенд юзера (зафіксована дельта з FBM + значення з Google-таблиці)."""
    __tablename__ = "buyer_daily_spends"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buyers.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    spend_fbm: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    spend_sheet: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FbmReconciliation(Base):
    """Добова звірка розбіжностей сум у БД з кабінетом FBM Cards."""
    __tablename__ = "fbm_reconciliations"
    id: Mapped[uuid.UUID] = pk()
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")  # ok | discrepancy
    db_total_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    fbm_total_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    diff_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    discrepancies: Mapped[List[Any]] = mapped_column(JSONB, default=list)


class ExpenseCategory(Base):
    """Категорії витрат для розділу Звітність (Отчетность)."""
    __tablename__ = "expense_categories"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    color: Mapped[str] = mapped_column(String(32), default="#f59e0b")
    created_at: Mapped[datetime] = ts()


class Expense(Base):
    """Записи витрат по категоріях."""
    __tablename__ = "expenses"
    id: Mapped[uuid.UUID] = pk()
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    spent_at: Mapped[date] = mapped_column(Date, server_default=func.current_date(), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()

    category: Mapped[ExpenseCategory] = relationship()

