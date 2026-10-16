"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { doTransition, needsDialog, TransitionDialog } from "@/components/accounts/transition";
import { ErrorNote, PageHeader } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import { FLOW, STAGE_LABEL, stageTone, TONE_STYLE } from "@/lib/stages";
import type { Account, AccountList, Stage } from "@/lib/types";
import { cn, timeLeft } from "@/lib/utils";

const COLUMNS: Stage[] = [...FLOW, "returned", "off"];
const COL_LIMIT = 40;  // карток на колонку; решта — посиланням у список

export default function KanbanPage() {
  const { user } = useMe();
  const { data, mutate } = useSWR<AccountList>("/api/accounts?limit=1000", fetcher, { refreshInterval: 30000 });
  const [drag, setDrag] = useState<Account | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const [dialog, setDialog] = useState<{ acc: Account; to: Stage } | null>(null);
  const [error, setError] = useState("");
  const write = canWrite(user);

  const items = data?.items ?? [];

  const allowed = (a: Account | null, to: Stage) => !!a && a.next_stages.includes(to) && !(to === "issued" && user?.role !== "admin");

  async function drop(to: Stage) {
    const a = drag;
    setDrag(null); setOver(null); setError("");
    if (!a || a.stage === to) return;
    if (!allowed(a, to)) {
      return setError(`${a.code}: перехід ${STAGE_LABEL[a.stage]} → ${STAGE_LABEL[to]} не дозволений${to === "issued" && user?.role !== "admin" ? " для вашої ролі" : ""}`);
    }
    if (needsDialog(to)) return setDialog({ acc: a, to });
    try { await doTransition(a.id, { to }); mutate(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <PageHeader title="Етапи (Канбан)" sub={write ? "Перетягніть картку на дозволений наступний етап" : "Режим перегляду"} />
      <ErrorNote>{error}</ErrorNote>
      <div className="mt-3 flex gap-3 overflow-x-auto pb-4">
        {COLUMNS.map((s) => {
          const col = items.filter((a) => a.stage === s);
          const t = TONE_STYLE[stageTone(s)];
          const ok = drag ? allowed(drag, s) : null;
          return (
            <div key={s}
              onDragOver={(e) => { if (drag) { e.preventDefault(); setOver(s); } }}
              onDragLeave={() => setOver((o) => (o === s ? null : o))}
              onDrop={() => drop(s)}
              className={cn("panel w-64 shrink-0 self-start p-3 transition", drag && ok && "ring-1 ring-[var(--success-border)]", over === s && (ok ? "ring-2 ring-success" : "ring-2 ring-danger"))}>
              <div className="mb-3 flex items-center justify-between px-1 text-[12px] font-semibold uppercase tracking-wider" style={{ color: t.fg }}>
                <span>{STAGE_LABEL[s]}</span><span className="font-mono">{col.length}</span>
              </div>
              <div className="max-h-[calc(100vh-220px)] space-y-2 overflow-y-auto pr-1">
                {col.slice(0, COL_LIMIT).map((a) => (
                  <div key={a.id} draggable={write} onDragStart={() => setDrag(a)} onDragEnd={() => { setDrag(null); setOver(null); }}
                    className={cn("rounded-lg border border-line bg-inset p-3 transition hover:border-line-hover", write && "cursor-grab active:cursor-grabbing", drag?.id === a.id && "opacity-40")}>
                    <Link href={`/accounts/${a.id}`} className="font-mono text-[13px] font-semibold text-accent hover:text-accent-light" draggable={false}>{a.code}</Link>
                    <div className="mt-1 flex justify-between text-[12px] text-muted">
                      <span>{a.client_name ?? a.supplier_name ?? "—"}</span>
                      {a.stage === "checking" && a.check_until && <span className="font-mono text-[var(--stage-check-fg)]">{timeLeft(a.check_until)}</span>}
                      {a.stage === "off" && a.off_reason && <span className="font-mono text-[var(--stage-off-fg)]">{a.off_reason}</span>}
                    </div>
                  </div>
                ))}
                {col.length > COL_LIMIT && (
                  <Link href={`/accounts?stage=${s}`} className="block rounded-lg border border-dashed border-line-strong px-3 py-2 text-center text-[12px] text-accent hover:bg-surface-hover">
                    +{col.length - COL_LIMIT} ще — відкрити списком →
                  </Link>
                )}
                {!col.length && <div className="px-1 py-4 text-center text-[12px] text-faint">порожньо</div>}
              </div>
            </div>
          );
        })}
      </div>
      {data && data.total > items.length && <p className="text-[12px] text-muted">Показано {items.length} з {data.total}</p>}
      {dialog && <TransitionDialog account={dialog.acc} target={dialog.to} onClose={() => setDialog(null)} onDone={() => { setDialog(null); mutate(); }} />}
    </>
  );
}
