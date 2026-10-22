"use client";
import { ArrowDownUp, CreditCard, KeyRound, RefreshCw, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import type { FbmCard, FbmCards, FbmCode } from "@/lib/types";
import { fmtDateTime, money } from "@/lib/utils";

const th = "px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-faint";
const statusColor = (s: string | null) =>
  s === "VALID CARD" ? "var(--success)" : s?.includes("BLOCK") ? "var(--stage-off-fg)" : "var(--warning)";

export default function CardsPage() {
  const { user } = useMe();
  const { data, mutate } = useSWR<FbmCards>("/api/fbm/cards", fetcher, { refreshInterval: 60000 });
  const [q, setQ] = useState("");
  const [acc, setAcc] = useState<string | null>(null);
  const [ownerFilter, setOwnerFilter] = useState<string>("");
  const [sortBy, setSortBy] = useState<"spend" | "owner" | "name" | "last4" | "status">("spend");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [codesFor, setCodesFor] = useState<FbmCard | null>(null);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      await api("/fbm/refresh", { method: "POST", body: {} });
      mutate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const ownersList = useMemo(() => {
    const s = new Set<string>();
    for (const c of data?.cards ?? []) {
      if (c.owner?.trim()) s.add(c.owner.trim());
    }
    return Array.from(s).sort();
  }, [data]);

  const cards = useMemo(() => {
    let c = [...(data?.cards ?? [])];
    if (acc) c = c.filter((x) => (x.account_name ?? "—") === acc);
    if (ownerFilter) c = c.filter((x) => (x.owner?.trim() ?? "") === ownerFilter);
    if (q) {
      const s = q.toLowerCase();
      c = c.filter((x) => [x.last4, x.name, x.owner, x.linked_code].some((f) => f?.toLowerCase().includes(s)));
    }
    const dir = sortDir === "desc" ? -1 : 1;
    c.sort((a, b) => {
      if (sortBy === "spend") {
        return ((Number(a.spend) || 0) - (Number(b.spend) || 0)) * dir;
      }
      if (sortBy === "owner") {
        return (a.owner ?? "").localeCompare(b.owner ?? "") * dir;
      }
      if (sortBy === "name") {
        return (a.name ?? "").localeCompare(b.name ?? "") * dir;
      }
      if (sortBy === "last4") {
        return (a.last4 ?? "").localeCompare(b.last4 ?? "") * dir;
      }
      return (a.status ?? "").localeCompare(b.status ?? "") * dir;
    });
    return c;
  }, [data, acc, ownerFilter, q, sortBy, sortDir]);

  if (data && !data.configured)
    return (
      <>
        <PageHeader title="Картки" />
        <Card className="p-10 text-center text-muted">FBM-pay не налаштовано (ключ у .env сервера).</Card>
      </>
    );

  return (
    <>
      <PageHeader
        title="Картки FBM"
        sub="Інвентар карток, сортування по юзерах і картках, спенд, баланси рахунків та 3DS-коди."
        right={
          <div className="flex items-center gap-3">
            {data?.last_sync && <span className="text-[12px] text-muted">оновлено {fmtDateTime(data.last_sync)}</span>}
            {canWrite(user) && (
              <Button variant="primary" onClick={refresh} disabled={busy}>
                <RefreshCw size={15} className={busy ? "animate-spin" : ""} />
                Оновити з FBM
              </Button>
            )}
          </div>
        }
      />
      <ErrorNote>{error}</ErrorNote>
      {!data ? (
        <Card className="p-10 text-center text-muted">Завантаження…</Card>
      ) : data.total === 0 ? (
        <Card className="p-10 text-center text-muted">Карток немає. Натисніть «Оновити», щоб підтягнути з FBM-pay.</Card>
      ) : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
            {[
              ["Усього карток", String(data.total), undefined],
              ["Активні", String(data.by_status["VALID CARD"] ?? 0), "var(--success)"],
              ["Сумарний спенд", money(data.total_spend), undefined],
              ["Зв'язано з акаунтами", String(data.cards.filter((c) => c.linked_code).length), undefined],
            ].map(([l, v, c]) => (
              <div key={l as string} className="panel kpi-glow p-5">
                <div className="text-[13px] text-muted">{l as string}</div>
                <div className="mt-2 font-mono text-[24px] font-bold" style={{ color: c as string }}>
                  {v as string}
                </div>
              </div>
            ))}
          </div>
          <Card>
            <CardHeader
              title={`Картки (${cards.length})`}
              icon={<CreditCard size={16} />}
              right={
                <div className="flex flex-wrap items-center gap-2">
                  <Select
                    className="h-8 w-44 text-[12px]"
                    value={ownerFilter}
                    onChange={(e) => setOwnerFilter(e.target.value)}
                  >
                    <option value="">Усі юзери FBM</option>
                    {ownersList.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </Select>
                  <div className="flex items-center gap-1 text-[12px] text-muted">
                    <ArrowDownUp size={13} />
                    <Select
                      className="h-8 w-44 text-[12px]"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                    >
                      <option value="spend">Сортувати: за спендом</option>
                      <option value="name">Сортувати: за юзером / назвою</option>
                      <option value="owner">Сортувати: за власником FBM</option>
                      <option value="last4">Сортувати: за номером картки</option>
                      <option value="status">Сортувати: за статусом</option>
                    </Select>
                    <button
                      onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
                      className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-1 font-mono text-[11px] text-muted hover:text-main"
                    >
                      {sortDir === "desc" ? "↓" : "↑"}
                    </button>
                  </div>
                  <div className="relative">
                    <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                    <Input
                      className="h-8 w-52 pl-8"
                      placeholder="last4, назва, баер, акаунт…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                  </div>
                </div>
              }
            />
            <div className="flex flex-wrap gap-2 border-b border-divider p-4">
              <button
                onClick={() => setAcc(null)}
                className={`cursor-pointer rounded-full border px-3 py-1 text-[12px] ${
                  !acc ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface-hover text-muted"
                }`}
              >
                Усі рахунки ({data.total})
              </button>
              {Object.entries(data.by_account).map(([a, n]) => (
                <button
                  key={a}
                  onClick={() => setAcc(a)}
                  className={`cursor-pointer rounded-full border px-3 py-1 text-[12px] ${
                    acc === a ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface-hover text-muted"
                  }`}
                >
                  {a} ({n})
                </button>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-divider bg-inset/50">
                    <th className={th}>Картка</th>
                    <th className={th}>Назва (Юзер / Команда)</th>
                    <th className={th}>Статус</th>
                    <th className={th}>Спенд</th>
                    <th className={th}>Власник FBM</th>
                    <th className={th}>Рахунок (Баланс)</th>
                    <th className={th}>Акаунт</th>
                    <th className={th}></th>
                  </tr>
                </thead>
                <tbody>
                  {cards.slice(0, 400).map((c) => (
                    <tr key={c.card_id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                      <td className="px-4 py-2.5 font-mono">•• {c.last4 ?? "—"}</td>
                      <td className="px-4 py-2.5 font-medium">{c.name ?? "—"}</td>
                      <td className="px-4 py-2.5">
                        <span className="font-mono text-[11px]" style={{ color: statusColor(c.status) }}>
                          {c.status ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono font-semibold">{c.spend !== null ? money(c.spend) : "—"}</td>
                      <td className="px-4 py-2.5 text-muted">{c.owner ?? "—"}</td>
                      <td className="px-4 py-2.5 text-muted">
                        {c.account_name ?? "—"}{" "}
                        {c.account_balance && <span className="font-mono text-[11px] text-faint">({money(c.account_balance)})</span>}
                      </td>
                      <td className="px-4 py-2.5">
                        {c.linked_code ? (
                          <Link href={`/accounts?q=${c.linked_code}`} className="font-mono text-accent hover:text-accent-light">
                            {c.linked_code}
                          </Link>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {canWrite(user) ? (
                          <button
                            onClick={() => setCodesFor(c)}
                            className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-line-strong bg-surface-hover px-2 py-1 text-[11px] text-muted hover:text-main"
                          >
                            <KeyRound size={12} />
                            3DS
                          </button>
                        ) : (
                          <span className="text-[11px] text-faint">лише оператор</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {cards.length > 400 && <p className="px-4 py-3 text-[12px] text-faint">Показано 400 із {cards.length}</p>}
            </div>
          </Card>
        </>
      )}
      {codesFor && <CodesModal card={codesFor} onClose={() => setCodesFor(null)} />}
    </>
  );
}

function CodesModal({ card, onClose }: { card: FbmCard; onClose: () => void }) {
  const { data, isLoading } = useSWR<FbmCode[]>(`/api/fbm/cards/${card.card_id}/codes`, fetcher, { refreshInterval: 15000 });
  function copy(code: string) {
    try {
      navigator.clipboard.writeText(code);
    } catch {}
  }
  return (
    <Modal title={`3DS-коди · •• ${card.last4 ?? ""}`} onClose={onClose}>
      <p className="text-[12px] text-muted">{card.name}</p>
      {isLoading ? (
        <p className="py-6 text-center text-muted">Завантаження…</p>
      ) : !data?.length ? (
        <Empty>Кодів ще немає</Empty>
      ) : (
        <ul className="divide-y divide-divider">
          {data.map((c, i) => (
            <li key={i} className="flex items-center justify-between py-2.5">
              <button
                onClick={() => c.code && copy(c.code)}
                className="cursor-pointer font-mono text-[18px] font-bold text-accent hover:text-accent-light"
                title="Копіювати"
              >
                {c.code ?? "—"}
              </button>
              <span className="font-mono text-[11px] text-faint">{c.at ? fmtDateTime(c.at) : ""}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-faint">Коди тягнуться з FBM наживо, не зберігаються. Клік — копіювати.</p>
    </Modal>
  );
}
