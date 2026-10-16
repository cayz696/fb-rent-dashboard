export type Stage =
  | "purchased" | "in_adspower" | "bm_created" | "phone_linked" | "warmup" | "card_linked"
  | "checking" | "ready" | "issued" | "sold" | "returned" | "off";
export type OffReason = "ban" | "reserve" | "paused" | "returned" | "written_off";
export type Role = "admin" | "operator" | "viewer";

export interface User { id: string; username: string; name: string; role: Role; allowed_sections?: string[] | null }

export interface Account {
  id: string; code: string; stage: Stage; off_reason: OffReason | null;
  supplier_id: string | null; supplier_name: string | null; batch_id: string | null;
  purchase_cost: string | null; client_id: string | null; client_name: string | null;
  adspower_profile_id: string | null; ad_account_id: string | null; bm_label: string | null;
  card_last4: string | null; timezone: string | null; spend_limit: string | null; adspower_group: string | null;
  check_until: string | null; ready_at: string | null; sold_to: string | null; sale_price: string | null; sold_at: string | null; notes: string | null;
  created_at: string; updated_at: string; next_stages: Stage[];
  fb_user_id: string | null; fb_login: string | null; fb_link: string | null; country: string | null;
  spend_today: string | null; spend_total: string | null; ads_active: number | null; ads_issues: number | null;
  card_fbm_id: string | null; card_name: string | null; card_status: string | null; card_spend: string | null; card_balance: string | null; card_currency: string | null;
}
export interface AccountList { items: Account[]; total: number }

export interface AccountEvent {
  id: number; account_id: string; account_code: string | null; type: string;
  from_stage: Stage | null; to_stage: Stage | null; payload: Record<string, unknown>;
  actor: string; actor_name: string | null; created_at: string;
}

export interface Client {
  id: string; name: string; telegram_chat_id: number | null; telegram_usernames: string[];
  terms: string | null; bm_id: string | null; fee_percent: string | null; balance: string; status: string; notes: string | null; accounts_issued: number; current_balance: string | null;
}
export interface Supplier { id: string; name: string; contact: string | null; notes: string | null }
export interface Batch {
  id: string; supplier_id: string; supplier_name: string | null; qty: number;
  unit_cost: string | null; bought_at: string; accounts_total: number; accounts_off: number;
}
export interface Dashboard {
  spend_today: string | null; issued: number; pool_total: number; ready: number;
  requests_queue: number; requests_pending_approval: number;
  funnel: Record<Stage, number>; off_breakdown: Record<OffReason, number>; signals_count: number; clover_last_received: string | null;
}
export interface Signal { type: string; severity: string; account_id: string | null; code: string | null; message: string }

export type RequestStatus = "new" | "proposed" | "approved" | "rejected" | "done";
export interface RequestItem {
  id: string; client_id: string | null; client_name: string | null; raw_text: string; message_link: string | null;
  parsed: { qty?: number; geo?: string | null; limit?: string | null; shortage?: number; source?: string } | null;
  status: RequestStatus; proposed: { id: string; code: string; stage: Stage }[]; approved_by_name: string | null; created_at: string;
}
export interface UserAdmin { id: string; username: string; name: string; role: Role; is_active: boolean; totp_enabled: boolean; allowed_sections?: string[] | null; created_at: string }
export interface Unmatched { ad_account_id: string; spend_today: string | null; spend_total: string | null; snapshots: number; last_received: string }
export interface CloverStatus { last_received: string | null; stale: boolean; snapshots: number; unmatched: number }
export interface SpendPoint { date: string; spend: string | null }
export interface BridgeStatus { online: boolean; last_seen: string | null; pending: number }
export interface BridgeCommand {
  id: string; command: string; args: Record<string, string>; status: "pending" | "sent" | "ok" | "error";
  result: Record<string, unknown> | null; created_by_name: string | null; created_at: string; done_at: string | null;
}

export interface Payment { id: string; amount: string; paid_at: string; note: string | null; created_by_name: string | null; created_at: string }
export interface FinanceAccountRow { id: string; code: string; stage: Stage; spend_total: string; accrued: string }
export interface ClientReport {
  client_id: string; client_name: string; fee_percent: string; accounts_active: number;
  spend_total: string; accrued: string; initial_balance: string; paid: string; balance: string; accounts: FinanceAccountRow[];
}
export interface FinanceClientRow { client_id: string; client_name: string; fee_percent: string; accounts_active: number; spend_total: string; accrued: string; balance: string }
export interface FinanceOverview {
  clients: FinanceClientRow[]; total_spend: string; total_accrued: string;
  issued_cost: string; pool_cost: string; written_off_cost: string; sales_revenue: string; sales_count: number; margin: string; clover_connected: boolean;
}

export interface ImportPreviewRow { name: string; fb_user_id: string; fb_login: string; country: string; twofa_ok: boolean; warnings: string[]; duplicate: boolean }
export interface ImportPreview { total: number; new: number; duplicates: number; rows: ImportPreviewRow[] }
export interface ImportResult { created: number; skipped_duplicates: number; codes: string[]; queued_to_bridge: number; adspower_file: string; filename: string }

