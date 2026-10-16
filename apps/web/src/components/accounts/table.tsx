"use client";
import Link from "next/link";
import { Empty, Mono, StageBadge } from "@/components/ui";
import type { Account } from "@/lib/types";
import { fmtDateTime, money, timeLeft } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export function AccountsTable({ items, showCost, selected, onToggle, onToggleAll }: {
  items: Account[]; showCost?: boolean;
  selected?: Set<string>; onToggle?: (id: string) => void; onToggleAll?: () => void;
}) {
  if (!items.length) return <Empty>Акаунтів за цим фільтром немає</Empty>;
  const selectable = !!selected && !!onToggle;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-divider bg-inset/50">
            {selectable && (
              <th className="w-10 pl-5">
                <input type="checkbox" aria-label="Обрати всі" className="accent-[var(--accent)]"
                  checked={items.length > 0 && items.every((a) => selected!.has(a.id))} onChange={onToggleAll} />
              </th>
            )}
            <th className={th}>Код</th><th className={th}>Клієнт</th><th className={th}>Етап</th>
            <th className={th}>Постачальник</th><th className={th}>Сьогодні</th><th className={th}>Ліміт</th><th className={th}>Оголошення</th><th className={th}>Загалом</th>
            {showCost && <th className={th}>Собівартість</th>}
            <th className={th}>Оновлено</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-b border-divider transition last:border-0 hover:bg-surface-hover">
              {selectable && (
                <td className="w-10 pl-5">
                  <input type="checkbox" aria-label={`Обрати ${a.code}`} className="accent-[var(--accent)]" checked={selected!.has(a.id)} onChange={() => onToggle!(a.id)} />
                </td>
              )}
              <td className="whitespace-nowrap px-5 py-3.5">
                <Link href={`/accounts/${a.id}`} className="font-mono font-semibold text-accent hover:text-accent-light">{a.code}</Link>
              </td>
              <td className="px-5 py-3.5">{a.client_name ?? <span className="text-faint">—</span>}</td>
              <td className="px-5 py-3.5">
                <StageBadge stage={a.stage} offReason={a.off_reason} />
                {a.stage === "checking" && a.check_until && <Mono className="ml-2 text-[11px] text-[var(--stage-check-fg)]">{timeLeft(a.check_until)}</Mono>}
              </td>
              <td className="px-5 py-3.5 text-muted">{a.supplier_name ?? "—"}</td>
              <td className="px-5 py-3.5 font-mono">{a.spend_today !== null ? money(a.spend_today) : <span className="text-faint">—</span>}</td>
              <td className="px-5 py-3.5 font-mono text-muted">{a.spend_limit ? money(a.spend_limit) : <span className="text-faint">—</span>}</td>
              <td className="whitespace-nowrap px-5 py-3.5 font-mono">
                {a.ads_active === null ? <span className="text-faint">—</span> : <>{a.ads_active}{!!a.ads_issues && <span className="ml-2 rounded bg-[var(--danger-bg)] px-1.5 py-0.5 text-[11px] text-[var(--stage-off-fg)]">+{a.ads_issues} err</span>}</>}
              </td>
              <td className="px-5 py-3.5 font-mono text-muted">{a.spend_total !== null ? money(a.spend_total) : <span className="text-faint">—</span>}</td>
              {showCost && <td className="px-5 py-3.5 font-mono text-muted">{money(a.purchase_cost)}</td>}
              <td className="whitespace-nowrap px-5 py-3.5 font-mono text-[12px] text-muted">{fmtDateTime(a.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
