"use client";
import {
  AlertTriangle,
  ArrowDownUp,
  Calendar,
  CheckCircle2,
  CheckSquare,
  Code,
  CreditCard,
  Download,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Square,
  UploadCloud,
  UserCheck,
  Wallet,
} from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import type { BuyerDetail, BuyerItem, BuyersOverview, TeamItem } from "@/lib/types";
import { fmtDateTime, money } from "@/lib/utils";

const th = "px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export default function BuyersPage() {
  const { user } = useMe();
  const [teamId, setTeamId] = useState<string>("");
  const [sortBy, setSortBy] = useState<"spend_total" | "spend_today" | "name" | "cards_count">("spend_total");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [selectedBuyerId, setSelectedBuyerId] = useState<string | null>(null);
  const [addingBuyer, setAddingBuyer] = useState(false);
  const [editingTeam, setEditingTeam] = useState<TeamItem | "new" | null>(null);

  const queryUrl = `/api/buyers/overview?sort_by=${sortBy}&sort_dir=${sortDir}${teamId ? `&team_id=${teamId}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const { data, mutate } = useSWR<BuyersOverview>(queryUrl, fetcher, { refreshInterval: 30000, keepPreviousData: true });

  async function togglePriority(b: BuyerItem, e: React.MouseEvent) {
    e.stopPropagation();
    if (!canWrite(user)) return;
    try {
      await api(`/buyers/${b.id}`, { method: "PATCH", body: { is_priority: !b.is_priority } });
      mutate();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runParseFbm() {
    setBusy("parse");
    setError("");
    setNotice("");
    try {
      const res = await api<{ teams_created: number; buyers_created: number; total_buyers: number }>("/buyers/parse-fbm", {
        method: "POST",
        body: {},
      });
      setNotice(`Парсинг FBM завершено: нових команд ${res.teams_created}, нових юзерів ${res.buyers_created} (усього ${res.total_buyers}). Дублів немає.`);
      mutate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function runSnapshotSpend() {
    setBusy("snap");
    setError("");
    setNotice("");
    try {
      const res = await api<{ cards_logged: number; total_delta: string }>("/buyers/snapshot-spend?refresh_fbm=true", {
        method: "POST",
        body: {},
      });
      setNotice(`Зафіксовано спенд по ${res.cards_logged} картках у базу даних (дельта з попередньої фіксації: ${money(res.total_delta)}).`);
      mutate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function runReconcile() {
    setBusy("reconcile");
    setError("");
    setNotice("");
    try {
      const res = await api<{ status: string; fbm_total_spend: string; db_total_spend: string; diff_amount: string }>("/buyers/reconcile?fetch_live=true", {
        method: "POST",
        body: {},
      });
      if (res.status === "ok") {
        setNotice(`Добова звірка з FBM Cards успішна: розбіжностей немає (сума ${money(res.fbm_total_spend)}).`);
      } else {
        setError(`Виявлено розбіжність із кабінетом FBM Cards на суму ${money(res.diff_amount)}! Створено сповіщення.`);
      }
      mutate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function pushTeamSheet(t: TeamItem) {
    setBusy(`push-${t.id}`);
    setError("");
    setNotice("");
    try {
      const res = await api<{ ok: boolean; buyers_count?: number }>(`/buyers/teams/${t.id}/push-sheet`, {
        method: "POST",
        body: {},
      });
      setNotice(`Успішно записано спенд по ${res.buyers_count ?? "всіх"} юзерах у Google-таблицю команди «${t.name}»!`);
      mutate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const activeTeam = data?.teams.find((t) => t.id === teamId) ?? null;

  return (
    <>
      <PageHeader
        title="Юзери та Команди"
        sub="Розбивка по командах та баєрах, фіксація спенду кожні 3–4 год, звірка з FBM Cards раз на добу та синхронізація таблиць."
        right={
          canWrite(user) && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={runParseFbm} disabled={!!busy}>
                <Sparkles size={14} className={busy === "parse" ? "animate-spin" : ""} />
                Спарсити юзерів із FBM
              </Button>
              <Button size="sm" onClick={runSnapshotSpend} disabled={!!busy}>
                <RefreshCw size={14} className={busy === "snap" ? "animate-spin" : ""} />
                Зафіксувати спенд (3–4г)
              </Button>
              <Button size="sm" onClick={runReconcile} disabled={!!busy}>
                <ShieldCheck size={14} className={busy === "reconcile" ? "animate-spin" : ""} />
                Звірити з FBM (24г)
              </Button>
              <Button size="sm" onClick={() => setEditingTeam("new")}>
                <FileSpreadsheet size={14} />+ Таблиця / Команда
              </Button>
              <Button size="sm" variant="primary" onClick={() => setAddingBuyer(true)}>
                <Plus size={14} />+ Юзер
              </Button>
            </div>
          )
        }
      />

      <ErrorNote>{error}</ErrorNote>
      {notice && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-success/40 bg-success/10 px-4 py-2.5 text-[13px] text-success">
          <span>{notice}</span>
          <button onClick={() => setNotice("")} className="cursor-pointer text-[11px] underline">
            Закрити
          </button>
        </div>
      )}

      {!data ? (
        <Card className="p-10 text-center text-muted">Завантаження даних по командах і юзерах…</Card>
      ) : (
        <div className="space-y-5">
          {/* 1. Блок балансів кабінетів FBM та Команд із таблиць */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Баланси кабінетів FBM Cards"
                icon={<Wallet size={16} />}
                right={<span className="text-[11px] text-faint">ліміт сповіщення &lt; $1,000</span>}
              />
              <div className="divide-y divide-divider">
                {data.fbm_accounts.length === 0 ? (
                  <Empty>Немає даних про рахунки FBM</Empty>
                ) : (
                  data.fbm_accounts.map((a) => (
                    <div key={a.account_name} className="flex items-center justify-between px-5 py-3.5">
                      <div>
                        <div className="flex items-center gap-2 font-medium">
                          <span>{a.account_name}</span>
                          {a.negative_balance && (
                            <span className="inline-flex items-center gap-1 rounded bg-danger/20 px-2 py-0.5 font-mono text-[11px] text-danger">
                              <AlertTriangle size={11} /> МІНУСОВИЙ БАЛАНС
                            </span>
                          )}
                          {!a.negative_balance && a.low_balance && (
                            <span className="inline-flex items-center gap-1 rounded bg-warning/20 px-2 py-0.5 font-mono text-[11px] text-warning">
                              <AlertTriangle size={11} /> &lt; $1,000
                            </span>
                          )}
                        </div>
                        <div className="text-[12px] text-muted">
                          {a.cards_count} карток · Сумарний спенд: <span className="font-mono">{money(a.total_spend)}</span>
                        </div>
                      </div>
                      <div
                        className="font-mono text-[20px] font-bold"
                        style={{
                          color: a.negative_balance
                            ? "var(--stage-off-fg)"
                            : a.low_balance
                              ? "var(--warning)"
                              : "var(--success)",
                        }}
                      >
                        {a.balance !== null ? money(a.balance) : "—"}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Баланси команд (з Google-таблиць)"
                icon={<FileSpreadsheet size={16} />}
                right={
                  <span className="text-[11px] text-faint">
                    {data.reconciliation ? (
                      data.reconciliation.status === "ok" ? (
                        <span className="inline-flex items-center gap-1 text-success">
                          <CheckCircle2 size={12} /> Звірка FBM OK ({money(data.reconciliation.fbm_total_spend)})
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-danger">
                          <AlertTriangle size={12} /> Розбіжність FBM: {money(data.reconciliation.diff_amount)}
                        </span>
                      )
                    ) : (
                      "Оновлення кожні 3–4 год"
                    )}
                  </span>
                }
              />
              <div className="divide-y divide-divider">
                {data.teams.map((t) => (
                  <div key={t.id} className="flex items-center justify-between px-5 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 font-medium">
                        <span className="truncate">{t.name}</span>
                        <span className="rounded bg-surface-hover px-1.5 py-0.5 font-mono text-[11px] text-muted">
                          комс {t.fee_percent}%
                        </span>
                        {t.negative_balance && (
                          <span className="rounded bg-danger/20 px-1.5 py-0.5 font-mono text-[10.5px] text-danger">
                            Мінус!
                          </span>
                        )}
                        {!t.negative_balance && t.low_balance && (
                          <span className="rounded bg-warning/20 px-1.5 py-0.5 font-mono text-[10.5px] text-warning">
                            &lt; $1,000
                          </span>
                        )}
                      </div>
                      <div className="text-[12px] text-muted">
                        {t.buyers_count} юзерів · Спенд FBM: <span className="font-mono text-main">{money(t.spend_total_fbm)}</span>
                        {t.spend_total_sheet && (
                          <>
                            {" "}· Таблиця: <span className="font-mono">{money(t.spend_total_sheet)}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-[10.5px] uppercase text-faint">Баланс таблиці</div>
                        <div
                          className="font-mono text-[16px] font-bold"
                          style={{
                            color:
                              t.sheet_balance === null
                                ? "var(--text-faint)"
                                : t.negative_balance
                                  ? "var(--stage-off-fg)"
                                  : t.low_balance
                                    ? "var(--warning)"
                                    : "var(--success)",
                          }}
                        >
                          {t.sheet_balance !== null ? money(t.sheet_balance) : "не задано"}
                        </div>
                      </div>
                      {canWrite(user) && (
                        <div className="flex items-center gap-1.5">
                          {t.sheet_webhook_url && (
                            <Button
                              size="sm"
                              variant="primary"
                              disabled={busy === `push-${t.id}`}
                              onClick={() => pushTeamSheet(t)}
                              title="Записати актуальні спенди з FBM у Google-таблицю"
                            >
                              <UploadCloud size={13} className={busy === `push-${t.id}` ? "animate-spin" : ""} />
                              Записати
                            </Button>
                          )}
                          <Button size="sm" onClick={() => setEditingTeam(t)}>
                            Таблиця
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* 2. Панель фільтрів по командах та сортування */}
          <Card>
            <CardHeader
              title={`Юзери / Баєри (${data.buyers.length})`}
              icon={<UserCheck size={16} />}
              right={
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1.5 text-[12px] text-muted">
                    <ArrowDownUp size={13} />
                    <span>Сортування:</span>
                    <Select
                      className="h-8 w-44 text-[12px]"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                    >
                      <option value="spend_total">За загальним спендом</option>
                      <option value="spend_today">За спендом сьогодні</option>
                      <option value="cards_count">За кількістю карток</option>
                      <option value="name">За назвою юзера (А–Я)</option>
                    </Select>
                    <button
                      onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
                      className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-1 font-mono text-[11px] text-muted hover:text-main"
                    >
                      {sortDir === "desc" ? "↓ Спад" : "↑ Зрост"}
                    </button>
                  </div>
                  <div className="relative">
                    <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                    <Input
                      className="h-8 w-56 pl-8"
                      placeholder="Юзер, команда, last4 картки…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                  </div>
                </div>
              }
            />

            {/* Вкладки команд */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-divider p-4">
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setTeamId("")}
                  className={`cursor-pointer rounded-full border px-3 py-1 text-[12px] transition ${
                    !teamId
                      ? "border-accent bg-accent font-semibold text-on-accent"
                      : "border-line-strong bg-surface-hover text-muted hover:text-main"
                  }`}
                >
                  Усі команди ({data.buyers.length})
                </button>
                {data.teams.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTeamId(t.id)}
                    className={`cursor-pointer rounded-full border px-3 py-1 text-[12px] transition ${
                      teamId === t.id
                        ? "border-accent bg-accent font-semibold text-on-accent"
                        : "border-line-strong bg-surface-hover text-muted hover:text-main"
                    }`}
                  >
                    {t.name} ({t.buyers_count})
                  </button>
                ))}
              </div>

              {activeTeam && (
                <div className="flex items-center gap-2">
                  <a
                    href={`/api/buyers/teams/${activeTeam.id}/export-csv`}
                    download={`${activeTeam.name}.csv`}
                    className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface-hover px-3 py-1 text-[12px] text-main hover:border-accent"
                  >
                    <Download size={13} /> Вивантажити таблицю спенду (CSV)
                  </a>
                </div>
              )}
            </div>

            {/* Таблиця юзерів */}
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-divider bg-inset/50">
                    <th className={th} title="Пріоритетні юзери завжди піднімаються наверх списку">
                      Пріоритет
                    </th>
                    <th className={th}>Юзер (Баєр)</th>
                    <th className={th}>Команда</th>
                    <th className={th}>Картки FBM</th>
                    <th className={th}>Кабінетів (T1)</th>
                    <th className={th}>Спенд сьогодні</th>
                    <th className={th}>Спенд по таблиці</th>
                    <th className={th}>Усього спенд (FBM)</th>
                    <th className={th}></th>
                  </tr>
                </thead>
                <tbody>
                  {data.buyers.map((b) => (
                    <tr
                      key={b.id}
                      onClick={() => setSelectedBuyerId(b.id)}
                      className={`cursor-pointer border-b border-divider last:border-0 transition hover:bg-surface-hover ${
                        b.is_priority ? "bg-accent/5" : ""
                      }`}
                    >
                      <td className="px-4 py-3" onClick={(e) => togglePriority(b, e)}>
                        <button
                          type="button"
                          className={`inline-flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[12px] font-medium transition ${
                            b.is_priority
                              ? "bg-accent/20 text-accent"
                              : "text-faint hover:bg-surface-hover hover:text-main"
                          }`}
                          title="Поставити галочку пріоритету (піднімає наверх списку)"
                        >
                          {b.is_priority ? <CheckSquare size={15} /> : <Square size={15} />}
                          {b.is_priority && <span className="text-[11px] font-semibold">ТОП</span>}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-mono font-semibold text-main">{b.name}</div>
                        {b.fbm_owner && <div className="text-[11px] text-faint">FBM: {b.fbm_owner}</div>}
                      </td>
                      <td className="px-4 py-3 text-muted">{b.team_name ?? "—"}</td>
                      <td className="px-4 py-3">
                        {b.cards.length === 0 ? (
                          <span className="text-faint">0 карток</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {b.cards.slice(0, 3).map((c) => (
                              <span
                                key={c.card_id}
                                className="rounded border border-line bg-inset px-1.5 py-0.5 font-mono text-[11px] text-muted"
                                title={`${c.name} (${money(c.spend)})`}
                              >
                                ••{c.last4}
                              </span>
                            ))}
                            {b.cards.length > 3 && (
                              <span className="rounded bg-surface-hover px-1.5 py-0.5 font-mono text-[11px] text-faint">
                                +{b.cards.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-muted">{b.accounts_count || "—"}</td>
                      <td className="px-4 py-3 font-mono">
                        {Number(b.spend_today) > 0 ? (
                          <span className="font-semibold text-success">{money(b.spend_today)}</span>
                        ) : (
                          <span className="text-faint">$0.00</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-muted">
                        {Number(b.spend_sheet) > 0 ? money(b.spend_sheet) : "—"}
                      </td>
                      <td className="px-4 py-3 font-mono font-semibold text-accent">{money(b.spend_total)}</td>
                      <td className="px-4 py-3 text-right">
                        <span className="rounded-md border border-line-strong bg-surface-hover px-2.5 py-1 text-[11.5px] text-muted hover:text-main">
                          Карточка →
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* Модалка детальної Карточки Юзера з фільтрами по періоду */}
      {selectedBuyerId && (
        <BuyerCardModal
          buyerId={selectedBuyerId}
          teams={data?.teams ?? []}
          onClose={() => setSelectedBuyerId(null)}
          onChanged={() => mutate()}
        />
      )}

      {/* Модалка додавання нового юзера вручну (з перевіркою дублів) */}
      {addingBuyer && (
        <AddBuyerModal
          teams={data?.teams ?? []}
          onClose={() => setAddingBuyer(false)}
          onDone={() => {
            setAddingBuyer(false);
            mutate();
          }}
        />
      )}

      {/* Модалка налаштування Команди та її Google-таблиці */}
      {editingTeam && (
        <TeamSheetModal
          team={editingTeam === "new" ? null : editingTeam}
          onClose={() => setEditingTeam(null)}
          onDone={() => {
            setEditingTeam(null);
            mutate();
          }}
        />
      )}
    </>
  );
}

function BuyerCardModal({
  buyerId,
  teams,
  onClose,
  onChanged,
}: {
  buyerId: string;
  teams: TeamItem[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { user } = useMe();
  const todayStr = new Date().toISOString().slice(0, 10);
  const monthStartStr = todayStr.slice(0, 8) + "01";
  const [dateFrom, setDateFrom] = useState(monthStartStr);
  const [dateTo, setDateTo] = useState(todayStr);

  const { data, mutate } = useSWR<BuyerDetail>(
    `/api/buyers/${buyerId}?date_from=${dateFrom}&date_to=${dateTo}`,
    fetcher,
  );

  function setQuickRange(days: number | "month" | "today") {
    const end = new Date();
    const toIso = end.toISOString().slice(0, 10);
    if (days === "today") {
      setDateFrom(toIso);
      setDateTo(toIso);
    } else if (days === "month") {
      setDateFrom(toIso.slice(0, 8) + "01");
      setDateTo(toIso);
    } else {
      const start = new Date(end.getTime() - (days - 1) * 86400000);
      setDateFrom(start.toISOString().slice(0, 10));
      setDateTo(toIso);
    }
  }

  async function patchBuyer(body: object) {
    await api(`/buyers/${buyerId}`, { method: "PATCH", body });
    mutate();
    onChanged();
  }

  const maxSpend = Math.max(
    1,
    ...(data?.daily_series.map((d) => Number(d.spend) || 0) ?? [1]),
  );

  return (
    <Modal title={data ? `Карточка юзера · ${data.name}` : "Карточка юзера"} onClose={onClose}>
      {!data ? (
        <p className="py-8 text-center text-muted">Завантаження карточки юзера…</p>
      ) : (
        <div className="max-h-[80vh] space-y-4 overflow-y-auto pr-1">
          {/* Верхній рядок: Пріоритет + Команда + Баланс кабінету */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-inset p-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => canWrite(user) && patchBuyer({ is_priority: !data.is_priority })}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] font-medium ${
                  data.is_priority
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line-strong bg-surface text-muted"
                }`}
              >
                {data.is_priority ? <CheckSquare size={14} /> : <Square size={14} />}
                Пріоритетний юзер
              </button>
              {canWrite(user) ? (
                <Select
                  className="h-8 text-[12px]"
                  value={data.team_id ?? ""}
                  onChange={(e) => patchBuyer({ team_id: e.target.value || null })}
                >
                  <option value="">Без команди</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
              ) : (
                <span className="text-[12px] text-muted">{data.team_name ?? "Без команди"}</span>
              )}
            </div>
            <div className="text-right text-[12px]">
              <span className="text-faint">Баланс команди: </span>
              <span className="font-mono font-bold text-success">
                {data.team_sheet_balance !== null ? money(data.team_sheet_balance) : "—"}
              </span>
            </div>
          </div>

          {/* Окремий блок балансів кабінетів FBM */}
          <div className="rounded-lg border border-line bg-surface p-3">
            <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-faint">
              <span>Баланс кабінету FBM Cards</span>
              <Wallet size={13} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              {data.fbm_accounts.map((acc) => (
                <div
                  key={acc.account_name}
                  className="flex items-center justify-between rounded border border-line bg-inset px-3 py-2 text-[12px]"
                >
                  <span className="text-muted">{acc.account_name}</span>
                  <span
                    className="font-mono font-bold"
                    style={{
                      color: acc.negative_balance
                        ? "var(--stage-off-fg)"
                        : acc.low_balance
                          ? "var(--warning)"
                          : "var(--success)",
                    }}
                  >
                    {acc.balance !== null ? money(acc.balance) : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Фільтри по періоду */}
          <div className="rounded-lg border border-line bg-surface p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[12px] font-semibold">
                <Calendar size={14} className="text-accent" /> Період спенду:
              </span>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setQuickRange("today")}
                  className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-0.5 text-[11px] hover:border-accent"
                >
                  Сьогодні
                </button>
                <button
                  type="button"
                  onClick={() => setQuickRange(7)}
                  className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-0.5 text-[11px] hover:border-accent"
                >
                  7 днів
                </button>
                <button
                  type="button"
                  onClick={() => setQuickRange(14)}
                  className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-0.5 text-[11px] hover:border-accent"
                >
                  14 днів
                </button>
                <button
                  type="button"
                  onClick={() => setQuickRange("month")}
                  className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-0.5 text-[11px] hover:border-accent"
                >
                  Цей місяць
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-faint">Від дати</label>
                <Input type="date" className="h-8 text-[12px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div>
                <label className="text-[11px] text-faint">До дати</label>
                <Input type="date" className="h-8 text-[12px]" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </div>

            {/* KPI спенду за вибраний період */}
            <div className="mt-3 grid grid-cols-3 gap-2">
              <div className="rounded border border-line bg-inset p-2.5">
                <div className="text-[11px] text-muted">Спенд за період</div>
                <div className="mt-0.5 font-mono text-[17px] font-bold text-accent">{money(data.period_spend)}</div>
              </div>
              <div className="rounded border border-line bg-inset p-2.5">
                <div className="text-[11px] text-muted">По таблиці (період)</div>
                <div className="mt-0.5 font-mono text-[17px] font-bold">{money(data.period_spend_sheet)}</div>
              </div>
              <div className="rounded border border-line bg-inset p-2.5">
                <div className="text-[11px] text-muted">Картки FBM (усього)</div>
                <div className="mt-0.5 font-mono text-[17px] font-bold text-success">{money(data.lifetime_spend_fbm)}</div>
              </div>
            </div>

            {/* Поденний графік спенду */}
            {data.daily_series.length > 0 && (
              <div className="mt-3">
                <div className="mb-1.5 text-[11px] text-faint">Динаміка спенду по днях ({data.date_from} — {data.date_to})</div>
                <div className="flex h-28 items-end gap-1 rounded border border-line bg-inset p-2.5">
                  {data.daily_series.map((d) => {
                    const val = Number(d.spend) || 0;
                    const h = val > 0 ? Math.max(8, Math.round((val / maxSpend) * 76)) : 3;
                    return (
                      <div key={d.date} className="flex flex-1 flex-col items-center justify-end gap-1" title={`${d.date}: ${money(d.spend)}`}>
                        <div
                          className="w-full rounded-t transition-all"
                          style={{
                            height: `${h}px`,
                            background: val > 0 ? "var(--accent)" : "var(--border-strong)",
                          }}
                        />
                        <span className="font-mono text-[9px] text-faint">{d.date.slice(8, 10)}.{d.date.slice(5, 7)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Картки FBM цього юзера */}
          <div className="rounded-lg border border-line bg-surface p-3">
            <div className="mb-2 flex items-center justify-between text-[12px] font-semibold">
              <span className="flex items-center gap-1.5">
                <CreditCard size={14} className="text-accent" /> Прив&apos;язані картки FBM ({data.cards.length})
              </span>
            </div>
            {data.cards.length === 0 ? (
              <p className="py-3 text-center text-[12px] text-faint">Карток FBM для цього юзера ще не знайдено</p>
            ) : (
              <div className="divide-y divide-divider text-[12px]">
                {data.cards.map((c) => (
                  <div key={c.card_id} className="flex items-center justify-between py-2">
                    <div>
                      <span className="font-mono font-semibold text-main">•• {c.last4}</span>{" "}
                      <span className="text-muted">{c.name}</span>
                      <div className="text-[11px] text-faint">
                        Рахунок: {c.account_name ?? "—"} ({c.account_balance !== null ? money(c.account_balance) : "—"})
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono font-bold text-accent">{money(c.spend)}</div>
                      <div className="font-mono text-[10px] text-muted">{c.status}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function AddBuyerModal({
  teams,
  onClose,
  onDone,
}: {
  teams: TeamItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState("");
  const [teamId, setTeamId] = useState(teams[0]?.id ?? "");
  const [isPriority, setIsPriority] = useState(false);
  const [accountsCount, setAccountsCount] = useState("");
  const [error, setError] = useState("");

  async function save() {
    setError("");
    try {
      await api("/buyers", {
        body: {
          name,
          team_id: teamId || null,
          is_priority: isPriority,
          accounts_count: accountsCount ? Number(accountsCount) : null,
        },
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title="Додати нового юзера (з перевіркою дублів)" onClose={onClose}>
      <Field label="Ім'я юзера (як у таблиці або FBM)" hint="Система автоматично перевірить відсутність дублів.">
        <Input autoFocus placeholder="Напр. WebAlex" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Команда">
        <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">Без команди</option>
          {teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Кількість кабінетів (T1)">
        <Input type="number" placeholder="Напр. 5" value={accountsCount} onChange={(e) => setAccountsCount(e.target.value)} />
      </Field>
      <label className="flex cursor-pointer items-center gap-2 text-[13px]">
        <input type="checkbox" checked={isPriority} onChange={(e) => setIsPriority(e.target.checked)} />
        <span>Пріоритетний юзер (підняти вгору списку)</span>
      </label>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant="primary" onClick={save} disabled={!name.trim()}>
          Додати юзера
        </Button>
      </div>
    </Modal>
  );
}

function TeamSheetModal({
  team,
  onClose,
  onDone,
}: {
  team: TeamItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(team?.name ?? "");
  const [sheetUrl, setSheetUrl] = useState(team?.sheet_url ?? "");
  const [sheetWebhookUrl, setSheetWebhookUrl] = useState(team?.sheet_webhook_url ?? "");
  const [sheetBalance, setSheetBalance] = useState(team?.sheet_balance ?? "");
  const [feePercent, setFeePercent] = useState(team?.fee_percent ?? "7.00");
  const [csvContent, setCsvContent] = useState("");
  const [showScript, setShowScript] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const scriptCode = `function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var maxCols = Math.max(sheet.getLastColumn(), 25);
    var maxRows = Math.max(sheet.getLastRow(), 30);
    var headerRow = sheet.getRange(1, 1, 1, maxCols).getValues()[0];
    
    // Карта дат (стовпці F+)
    var dateMap = {};
    for (var c = 0; c < headerRow.length; c++) {
      var val = String(headerRow[c]).trim();
      if (val) dateMap[val] = c + 1;
    }
    
    // Карта юзерів (стовпець A, починаючи з рядка 4)
    var buyerCol = sheet.getRange(1, 1, maxRows, 1).getValues();
    var buyerRowMap = {};
    for (var r = 3; r < buyerCol.length; r++) {
      var bName = String(buyerCol[r][0]).trim().toLowerCase();
      if (bName) buyerRowMap[bName] = r + 1;
    }
    
    var nextRow = sheet.getLastRow() + 1;
    var updated = 0;
    
    for (var i = 0; i < data.buyers.length; i++) {
      var b = data.buyers[i];
      var bLower = b.name.trim().toLowerCase();
      var rIdx = buyerRowMap[bLower];
      
      if (!rIdx) {
        sheet.getRange(nextRow, 1).setValue(b.name);
        if (b.accounts_count) sheet.getRange(nextRow, 5).setValue(b.accounts_count);
        rIdx = nextRow;
        buyerRowMap[bLower] = rIdx;
        nextRow++;
      } else if (b.accounts_count) {
        sheet.getRange(rIdx, 5).setValue(b.accounts_count);
      }
      
      for (var dt in b.spends) {
        var cIdx = dateMap[dt];
        if (!cIdx) {
          cIdx = sheet.getLastColumn() + 1;
          sheet.getRange(1, cIdx).setValue(dt);
          dateMap[dt] = cIdx;
        }
        sheet.getRange(rIdx, cIdx).setValue(parseFloat(b.spends[dt]) || 0);
        updated++;
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ status: "ok", updated: updated }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}`;

  function copyScript() {
    navigator.clipboard.writeText(scriptCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      let teamId = team?.id;
      if (!teamId) {
        const res = await api<{ id: string }>("/buyers/teams", {
          body: {
            name,
            sheet_url: sheetUrl || null,
            sheet_webhook_url: sheetWebhookUrl || null,
            sheet_balance: sheetBalance !== "" ? sheetBalance : null,
            fee_percent: feePercent || "7.00",
          },
        });
        teamId = res.id;
      } else {
        await api(`/buyers/teams/${teamId}`, {
          method: "PATCH",
          body: {
            name,
            sheet_url: sheetUrl || null,
            sheet_webhook_url: sheetWebhookUrl || null,
            sheet_balance: sheetBalance !== "" ? sheetBalance : null,
            fee_percent: feePercent || "7.00",
          },
        });
      }

      if (teamId && (csvContent.trim() || sheetUrl.trim())) {
        await api(`/buyers/teams/${teamId}/sync-sheet`, {
          method: "POST",
          body: csvContent.trim() ? { csv_content: csvContent } : {},
        });
      }
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={team ? `Таблиця команди · ${team.name}` : "Нова команда та Google-таблиця"} onClose={onClose}>
      <Field label="Назва команди">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Напр. CPA Samurai Team 298" />
      </Field>
      <Field
        label="Посилання на Google-таблицю (для читання)"
        hint="Дашборд зчитує баланс команди та структуру юзерів."
      >
        <Input
          placeholder="https://docs.google.com/spreadsheets/d/..."
          value={sheetUrl}
          onChange={(e) => setSheetUrl(e.target.value)}
        />
      </Field>
      
      <div className="rounded-lg border border-accent/30 bg-accent-soft/20 p-3 text-[12.5px]">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-accent">Автозапис спенду в Google-таблицю (без рук)</span>
          <button
            type="button"
            onClick={() => setShowScript(!showScript)}
            className="flex cursor-pointer items-center gap-1 font-mono text-[11.5px] text-accent underline"
          >
            <Code size={13} /> {showScript ? "Приховати інструкцію" : "Інструкція та код скрипта"}
          </button>
        </div>
        <p className="mt-1 text-muted text-[11.5px]">
          Вкажіть Webhook URL, і дашборд кожні 3–4 години сам вноситиме свіжий спенд з FBM у відповідні клітинки таблиці по юзерах і датах.
        </p>
        <div className="mt-2">
          <Input
            placeholder="https://script.google.com/macros/s/.../exec"
            value={sheetWebhookUrl}
            onChange={(e) => setSheetWebhookUrl(e.target.value)}
          />
        </div>

        {showScript && (
          <div className="mt-3 space-y-2 border-t border-divider pt-2.5">
            <div className="text-[11.5px] text-muted">
              <b>Як отримати цей Webhook за 1 хвилину:</b>
              <ol className="mt-1 list-decimal space-y-1 pl-4 text-[11px]">
                <li>У Google Таблиці натисніть <b>Розширення (Extensions) → Apps Script</b>.</li>
                <li>Вставте готовий код нижче та натисніть <b>Зберегти (Save)</b>.</li>
                <li>Натисніть <b>Розгорнути (Deploy) → Нове розгортання (New deployment)</b>.</li>
                <li>Виберіть тип: <b>Веб-програма (Web app)</b>. Доступ: <b>Усі (Anyone)</b>.</li>
                <li>Скопіюйте отриманий URL веб-програми та вставте його в поле вище!</li>
              </ol>
            </div>
            <div className="relative">
              <pre className="max-h-40 overflow-y-auto rounded bg-inset p-2 font-mono text-[10.5px] text-main">
                {scriptCode}
              </pre>
              <button
                type="button"
                onClick={copyScript}
                className="absolute right-2 top-2 rounded border border-line-strong bg-surface px-2 py-1 text-[11px] font-semibold text-accent shadow hover:bg-surface-hover cursor-pointer"
              >
                {copied ? "Скопійовано!" : "Скопіювати скрипт"}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 mt-2">
        <Field label="Поточний баланс команди ($)" hint="Якщо < $1000 або < $0 — прийде сповіщення">
          <Input
            type="number"
            step="0.01"
            placeholder="2283.48"
            value={sheetBalance}
            onChange={(e) => setSheetBalance(e.target.value)}
          />
        </Field>
        <Field label="Комісія команди (%)">
          <Input type="number" step="0.1" value={feePercent} onChange={(e) => setFeePercent(e.target.value)} />
        </Field>
      </div>

      <Field
        label="Або вставте скопійовані дані з таблиці (CSV)"
        hint="Опціонально для початкової синхронізації."
      >
        <textarea
          rows={2}
          className="w-full rounded-md border border-line-strong bg-inset p-2 font-mono text-[12px]"
          placeholder="Юзер,ID аккаунта,Спенд потрачено..."
          value={csvContent}
          onChange={(e) => setCsvContent(e.target.value)}
        />
      </Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant="primary" onClick={save} disabled={!name.trim() || busy}>
          {busy ? "Збереження…" : "Зберегти"}
        </Button>
      </div>
    </Modal>
  );
}