export interface SyncProfile { profile_id: string | null; serial: string | null; name: string | null; group_name: string | null; username: string | null; country: string | null; fb_user_id: string | null; linked_code: string | null; linked_stage: string | null }
export interface SyncView { last_sync: string | null; total: number; linked: number; unlinked: number; by_group: Record<string, number>; profiles: SyncProfile[]; pending: boolean }
export interface AdsImportResult { created: number; updated_group: number; skipped: number; by_stage: Record<string, number> }

export interface FbmCard { card_id: string; last4: string | null; name: string | null; status: string | null; payment_system: string | null; spend: string | null; currency: string | null; owner: string | null; account_name: string | null; account_balance: string | null; linked_code: string | null }
export interface FbmCards { configured: boolean; last_sync: string | null; total: number; total_spend: string; by_status: Record<string, number>; by_account: Record<string, number>; cards: FbmCard[] }
export interface FbmCode { code: string | null; type: string | null; at: string | null; description: string | null }

export interface FbmAccountBalance {
  account_name: string; balance: string | null; currency: string; cards_count: number;
  total_spend: string; low_balance: boolean; negative_balance: boolean;
}
export interface TeamItem {
  id: string; name: string; sheet_url: string | null; sheet_gid: string | null;
  sheet_balance: string | null; topup_total: string | null; spend_total_sheet: string | null;
  spend_total_fbm: string; fee_percent: string; buyers_count: number;
  last_sheet_sync: string | null; low_balance: boolean; negative_balance: boolean; notes: string | null;
}
export interface BuyerCardItem {
  card_id: string; last4: string | null; name: string | null; status: string | null;
  spend: string; owner: string | null; account_name: string | null; account_balance: string | null; currency: string;
}
export interface BuyerItem {
  id: string; name: string; team_id: string | null; team_name: string | null;
  is_priority: boolean; fbm_owner: string | null; accounts_count: number; cards_count: number;
  spend_today: string; spend_month: string; spend_total: string; spend_sheet: string;
  notes: string | null; cards: BuyerCardItem[];
}
export interface FbmReconciliationInfo {
  id: string; checked_at: string; status: "ok" | "discrepancy";
  db_total_spend: string; fbm_total_spend: string; diff_amount: string;
  discrepancies: { card_id: string; last4: string | null; card_name: string | null; db_spend: string; fbm_spend: string; diff: string; reason: string }[];
}
export interface BuyersOverview {
  fbm_accounts: FbmAccountBalance[];
  teams: TeamItem[];
  buyers: BuyerItem[];
  tracker: { last_recorded_at: string; cards_logged: number; total_delta: string } | null;
  reconciliation: FbmReconciliationInfo | null;
}
export interface BuyerDetail {
  id: string; name: string; team_id: string | null; team_name: string | null;
  team_sheet_balance: string | null; is_priority: boolean; fbm_owner: string | null;
  accounts_count: number; notes: string | null; date_from: string; date_to: string;
  period_spend: string; period_spend_sheet: string; lifetime_spend_fbm: string;
  cards: BuyerCardItem[]; fbm_accounts: FbmAccountBalance[];
  daily_series: { date: string; spend_fbm: string; spend_sheet: string | null; spend: string }[];
  recent_logs: { id: number; card_id: string; last4: string | null; card_name: string | null; spend_cumulative: string; spend_delta: string; account_name: string | null; account_balance: string | null; recorded_at: string }[];
}
export interface ExpenseCategoryItem { id: string; name: string; color: string }
export interface ExpenseItem {
  id: string; category_id: string; category_name: string; category_color: string;
  amount: string; spent_at: string; description: string | null; created_by: string;
}
export interface ReportSummary {
  date_from: string; date_to: string; fee_percent: string; include_batches_cost: boolean;
  total_spend: string; commission_revenue: string; sales_revenue: string; total_revenue: string;
  manual_expenses: string; batches_cost: string; total_expenses: string;
  net_profit: string; roi_percent: string;
  breakeven: {
    spend_needed: string; spend_current: string; spend_remaining: string;
    revenue_needed: string; revenue_current: string; progress_pct: string;
    is_profitable: boolean; surplus_or_deficit: string; reached_at_date: string | null;
  };
  by_category: { category_id: string; name: string; color: string; amount: string; percent: string }[];
  daily_chart: { date: string; spend: string; revenue: string; expenses: string; cumulative_revenue: string; cumulative_expenses: string; cumulative_profit: string }[];
  expenses: ExpenseItem[];
  categories: ExpenseCategoryItem[];
}
export interface SystemStatus {
  git_initialized: boolean; commit: string; branch: string; remote_url: string;
  last_commit_msg: string; behind_count: number;
  auto_sync_interval_hours: number; reconcile_interval_hours: number;
  last_spend_snapshot: string | null;
}
