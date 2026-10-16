"use client";
import { AlertCircle, CircleDollarSign, Landmark, Tag, TrendingUp, Wallet } from "lucide-react";
import Link from "next/link";
import { type ReactNode } from "react";
import useSWR from "swr";
import { Card, CardHeader, Empty, PageHeader } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/session";
import type { FinanceOverview } from "@/lib/types";
import { money } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

function Kpi({ label, value, icon, tone }: { label: string; value: string; icon: ReactNode; tone?: string }) {
  return (
    <div className="panel kpi-glow p-5">
      <div className="flex items-center justify-between text-[13px] text-muted">{label}<span className="text-accent">{icon}</span></div>
      <div className="mt-2 font-mono text-[26px] font-bold" style={{ color: tone }}>{value}</div>
    </div>
  );
}

export default function FinancePage() {
  const { user } = useMe();
  const { data } = useSWR<FinanceOverview>(isAdmin(user) ? "/api/finance" : null, fetcher, { refreshInterval: 30000 });

  if (user && !isAdmin(user)) return <><PageHeader title="Фінанси" /><div className="panel"><Empty>Розділ доступний лише адміну.</Empty></div></>;
  if (!data) return <><PageHeader title="Фінанси" /><p className="text-muted">Завантаження…</p></>;

  return (
    <>
      <PageHeader title="Фінанси" sub="Оренда: нарахування = спенд картки (FBM) × % клієнта. Продаж: виручка за продані акаунти. Маржа = нараховано + продажі − собівартість." />
      {!data.clover_connected && (
        <p className="mb-5 flex items-center gap-2 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-4 py-3 text-[13px] text-warning">
          <AlertCircle size={16} />Немає даних FBM — спенд порожній. Оновіть «Картки» і проставте last4 карток в акаунтах, щоб нарахування рахувались.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
        <Kpi label="Спенд клієнтів" value={money(data.total_spend)} icon={<CircleDollarSign size={17} />} />
        <Kpi label="Нараховано клієнтам" value={money(data.total_accrued)} icon={<Wallet size={17} />} />
        <Kpi label="Собівартість пулу" value={money(data.pool_cost)} icon={<Landmark size={17} />} />
        <Kpi label="Продажі" value={`${money(data.sales_revenue)}${data.sales_count ? ` · ${data.sales_count} шт` : ""}`} icon={<Tag size={17} />} />
        <Kpi label="Маржа" value={money(data.margin)} icon={<TrendingUp size={17} />} tone={Number(data.margin) < 0 ? "var(--stage-off-fg)" : "var(--success)"} />
      </div>

      <Card className="mt-5">
        <CardHeader title="По клієнтах" />
        {!data.clients.length ? <Empty>Клієнтів ще немає</Empty> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-divider bg-inset/50">
              <th className={th}>Клієнт</th><th className={th}>%</th><th className={th}>Активні</th><th className={th}>Спенд</th><th className={th}>Нараховано</th><th className={th}>Баланс</th>
            </tr></thead>
            <tbody>
              {data.clients.map((c) => (
                <tr key={c.client_id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                  <td className="px-5 py-3.5"><Link href={`/clients/${c.client_id}`} className="font-semibold text-main hover:text-accent">{c.client_name}</Link></td>
                  <td className="px-5 py-3.5 font-mono text-muted">{Number(c.fee_percent) ? `${Number(c.fee_percent)}%` : "—"}</td>
                  <td className="px-5 py-3.5 font-mono">{c.accounts_active}</td>
                  <td className="px-5 py-3.5 font-mono">{money(c.spend_total)}</td>
                  <td className="px-5 py-3.5 font-mono">{money(c.accrued)}</td>
                  <td className="px-5 py-3.5 font-mono font-semibold" style={{ color: Number(c.balance) < 0 ? "var(--stage-off-fg)" : "var(--success)" }}>{money(c.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <p className="mt-4 text-[12px] text-faint">Від'ємний баланс = клієнт винен нам. Умови нарахування узгоджуються з власником (ТЗ §12) — поточна модель: % від спенду.</p>
    </>
  );
}
