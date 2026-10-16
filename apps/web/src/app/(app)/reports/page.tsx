"use client";
import {
  BarChart3,
  Calculator,
  CheckCircle2,
  FolderPlus,
  Plus,
  Target,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import type { ExpenseCategoryItem, ReportSummary } from "@/lib/types";
import { money } from "@/lib/utils";

const th = "px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export default function ReportsPage() {
  const { user } = useMe();
  const todayStr = new Date().toISOString().slice(0, 10);
  const monthStartStr = todayStr.slice(0, 8) + "01";

  const [dateFrom, setDateFrom] = useState(monthStartStr);
  const [dateTo, setDateTo] = useState(todayStr);
  const [feePercent, setFeePercent] = useState("7.0");
  const [includeBatches, setIncludeBatches] = useState(true);

  const [addingExpense, setAddingExpense] = useState(false);
  const [addingCategory, setAddingCategory] = useState(false);
  const [error, setError] = useState("");

  const url = `/api/reports/summary?date_from=${dateFrom}&date_to=${dateTo}&fee_percent=${encodeURIComponent(feePercent || "0")}&include_batches_cost=${includeBatches}`;
  const { data, mutate } = useSWR<ReportSummary>(url, fetcher, { keepPreviousData: true });

  async function removeExpense(id: string) {
    if (!confirm("Видалити цей запис витрати?")) return;
    setError("");
    try {
      await api(`/reports/expenses/${id}`, { method: "DELETE" });
      mutate();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const maxChartVal = Math.max(
    1,
    ...(data?.daily_chart.map((d) => Math.max(Number(d.revenue) || 0, Number(d.expenses) || 0)) ?? [1]),
  );

  return (
    <>
      <PageHeader
        title="Звітність та Точка прибутку"
        sub="Облік витрат за категоріями, формула відсотка комісії, розрахунок чистого прибутку та точки беззбитковості."
        right={
          canWrite(user) && (
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={() => setAddingCategory(true)}>
                <FolderPlus size={14} />+ Категорія витрат
              </Button>
              <Button size="sm" variant="primary" onClick={() => setAddingExpense(true)}>
                <Plus size={14} />+ Вписати витрату
              </Button>
            </div>
          )
        }
      />

      <ErrorNote>{error}</ErrorNote>

      {/* Панель фільтрів періоду та формули відсотка */}
      <Card className="mb-5 p-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase text-faint">Період від</label>
              <Input type="date" className="h-9 w-40" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium uppercase text-faint">Період до</label>
              <Input type="date" className="h-9 w-40" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 flex items-center gap-1 text-[11px] font-medium uppercase text-accent">
                <Calculator size={12} /> Формула комісії (% від спенду)
              </label>
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  step="0.5"
                  min="0"
                  max="100"
                  className="h-9 w-24 font-mono font-bold text-accent"
                  value={feePercent}
                  onChange={(e) => setFeePercent(e.target.value)}
                />
                {["5.0", "7.0", "10.0", "15.0", "20.0"].map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setFeePercent(p)}
                    className={`cursor-pointer rounded border px-2 py-1.5 font-mono text-[11.5px] ${
                      Number(feePercent) === Number(p)
                        ? "border-accent bg-accent font-bold text-on-accent"
                        : "border-line-strong bg-surface-hover text-muted hover:text-main"
                    }`}
                  >
                    {Number(p)}%
                  </button>
                ))}
              </div>
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-muted">
            <input
              type="checkbox"
              checked={includeBatches}
              onChange={(e) => setIncludeBatches(e.target.checked)}
            />
            <span>Враховувати закупівлю партій акаунтів у витратах автоматично</span>
          </label>
        </div>
      </Card>

      {!data ? (
        <Card className="p-10 text-center text-muted">Розрахунок звітності…</Card>
      ) : (
        <div className="space-y-5">
          {/* 1. Головні фінансові KPI */}
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <div className="panel kpi-glow p-5">
              <div className="text-[12.5px] text-muted">Загальний спенд за період</div>
              <div className="mt-2 font-mono text-[26px] font-bold">{money(data.total_spend)}</div>
              <div className="mt-1 text-[11.5px] text-faint">база для формули {data.fee_percent}%</div>
            </div>

            <div className="panel kpi-glow p-5">
              <div className="text-[12.5px] text-muted">Загальний дохід (Виручка)</div>
              <div className="mt-2 font-mono text-[26px] font-bold text-success">{money(data.total_revenue)}</div>
              <div className="mt-1 text-[11.5px] text-faint">
                комісія {money(data.commission_revenue)} + продажі {money(data.sales_revenue)}
              </div>
            </div>

            <div className="panel kpi-glow p-5">
              <div className="text-[12.5px] text-muted">Сумарні витрати</div>
              <div className="mt-2 font-mono text-[26px] font-bold text-warning">{money(data.total_expenses)}</div>
              <div className="mt-1 text-[11.5px] text-faint">
                вручну {money(data.manual_expenses)}
                {data.include_batches_cost ? ` + партії ${money(data.batches_cost)}` : ""}
              </div>
            </div>

            <div className="panel kpi-glow p-5">
              <div className="text-[12.5px] text-muted">Чистий прибуток</div>
              <div
                className="mt-2 font-mono text-[26px] font-bold"
                style={{ color: Number(data.net_profit) >= 0 ? "var(--success)" : "var(--stage-off-fg)" }}
              >
                {money(data.net_profit)}
              </div>
              <div className="mt-1 font-mono text-[11.5px] text-muted">ROI: {data.roi_percent}%</div>
            </div>
          </div>

          {/* 2. Блок «Точка прибутку» (Break-even Point) */}
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div
                  className="grid size-11 place-items-center rounded-lg border"
                  style={{
                    borderColor: data.breakeven.is_profitable ? "var(--success)" : "var(--accent)",
                    background: data.breakeven.is_profitable ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)",
                    color: data.breakeven.is_profitable ? "var(--success)" : "var(--accent)",
                  }}
                >
                  <Target size={22} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-[16px] font-bold">Точка прибутку (Break-even Point)</h2>
                    {data.breakeven.is_profitable ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-success/20 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-success">
                        <CheckCircle2 size={12} /> ТОЧКУ ПРОЙДЕНО (+{money(data.breakeven.surplus_or_deficit)})
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-warning/20 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-warning">
                        ДО ТОЧКИ ПРИБУТКУ: {money(data.breakeven.spend_remaining)} спенду
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[12.5px] text-muted">
                    Щоб перекрити витрати <b className="font-mono text-main">{money(data.total_expenses)}</b> при ставці{" "}
                    <b className="font-mono text-accent">{data.fee_percent}%</b>, необхідний обсяг спенду становить{" "}
                    <b className="font-mono text-main">{money(data.breakeven.spend_needed)}</b>.
                    {data.breakeven.reached_at_date && (
                      <> Вихід у чистий плюс зафіксовано: <b className="font-mono text-success">{data.breakeven.reached_at_date}</b>.</>
                    )}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <div className="text-[11px] uppercase text-faint">Покриття витрат доходом</div>
                <div className="font-mono text-[22px] font-bold text-accent">{data.breakeven.progress_pct}%</div>
              </div>
            </div>

            {/* Прогрес-бар до точки прибутку */}
            <div className="mt-4">
              <div className="h-3.5 w-full overflow-hidden rounded-full border border-line bg-inset">
                <div
                  className="h-full transition-all duration-300"
                  style={{
                    width: `${Math.min(100, Math.max(2, Number(data.breakeven.progress_pct) || 0))}%`,
                    background: data.breakeven.is_profitable
                      ? "linear-gradient(90deg, var(--accent), var(--success))"
                      : "var(--accent)",
                  }}
                />
              </div>
              <div className="mt-1.5 flex justify-between font-mono text-[11px] text-muted">
                <span>$0</span>
                <span>
                  Точка беззбитковості: {money(data.breakeven.spend_needed)} спенду ({money(data.breakeven.revenue_needed)} доходу)
                </span>
                <span>Поточний спенд: {money(data.breakeven.spend_current)}</span>
              </div>
            </div>
          </Card>

          {/* 3. Графік Доходів та Витрат + Розподіл по категоріях */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader
                title="Графік: Дохід vs Витрати по днях"
                icon={<TrendingUp size={16} />}
                right={
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="flex items-center gap-1 text-success">
                      <i className="size-2.5 rounded-sm bg-success" /> Дохід ({data.fee_percent}%)
                    </span>
                    <span className="flex items-center gap-1 text-warning">
                      <i className="size-2.5 rounded-sm bg-warning" /> Витрати
                    </span>
                  </div>
                }
              />
              <div className="p-5">
                {data.daily_chart.length === 0 ? (
                  <Empty>Немає даних за вибраний період</Empty>
                ) : (
                  <div className="flex h-52 items-end gap-1.5 rounded-lg border border-line bg-inset p-3 overflow-x-auto">
                    {data.daily_chart.map((d) => {
                      const rev = Number(d.revenue) || 0;
                      const exp = Number(d.expenses) || 0;
                      const hRev = rev > 0 ? Math.max(6, Math.round((rev / maxChartVal) * 150)) : 2;
                      const hExp = exp > 0 ? Math.max(6, Math.round((exp / maxChartVal) * 150)) : 2;
                      return (
                        <div
                          key={d.date}
                          className="flex min-w-[26px] flex-1 flex-col items-center justify-end gap-1"
                          title={`${d.date}\nСпенд: ${money(d.spend)}\nДохід: ${money(d.revenue)}\nВитрати: ${money(d.expenses)}\nКумулятивний прибуток: ${money(d.cumulative_profit)}`}
                        >
                          <div className="flex w-full items-end justify-center gap-0.5">
                            <div
                              className="w-1/2 rounded-t"
                              style={{
                                height: `${hRev}px`,
                                background: rev > 0 ? "var(--success)" : "var(--border-strong)",
                              }}
                            />
                            <div
                              className="w-1/2 rounded-t"
                              style={{
                                height: `${hExp}px`,
                                background: exp > 0 ? "var(--warning)" : "var(--border-strong)",
                              }}
                            />
                          </div>
                          <span className="font-mono text-[9.5px] text-faint">
                            {d.date.slice(8, 10)}.{d.date.slice(5, 7)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Структура витрат за категоріями"
                icon={<BarChart3 size={16} />}
                right={
                  canWrite(user) && (
                    <button
                      onClick={() => setAddingCategory(true)}
                      className="cursor-pointer text-[11.5px] text-accent hover:underline"
                    >
                      + Категорія
                    </button>
                  )
                }
              />
              <div className="space-y-3 p-5">
                {data.by_category.map((cat) => (
                  <div key={cat.category_id} className="space-y-1">
                    <div className="flex items-center justify-between text-[12.5px]">
                      <span className="flex items-center gap-2 font-medium">
                        <i className="size-2.5 rounded-full" style={{ background: cat.color }} />
                        {cat.name}
                      </span>
                      <span className="font-mono font-semibold">
                        {money(cat.amount)}{" "}
                        <span className="text-[11px] font-normal text-faint">({cat.percent}%)</span>
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-inset">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Number(cat.percent) || 0)}%`,
                          background: cat.color,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* 4. Таблиця записаних витрат */}
          <Card>
            <CardHeader
              title={`Журнал витрат за період (${data.expenses.length})`}
              right={
                canWrite(user) && (
                  <Button size="sm" variant="primary" onClick={() => setAddingExpense(true)}>
                    <Plus size={14} /> Вписати витрату
                  </Button>
                )
              }
            />
            {data.expenses.length === 0 ? (
              <Empty>Витрат за цей період ще не вписано. Натисніть «Вписати витрату», щоб додати запис.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-divider bg-inset/50">
                      <th className={th}>Дата</th>
                      <th className={th}>Категорія</th>
                      <th className={th}>Опис / Примітка</th>
                      <th className={th}>Хто вніс</th>
                      <th className={th}>Сума</th>
                      <th className={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expenses.map((e) => (
                      <tr key={e.id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                        <td className="px-4 py-3 font-mono text-muted">{e.spent_at}</td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-inset px-2.5 py-0.5 text-[12px]">
                            <i className="size-2 rounded-full" style={{ background: e.category_color }} />
                            {e.category_name}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-main">{e.description || "—"}</td>
                        <td className="px-4 py-3 text-muted">{e.created_by}</td>
                        <td className="px-4 py-3 font-mono font-bold text-warning">{money(e.amount)}</td>
                        <td className="px-4 py-3 text-right">
                          {canWrite(user) && (
                            <button
                              onClick={() => removeExpense(e.id)}
                              className="cursor-pointer rounded p-1 text-faint hover:bg-surface-hover hover:text-danger"
                              title="Видалити"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {addingExpense && (
        <AddExpenseModal
          categories={data?.categories ?? []}
          onClose={() => setAddingExpense(false)}
          onDone={() => {
            setAddingExpense(false);
            mutate();
          }}
        />
      )}

      {addingCategory && (
        <AddCategoryModal
          onClose={() => setAddingCategory(false)}
          onDone={() => {
            setAddingCategory(false);
            mutate();
          }}
        />
      )}
    </>
  );
}

function AddExpenseModal({
  categories,
  onClose,
  onDone,
}: {
  categories: ExpenseCategoryItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [spentAt, setSpentAt] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  async function save() {
    setError("");
    try {
      await api("/reports/expenses", {
        body: {
          category_id: categoryId,
          amount: Number(amount),
          spent_at: spentAt,
          description: description || null,
        },
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title="Вписати витрату" onClose={onClose}>
      <Field label="Категорія витрат">
        <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Сума ($)">
          <Input
            autoFocus
            type="number"
            step="0.01"
            min="0.01"
            placeholder="150.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </Field>
        <Field label="Дата витрати">
          <Input type="date" value={spentAt} onChange={(e) => setSpentAt(e.target.value)} />
        </Field>
      </div>
      <Field label="Опис / Коментар">
        <Input
          placeholder="Напр. Оплата мобільних проксі UA на місяць"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant="primary" onClick={save} disabled={!categoryId || !(Number(amount) > 0)}>
          Зберегти витрату
        </Button>
      </div>
    </Modal>
  );
}

function AddCategoryModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("#f59e0b");
  const [error, setError] = useState("");

  const palette = ["#f59e0b", "#38bdf8", "#10b981", "#a855f7", "#ec4899", "#ef4444", "#eab308", "#6366f1"];

  async function save() {
    setError("");
    try {
      await api("/reports/categories", { body: { name, color } });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title="Створити категорію витрат" onClose={onClose}>
      <Field label="Назва категорії">
        <Input autoFocus placeholder="Напр. Номери SMS / Верифікація" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Колір мітки">
        <div className="flex items-center gap-2 pt-1">
          {palette.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className={`size-7 cursor-pointer rounded-full border-2 transition ${
                color === c ? "scale-110 border-white" : "border-transparent opacity-70"
              }`}
              style={{ background: c }}
            />
          ))}
        </div>
      </Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant="primary" onClick={save} disabled={!name.trim()}>
          Створити
        </Button>
      </div>
    </Modal>
  );
}
