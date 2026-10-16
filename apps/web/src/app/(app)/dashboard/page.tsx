"use client";
import { Bell, CheckCircle2, CircleDollarSign, Filter, MessageSquare, Plus, Search, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { AccountsTable } from "@/components/accounts/table";
import { RequestCard } from "@/components/requests/request-card";
import { Card, CardHeader, Chip, Empty, Input, PageHeader } from "@/components/ui";
import { fetcher, qs } from "@/lib/api";
import { canWrite, isAdmin, useMe } from "@/lib/session";
import { FLOW, OFF_LABEL, STAGE_SHORT } from "@/lib/stages";
import type { AccountList, Dashboard, RequestItem, Signal, Stage } from "@/lib/types";
import { cn, money } from "@/lib/utils";

type Tab = "all" | "issued" | "ready" | "signals";

function Kpi({ label, icon, children, foot }: { label: string; icon: ReactNode; children: ReactNode; foot: ReactNode }) {
  return (
    <div className="panel kpi-glow flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between text-[13px] text-muted">
        {label}
        <span className="grid size-8 place-items-center rounded-md border border-line-strong bg-surface-hover text-accent">{icon}</span>
      </div>
      <div className="flex items-baseline gap-3">{children}</div>
      <div className="text-[12px] text-faint">{foot}</div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useMe();
  const { data: d } = useSWR<Dashboard>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const [tab, setTab] = useState<Tab>("all");
  const [stageFilter, setStageFilter] = useState<Stage | null>(null);
  const [q, setQ] = useState("");

  const params = { stage: stageFilter ? [stageFilter] : tab === "issued" ? ["issued"] : tab === "ready" ? ["ready"] : [], signal: tab === "signals", q, limit: "12" };
  const { data: reqs, mutate: mutReqs } = useSWR<RequestItem[]>("/api/requests?status=new&status=proposed&limit=5", fetcher, { refreshInterval: 20000 });
  const { data: signals } = useSWR<Signal[]>("/api/signals", fetcher, { refreshInterval: 30000 });
  const refreshAll = () => { mutReqs(); globalMutate("/api/dashboard"); globalMutate((k) => typeof k === "string" && k.startsWith("/api/accounts")); };
  const { data: list } = useSWR<AccountList>(`/api/accounts${qs(params)}`, fetcher, { keepPreviousData: true });

  const today = new Date().toLocaleDateString("uk-UA", { weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Kyiv" });
  const offTotal = d ? Object.values(d.off_breakdown).reduce((a, b) => a + b, 0) : 0;
  const util = d && d.pool_total ? ((d.issued / d.pool_total) * 100).toFixed(1) : "0";

  return (
    <>
      <PageHeader
        title="Панель керування"
        sub={today.charAt(0).toUpperCase() + today.slice(1)}
        right={
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
              <Input className="w-72 pl-9" placeholder="Пошук кабінету, клієнта, ID…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <Link href="/suppliers?new=batch" className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-[13px] font-semibold text-on-accent shadow-[0_0_16px_var(--accent-glow)] hover:bg-accent-light">
              <Plus size={15} />Додати партію
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi label="Спенд сьогодні" icon={<CircleDollarSign size={16} />} foot={d?.clover_last_received ? "дані з Clover" : "Clover ще не надсилав дані"}>
          <span className="font-mono text-[32px] font-bold">{d?.spend_today ? money(d.spend_today) : "—"}</span>
        </Kpi>
        <Kpi label="Видані / Всього в пулі" icon={<CheckCircle2 size={16} />} foot={`${util}% утилізація пулу`}>
          <span className="font-mono text-[32px] font-bold">{d?.issued ?? "…"}</span>
          <span className="font-mono text-[18px] text-faint">/ {d?.pool_total ?? "…"}</span>
        </Kpi>
        <Kpi label="Готові до видачі" icon={<ShieldCheck size={16} />} foot="пройшли перевірку 24г">
          <span className="font-mono text-[32px] font-bold">{d?.ready ?? "…"}</span>
          <span className="font-semibold text-info">кабінетів</span>
        </Kpi>
        <Kpi label="Заявки в черзі" icon={<MessageSquare size={16} />} foot="відкриті заявки на видачу">
          <span className="font-mono text-[32px] font-bold">{d?.requests_queue ?? "…"}</span>
          {!!d?.requests_pending_approval && <span className="rounded bg-[var(--warning-bg)] px-2 py-0.5 font-mono text-[11px] text-warning">{d.requests_pending_approval} чекають апруву</span>}
        </Kpi>
      </div>

      <Card className="mt-5">
        <CardHeader title="Операційний ланцюг акаунтів" icon={<Filter size={16} />}
          right={<span className="text-[12px] text-muted">Клік по етапу активує фільтр списку</span>} />
        <div className="flex flex-wrap items-stretch gap-3 p-5">
          <div className="grid flex-1 grid-cols-3 gap-2 md:grid-cols-5 xl:grid-cols-9">
            {FLOW.map((s, i) => {
              const active = stageFilter === s;
              const cls = s === "ready" ? "border-[var(--info-border)] bg-[var(--info-bg)]" : s === "issued" ? "border-[var(--success-border)] bg-[var(--success-bg)]" : "border-line bg-inset";
              return (
                <button key={s} onClick={() => { setStageFilter(active ? null : s); setTab("all"); }}
                  className={cn("rounded-lg border p-3 text-left transition hover:brightness-125 cursor-pointer", cls, active && "ring-2 ring-accent")}>
                  <div className="truncate text-[10px] font-semibold uppercase tracking-wider text-muted">{i + 1}. {STAGE_SHORT[s]}</div>
                  <div className="mt-1 font-mono text-[22px] font-semibold">{d?.funnel[s] ?? "…"}</div>
                </button>
              );
            })}
          </div>
          <button onClick={() => { setStageFilter(stageFilter === "off" ? null : "off"); setTab("all"); }}
            className={cn("min-w-52 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] p-3 text-left cursor-pointer", stageFilter === "off" && "ring-2 ring-accent")}>
            <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-[var(--stage-off-fg)]">
              <span>Off-пул</span><span className="font-mono text-[18px] text-main">{offTotal}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted">
              {d && (["ban", "reserve", "paused"] as const).map((r) => <span key={r}>{OFF_LABEL[r]}: <b className="text-main">{d.off_breakdown[r]}</b></span>)}
            </div>
          </button>
        </div>
      </Card>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader title="Реєстр акаунтів"
            right={
              <div className="flex gap-2">
                <Chip active={tab === "all" && !stageFilter} onClick={() => { setTab("all"); setStageFilter(null); }}>Усі</Chip>
                <Chip active={tab === "issued"} onClick={() => { setTab("issued"); setStageFilter(null); }}>Видані ({d?.issued ?? 0})</Chip>
                <Chip active={tab === "ready"} onClick={() => { setTab("ready"); setStageFilter(null); }}>Готові ({d?.ready ?? 0})</Chip>
                <Chip active={tab === "signals"} tone="danger" onClick={() => { setTab("signals"); setStageFilter(null); }}>Сигнали ({d?.signals_count ?? 0})</Chip>
              </div>
            } />
          <AccountsTable items={list?.items ?? []} showCost={user?.role === "admin"} />
          {list && list.total > list.items.length && (
            <div className="border-t border-divider px-5 py-3 text-right text-[13px]">
              <Link href="/accounts" className="text-accent hover:text-accent-light">Показано {list.items.length} з {list.total} — усі акаунти →</Link>
            </div>
          )}
        </Card>

        <div className="space-y-5 self-start">
          <Card>
            <CardHeader title="Заявки" icon={<Send size={16} />} right={!!d?.requests_queue && <span className="rounded-full bg-accent px-2 font-mono text-[11px] font-bold text-on-accent">{d.requests_queue}</span>} />
            {reqs && !reqs.length ? <Empty>Відкритих заявок немає</Empty> : (
              <div className="space-y-3 p-4">
                {reqs?.map((r) => <RequestCard key={r.id} r={r} compact admin={isAdmin(user)} canEdit={canWrite(user)} onChange={refreshAll} />)}
                <Link href="/requests" className="block text-center text-[13px] text-accent hover:text-accent-light">Усі заявки →</Link>
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title="Сигнали" icon={<Bell size={16} />} right={<span className="font-mono text-[12px] text-faint">{signals?.length ?? 0}</span>} />
            {signals && !signals.length ? <Empty>Усе спокійно</Empty> : (
              <ul className="divide-y divide-divider">
                {signals?.slice(0, 8).map((sg, i) => (
                  <li key={i} className="flex items-start gap-3 px-5 py-3 text-[13px]">
                    <i className="mt-1.5 size-2 shrink-0 rounded-full" style={{ background: sg.severity === "danger" ? "var(--danger)" : "var(--warning)" }} />
                    <span className="text-muted">
                      {sg.account_id ? (
                        <Link href={`/accounts?q=${encodeURIComponent(sg.code ?? "")}`} className="mr-2 font-mono font-semibold text-accent hover:text-accent-light">{sg.code}</Link>
                      ) : (
                        <Link href="/buyers" className="mr-2 font-mono font-semibold text-accent hover:text-accent-light">{sg.code}</Link>
                      )}
                      {sg.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
