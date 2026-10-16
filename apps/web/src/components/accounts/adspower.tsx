"use client";
import { MonitorPlay, Plus, X } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, ErrorNote } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import type { Account, BridgeCommand, BridgeStatus } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

export const CMD_LABEL: Record<string, string> = {
  create_profile: "Створити профіль", open_profile: "Відкрити профіль", close_profile: "Закрити профіль",
  list_profiles: "Список профілів", find_profile: "Знайти профіль", update_profile_group: "Змінити групу",
};
export const CMD_STATUS: Record<BridgeCommand["status"], { label: string; color: string }> = {
  pending: { label: "у черзі", color: "var(--warning)" }, sent: { label: "виконується", color: "var(--info)" },
  ok: { label: "виконано", color: "var(--success)" }, error: { label: "помилка", color: "var(--stage-off-fg)" },
};

export function AdsPowerCard({ acc, canWrite, onChanged }: { acc: Account; canWrite: boolean; onChanged: () => void }) {
  const { data: st } = useSWR<BridgeStatus>("/api/bridge/status", fetcher, { refreshInterval: 10000 });
  const [active, setActive] = useState(false);
  const { data: cmds, mutate } = useSWR<BridgeCommand[]>(`/api/bridge/commands?account_id=${acc.id}&limit=5`, fetcher, {
    refreshInterval: active ? 2000 : 0,
    onSuccess: (d) => {
      const running = d.some((c) => c.status === "pending" || c.status === "sent");
      if (active && !running) onChanged();  // команда завершилась → оновити акаунт і журнал
      setActive(running);
    },
  });
  const [error, setError] = useState("");
  const busy = !!cmds?.some((c) => c.status === "pending" || c.status === "sent");

  async function run(path: string) {
    setError("");
    try { await api(`/accounts/${acc.id}/adspower/${path}`, { method: "POST", body: {} }); setActive(true); mutate(); } catch (e) { setError((e as Error).message); }
  }
  async function cancel(id: string) { try { await api(`/bridge/commands/${id}/cancel`, { method: "POST", body: {} }); mutate(); } catch (e) { setError((e as Error).message); } }

  return (
    <Card>
      <CardHeader title="AdsPower" icon={<MonitorPlay size={16} />}
        right={<span className="flex items-center gap-1.5 font-mono text-[11px]" style={{ color: st?.online ? "var(--success)" : "var(--stage-off-fg)" }}>
          <i className="size-1.5 rounded-full" style={{ background: st?.online ? "var(--success)" : "var(--danger)" }} />{st?.online ? "міст онлайн" : "міст офлайн"}</span>} />
      <div className="space-y-3 p-5 text-[13px]">
        <div className="flex items-center justify-between">
          <span className="text-muted">Профіль</span>
          <span className="font-mono">{acc.adspower_profile_id ?? <span className="text-faint">не створено</span>}</span>
        </div>
        {!st?.online && <p className="rounded-md border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-[12px] text-warning">Міст офлайн — команда чекатиме в черзі й виконається, щойно він підключиться.</p>}
        {canWrite && (
          <div className="flex flex-wrap gap-2">
            {!acc.adspower_profile_id
              ? <Button size="sm" variant="primary" disabled={busy} onClick={() => run("create-profile")}><Plus size={14} />Створити профіль</Button>
              : <><Button size="sm" disabled={busy} onClick={() => run("open")}>Відкрити</Button><Button size="sm" disabled={busy} onClick={() => run("close")}>Закрити</Button></>}
          </div>
        )}
        <ErrorNote>{error}</ErrorNote>
        {!!cmds?.length && (
          <ul className="divide-y divide-divider rounded-md border border-line">
            {cmds.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-3 py-2 text-[12px]">
                <span className="flex-1">{CMD_LABEL[c.command] ?? c.command}
                  {c.status === "error" && <span className="ml-2 text-[var(--stage-off-fg)]">{String(c.result?.error ?? "")}</span>}</span>
                <span className="font-mono text-[11px] text-faint">{fmtDateTime(c.created_at)}</span>
                <span className="font-mono" style={{ color: CMD_STATUS[c.status].color }}>{CMD_STATUS[c.status].label}</span>
                {c.status === "pending" && canWrite && <button aria-label="Скасувати" title="Скасувати" onClick={() => cancel(c.id)} className="text-muted hover:text-main cursor-pointer"><X size={14} /></button>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
