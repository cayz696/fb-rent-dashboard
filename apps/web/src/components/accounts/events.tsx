"use client";
import Link from "next/link";
import { Empty, Mono, StageBadge } from "@/components/ui";
import { OFF_LABEL } from "@/lib/stages";
import type { AccountEvent, OffReason } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

const FIELD_LABEL: Record<string, string> = {
  ad_account_id: "Ad account ID", adspower_profile_id: "Профіль AdsPower", bm_label: "БМ", card_last4: "Карта (last4)",
  timezone: "Часовий пояс", spend_limit: "Ліміт", notes: "Нотатка", supplier_id: "Постачальник", batch_id: "Партія", purchase_cost: "Собівартість",
};

function Body({ e }: { e: AccountEvent }) {
  const p = e.payload as Record<string, any>;
  if (e.type === "created") return <span>Акаунт створено</span>;
  if (e.type === "stage_change") {
    return (
      <span className="flex flex-wrap items-center gap-2">
        {e.from_stage && <StageBadge stage={e.from_stage} />}<span className="text-faint">→</span>
        {e.to_stage && <StageBadge stage={e.to_stage} offReason={p.off_reason as OffReason} />}
        {p.off_reason && <span className="text-muted">{OFF_LABEL[p.off_reason as OffReason]}</span>}
        {p.manual_confirm && <span className="text-[11px] text-faint">ручне підтвердження</span>}
        {p.comment && <span className="text-muted">«{p.comment}»</span>}
      </span>
    );
  }
  if (e.type === "updated") {
    return (
      <span className="text-muted">
        Змінено: {Object.entries(p).map(([k, v]) => `${FIELD_LABEL[k] ?? k}${k === "notes" ? "" : `: ${v.from ?? "—"} → ${v.to ?? "—"}`}`).join("; ")}
      </span>
    );
  }
  return <span className="text-muted">{e.type}</span>;
}

export function EventList({ events, showAccount }: { events: AccountEvent[]; showAccount?: boolean }) {
  if (!events.length) return <Empty>Подій ще немає</Empty>;
  return (
    <ol className="divide-y divide-divider">
      {events.map((e) => (
        <li key={e.id} className="flex items-start gap-4 px-5 py-3.5 text-[13px]">
          <Mono className="w-28 shrink-0 pt-0.5 text-[12px] text-faint">{fmtDateTime(e.created_at)}</Mono>
          {showAccount && (
            <Link href={`/accounts/${e.account_id}`} className="w-20 shrink-0 font-mono font-semibold text-accent hover:text-accent-light">{e.account_code}</Link>
          )}
          <div className="min-w-0 flex-1"><Body e={e} /></div>
          <span className="shrink-0 text-[12px] text-muted">{e.actor_name ?? e.actor}</span>
        </li>
      ))}
    </ol>
  );
}
