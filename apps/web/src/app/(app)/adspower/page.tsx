"use client";
import { CheckCircle2, Link2Off, RefreshCw, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { Card, CardHeader, Chip, Empty, ErrorNote, Input, PageHeader, StageBadge } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, isAdmin, useMe } from "@/lib/session";
import type { AdsImportResult, BridgeStatus, Stage, SyncView } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

const th = "px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export default function AdsPowerPage() {
  const { user } = useMe();
  const { data: bridge } = useSWR<BridgeStatus>("/api/bridge/status", fetcher, { refreshInterval: 10000 });
  const { data, mutate } = useSWR<SyncView>("/api/adspower/profiles", fetcher, {
    refreshInterval: (d) => (d?.pending ? 2000 : 0),
  });
  const [q, setQ] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const [onlyUnlinked, setOnlyUnlinked] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [imported, setImported] = useState<AdsImportResult | null>(null);

  async function importUnlinked() {
    setBusy(true); setError(""); setImported(null);
    try { setImported(await api<AdsImportResult>("/adspower/import-unlinked", { method: "POST", body: {} })); mutate(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError("");
    try { await api("/adspower/refresh", { method: "POST", body: {} }); mutate(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const profiles = useMemo(() => {
    let p = data?.profiles ?? [];
    if (group) p = p.filter((x) => (x.group_name ?? "— без групи —") === group);
    if (onlyUnlinked) p = p.filter((x) => !x.linked_code);
    if (q) {
      const s = q.toLowerCase();
      p = p.filter((x) => [x.name, x.fb_user_id, x.username, x.group_name, x.linked_code].some((f) => f?.toLowerCase().includes(s)));
    }
    return p;
  }, [data, group, onlyUnlinked, q]);

  return (
    <>
      <PageHeader title="AdsPower" sub="Дзеркало профілів з AdsPower. Тільки читання — паролі й cookies не зберігаються."
        right={
          <div className="flex items-center gap-3">
            {data?.last_sync && <span className="text-[12px] text-muted">синхронізовано {fmtDateTime(data.last_sync)}</span>}
            {isAdmin(user) && !!data?.unlinked && !data?.pending && (
              <button onClick={importUnlinked} disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-line-strong bg-surface-hover px-4 text-[13px] font-semibold text-main disabled:opacity-40 hover:bg-surface-active">
                Імпортувати непов'язані ({data.unlinked})
              </button>
            )}
            {canWrite(user) && (
              <button onClick={refresh} disabled={busy || data?.pending || !bridge?.online}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-[13px] font-semibold text-on-accent disabled:opacity-40 hover:bg-accent-light">
                <RefreshCw size={15} className={data?.pending ? "animate-spin" : ""} />{data?.pending ? "Синхронізація…" : "Синхронізувати"}
              </button>
            )}
          </div>
        } />
      <ErrorNote>{error}</ErrorNote>
      {imported && <p className="mb-4 rounded-md border border-[var(--success-border)] bg-[var(--success-bg)] px-3 py-2 text-[13px] text-success">Створено акаунтів: {imported.created}. Оновлено груп: {imported.updated_group}. Пропущено: {imported.skipped}. За етапами: {Object.entries(imported.by_stage).map(([k,v]) => `${k}:${v}`).join(", ") || "—"}</p>}
      {!bridge?.online && <p className="mb-4 rounded-md border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-[13px] text-warning">Bridge офлайн — синхронізація недоступна. Останні дані показані нижче.</p>}

      {!data || data.total === 0 ? (
        <Card className="p-10 text-center text-[13px] text-muted">
          {data?.pending ? "Тягнемо профілі з AdsPower…" : "Профілів ще не синхронізовано. Натисніть «Синхронізувати», коли bridge онлайн."}
        </Card>
      ) : (
        <>
          <div className="mb-5 grid grid-cols-3 gap-4">
            {[["Усього профілів", data.total, undefined], ["Зіставлено з акаунтами", data.linked, "var(--success)"], ["Не зіставлено", data.unlinked, data.unlinked ? "var(--warning)" : undefined]].map(([l, v, c]) => (
              <div key={l as string} className="panel kpi-glow p-5">
                <div className="text-[13px] text-muted">{l as string}</div>
                <div className="mt-2 font-mono text-[26px] font-bold" style={{ color: c as string }}>{v as number}</div>
              </div>
            ))}
          </div>

          <Card>
            <CardHeader title="Профілі" right={
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-[12px] text-muted cursor-pointer">
                  <input type="checkbox" className="accent-[var(--accent)]" checked={onlyUnlinked} onChange={(e) => setOnlyUnlinked(e.target.checked)} />лише не зіставлені
                </label>
                <div className="relative">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                  <Input className="h-8 w-56 pl-8" placeholder="FB ID, назва, пошта, група…" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
              </div>
            } />
            <div className="flex flex-wrap gap-2 border-b border-divider p-4">
              <Chip active={!group} onClick={() => setGroup(null)}>Усі групи ({data.total})</Chip>
              {Object.entries(data.by_group).map(([g, n]) => <Chip key={g} active={group === g} onClick={() => setGroup(g)}>{g} ({n})</Chip>)}
            </div>
            {profiles.length === 0 ? <Empty>Нічого не знайдено</Empty> : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="border-b border-divider bg-inset/50">
                    <th className={th}>Профіль</th><th className={th}>FB ID</th><th className={th}>Пошта</th><th className={th}>Група</th><th className={th}>GEO</th><th className={th}>У дашборді</th>
                  </tr></thead>
                  <tbody>
                    {profiles.slice(0, 500).map((p) => (
                      <tr key={p.profile_id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                        <td className="px-4 py-2.5">{p.name}</td>
                        <td className="px-4 py-2.5 font-mono text-[12px]">{p.fb_user_id ?? <span className="text-faint">—</span>}</td>
                        <td className="px-4 py-2.5 text-muted">{p.username ?? "—"}</td>
                        <td className="px-4 py-2.5">{p.group_name ?? <span className="text-faint">— без групи —</span>}</td>
                        <td className="px-4 py-2.5 font-mono">{p.country ?? "—"}</td>
                        <td className="px-4 py-2.5">
                          {p.linked_code
                            ? <span className="inline-flex items-center gap-1.5 text-success"><CheckCircle2 size={14} /><span className="font-mono">{p.linked_code}</span>{p.linked_stage && <StageBadge stage={p.linked_stage as Stage} />}</span>
                            : <span className="inline-flex items-center gap-1.5 text-faint"><Link2Off size={14} />не зіставлено</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {profiles.length > 500 && <p className="px-4 py-3 text-[12px] text-faint">Показано 500 із {profiles.length}</p>}
              </div>
            )}
          </Card>
          <p className="mt-4 text-[12px] text-faint">Не зіставлені профілі — це акаунти, що є в AdsPower, але ще не заведені в дашборді. Наступний крок (окремо): імпортувати їх як акаунти з прив'язкою за FB ID.</p>
        </>
      )}
    </>
  );
}
