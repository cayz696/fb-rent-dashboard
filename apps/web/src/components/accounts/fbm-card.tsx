"use client";
import { CreditCard, KeyRound } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Card, CardHeader, Empty, Modal } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { Account, FbmCode } from "@/lib/types";
import { fmtDateTime, money } from "@/lib/utils";

const statusColor = (s: string | null) =>
  s === "VALID CARD" ? "var(--success)" : s?.includes("BLOCK") ? "var(--stage-off-fg)" : "var(--warning)";

export function AccountFbmCard({ acc }: { acc: Account }) {
  const [codes, setCodes] = useState(false);
  if (!acc.card_last4) {
    return (
      <Card>
        <CardHeader title="Картка" icon={<CreditCard size={16} />} />
        <div className="px-5 py-6 text-center text-[13px] text-muted">Впишіть last4 картки (у «Прив'язки й дані»), щоб побачити спенд, статус і 3DS-коди з FBM.</div>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title="Картка FBM" icon={<CreditCard size={16} />}
        right={acc.card_fbm_id && <button onClick={() => setCodes(true)} className="inline-flex items-center gap-1 rounded-md border border-line-strong bg-surface-hover px-2 py-1 text-[11px] text-muted hover:text-main cursor-pointer"><KeyRound size={12} />3DS-коди</button>} />
      {!acc.card_fbm_id ? (
        <div className="px-5 py-6 text-[13px] text-muted">Картку •• {acc.card_last4} не знайдено у знімку FBM. Оновіть «Картки» або перевірте last4.</div>
      ) : (
        <div className="grid grid-cols-2 gap-px bg-divider">
          {[["Картка", `•• ${acc.card_last4}`], ["Статус", acc.card_status ?? "—"], ["Спенд", acc.card_spend !== null ? money(acc.card_spend) : "—"], ["Баланс рахунку", acc.card_balance !== null ? money(acc.card_balance) : "—"]].map(([l, v]) => (
            <div key={l} className="bg-surface px-5 py-3">
              <div className="text-[11px] uppercase tracking-wider text-faint">{l}</div>
              <div className="mt-1 font-mono text-[15px]" style={{ color: l === "Статус" ? statusColor(acc.card_status) : undefined }}>{v}</div>
            </div>
          ))}
          <div className="col-span-2 bg-surface px-5 py-2 text-[12px] text-muted">{acc.card_name}</div>
        </div>
      )}
      {codes && acc.card_fbm_id && <CodesModal cardId={acc.card_fbm_id} last4={acc.card_last4} onClose={() => setCodes(false)} />}
    </Card>
  );
}

function CodesModal({ cardId, last4, onClose }: { cardId: string; last4: string | null; onClose: () => void }) {
  const { data, isLoading } = useSWR<FbmCode[]>(`/api/fbm/cards/${cardId}/codes`, fetcher, { refreshInterval: 15000 });
  return (
    <Modal title={`3DS-коди · •• ${last4 ?? ""}`} onClose={onClose}>
      {isLoading ? <p className="py-6 text-center text-muted">Завантаження…</p>
        : !data?.length ? <Empty>Кодів ще немає</Empty>
        : <ul className="divide-y divide-divider">
            {data.map((c, i) => (
              <li key={i} className="flex items-center justify-between py-2.5">
                <button onClick={() => c.code && navigator.clipboard?.writeText(c.code)} className="font-mono text-[18px] font-bold text-accent hover:text-accent-light cursor-pointer" title="Копіювати">{c.code ?? "—"}</button>
                <span className="font-mono text-[11px] text-faint">{c.at ? fmtDateTime(c.at) : ""}</span>
              </li>
            ))}
          </ul>}
    </Modal>
  );
}
