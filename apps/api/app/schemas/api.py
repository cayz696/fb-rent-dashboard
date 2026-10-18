import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OffReason, RequestStatus, Role, Stage


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    step: str  # totp_required | totp_setup
    pre_token: str


class TotpSetupOut(BaseModel):
    secret: str
    uri: str


class TotpVerifyIn(BaseModel):
    pre_token: str
    code: str


class UserOut(ORM):
    id: uuid.UUID
    username: str
    name: str
    role: Role
    allowed_sections: list[str] | None = None


# ---- suppliers / batches / clients
class SupplierIn(BaseModel):
    name: str = Field(min_length=1)
    contact: str | None = None
    notes: str | None = None


class SupplierOut(ORM, SupplierIn):
    id: uuid.UUID


class BatchIn(BaseModel):
    supplier_id: uuid.UUID
    qty: int = Field(ge=1, le=1000)
    unit_cost: Decimal = Field(ge=0)
    bought_at: date | None = None
    create_accounts: bool = True


class BatchOut(ORM):
    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    qty: int
    unit_cost: Decimal | None = None
    bought_at: date
    accounts_total: int = 0
    accounts_off: int = 0


class ClientIn(BaseModel):
    name: str = Field(min_length=1)
    telegram_chat_id: int | None = None
    telegram_usernames: list[str] = []
    terms: str | None = None
    bm_id: str | None = None
    fee_percent: Decimal | None = Field(default=None, ge=0, le=100)
    balance: Decimal = Decimal(0)
    status: str = "active"
    notes: str | None = None


class ClientOut(ORM, ClientIn):
    id: uuid.UUID
    accounts_issued: int = 0
    current_balance: Decimal | None = None


# ---- accounts
class AccountCreate(BaseModel):
    supplier_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    purchase_cost: Decimal | None = None
    notes: str | None = None


class AccountPatch(BaseModel):
    supplier_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    purchase_cost: Decimal | None = None
    adspower_profile_id: str | None = None
    ad_account_id: str | None = None
    bm_label: str | None = None
    card_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    timezone: str | None = None
    spend_limit: Decimal | None = None
    notes: str | None = None


class AccountOut(ORM):
    id: uuid.UUID
    code: str
    stage: Stage
    off_reason: OffReason | None
    supplier_id: uuid.UUID | None
    supplier_name: str | None = None
    batch_id: uuid.UUID | None
    purchase_cost: Decimal | None
    client_id: uuid.UUID | None
    client_name: str | None = None
    adspower_profile_id: str | None
    ad_account_id: str | None
    fb_user_id: str | None
    fb_login: str | None
    fb_link: str | None
    country: str | None
    adspower_group: str | None
    bm_label: str | None
    card_last4: str | None
    timezone: str | None
    spend_limit: Decimal | None
    check_until: datetime | None
    ready_at: datetime | None
    sold_to: str | None
    sale_price: Decimal | None
    sold_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    next_stages: list[Stage] = []
    spend_today: Decimal | None = None
    spend_total: Decimal | None = None
    ads_active: int | None = None
    ads_issues: int | None = None
    card_fbm_id: str | None = None
    card_name: str | None = None
    card_status: str | None = None
    card_spend: Decimal | None = None
    card_balance: Decimal | None = None
    card_currency: str | None = None


class AccountList(BaseModel):
    items: list[AccountOut]
    total: int


class TransitionIn(BaseModel):
    to: Stage
    off_reason: OffReason | None = None
    comment: str | None = None
    client_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None
    confirm_manual: bool = False
    sold_to: str | None = None
    sale_price: Decimal | None = None


class EventOut(ORM):
    id: int
    account_id: uuid.UUID
    account_code: str | None = None
    type: str
    from_stage: Stage | None
    to_stage: Stage | None
    payload: dict
    actor: str
    actor_name: str | None = None
    created_at: datetime


class SignalOut(BaseModel):
    type: str
    severity: str
    account_id: uuid.UUID | None
    code: str | None
    message: str


class DashboardOut(BaseModel):
    spend_today: Decimal | None
    issued: int
    pool_total: int
    ready: int
    requests_queue: int
    requests_pending_approval: int
    funnel: dict[str, int]
    off_breakdown: dict[str, int]
    signals_count: int
    clover_last_received: datetime | None = None
    fbm_spend_today: Decimal | None = None
    fbm_spend_total: Decimal | None = None


# ---- users (admin)
class UserAdminOut(ORM):
    id: uuid.UUID
    username: str
    name: str
    role: Role
    is_active: bool
    totp_enabled: bool
    allowed_sections: list[str] | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1)
    role: Role
    password: str = Field(min_length=8)
    allowed_sections: list[str] | None = None


class UserPatch(BaseModel):
    name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)
    reset_2fa: bool = False
    allowed_sections: list[str] | None = None


# ---- requests
class RequestCreate(BaseModel):
    client_id: uuid.UUID
    raw_text: str = Field(min_length=1)
    qty: int = Field(ge=1, le=100)
    limit: Decimal | None = Field(default=None, ge=0)
    geo: str | None = None


class ProposedAccount(BaseModel):
    id: uuid.UUID
    code: str
    stage: Stage


class RequestOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None
    raw_text: str
    message_link: str | None
    parsed: dict | None
    status: RequestStatus
    proposed: list[ProposedAccount]
    approved_by_name: str | None
    created_at: datetime


class ProposedIn(BaseModel):
    account_ids: list[uuid.UUID]


# ---- clover
class LinkIn(BaseModel):
    ad_account_id: str
    account_id: uuid.UUID


class UnmatchedOut(BaseModel):
    ad_account_id: str
    spend_today: Decimal | None
    spend_total: Decimal | None
    snapshots: int
    last_received: datetime


class SpendPoint(BaseModel):
    date: str
    spend: Decimal | None


class CloverStatus(BaseModel):
    last_received: datetime | None
    stale: bool
    snapshots: int
    unmatched: int


# ---- finance
class PaymentIn(BaseModel):
    amount: Decimal
    paid_at: date | None = None
    note: str | None = None


class PaymentOut(ORM):
    id: uuid.UUID
    amount: Decimal
    paid_at: date
    note: str | None
    created_by_name: str | None = None
    created_at: datetime


class FinanceAccountRow(BaseModel):
    id: uuid.UUID
    code: str
    stage: Stage
    spend_total: Decimal
    accrued: Decimal


class ClientReport(BaseModel):
    client_id: uuid.UUID
    client_name: str
    fee_percent: Decimal
    accounts_active: int
    spend_total: Decimal
    accrued: Decimal
    initial_balance: Decimal
    paid: Decimal
    balance: Decimal
    accounts: list[FinanceAccountRow]


class FinanceClientRow(BaseModel):
    client_id: uuid.UUID
    client_name: str
    fee_percent: Decimal
    accounts_active: int
    spend_total: Decimal
    accrued: Decimal
    balance: Decimal


class FinanceOverview(BaseModel):
    clients: list[FinanceClientRow]
    total_spend: Decimal
    total_accrued: Decimal
    issued_cost: Decimal
    pool_cost: Decimal
    written_off_cost: Decimal
    sales_revenue: Decimal
    sales_count: int
    margin: Decimal
    clover_connected: bool


# ---- import order → AdsPower
class ImportPreviewRow(BaseModel):
    name: str
    fb_user_id: str
    fb_login: str
    country: str
    twofa_ok: bool
    warnings: list[str]
    duplicate: bool


class ImportPreview(BaseModel):
    total: int
    new: int
    duplicates: int
    rows: list[ImportPreviewRow]


class ImportResult(BaseModel):
    created: int
    skipped_duplicates: int
    codes: list[str]
    queued_to_bridge: int = 0
    adspower_file: str          # вміст файлу для масового імпорту AdsPower (містить секрети — не зберігається на сервері)
    filename: str
