"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { UserBadge } from "@/components/users/icon";
import { Empty, ErrorNote, Input, PageHeader, Select } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";

type DailyPoint = { date: string; done: number; assigned: number };
type PersonDaily = { date: string; count: number };
type CategoryStat = { category: string; open: number; done: number };

type StaffPerson = {
  id: string | null;
  name: string;
  icon?: string | null;
  role: string | null;
  active: boolean;
  open: number;
  inbox: number;
  todo: number;
  in_progress: number;
  review: number;
  stuck: number;
  urgent_open: number;
  assigned_period: number;
  done_period: number;
  rejected_period: number;
  success_rate: number | null;
  throughput: number | null;
  median_reaction_hours: number | null;
  median_work_hours: number | null;
  categories: CategoryStat[];
  daily_done: PersonDaily[];
};

type StaffReport = {
  date_from: string;
  date_to: string;
  team: {
    people: number;
    open: number;
    stuck: number;
    urgent_open: number;
    unassigned_open: number;
    assigned_period: number;
    done_period: number;
    rejected_period: number;
    success_rate: number | null;
    throughput: number | null;
    median_reaction_hours: number | null;
    median_work_hours: number | null;
    daily: DailyPoint[];
  };
  unassigned: StaffPerson;
  people: StaffPerson[];
};

const CATEGORY_LABEL: Record<string, string> = {
  issue_accounts: "Видача акаунтів",
  card_issue: "Картки",
  bm_share: "БМ / Піксель",
  account_check: "Перевірка акаунтів",
  procurement: "Закупівля",
  finance: "Фінанси",
  general: "Загальне",
};

function hoursLabel(value: number | null): string {
  if (value == null) return "—";
  if (value < 1) return `${Math.max(1, Math.round(value * 60))} хв`;
  const whole = Math.floor(value);
  const minutes = Math.round((value - whole) * 60);
  return minutes ? `${whole} год ${minutes} хв` : `${whole} год`;
}

function pct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}

function dayLabel(iso: string): string {
  return iso.slice(8);
}

function kyivStamp(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("uk-UA", {
    timeZone: "Europe/Kyiv",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type StaffKind = "done" | "created" | "open" | "rejected" | "stuck";

const KIND_LABEL: Record<StaffKind, string> = {
  done: "Виконані",
  created: "Нові",
  open: "Висять",
  rejected: "Відхилені",
  stuck: "Завислі",
};

const STATUS_LABEL: Record<string, string> = {
  inbox: "Вхідні",
  todo: "До виконання",
  in_progress: "В роботі",
  review: "На перевірці",
  done: "Виконано",
  rejected: "Відхилено",
};

type StaffTaskRow = {
  id: string;
  code: string;
  title: string;
  status: string;
  category: string;
  priority: string;
  buyer_name: string | null;
  telegram_chat_title: string | null;
  telegram_topic_title: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

type StaffTaskList = {
  date_from: string;
  date_to: string;
  kind: StaffKind;
  total: number;
  tasks: StaffTaskRow[];
};

export default function StaffReportPage() {
  const { user } = useMe();
  const today = new Date().toISOString().slice(0, 10);
  const [dateTo, setDateTo] = useState(today);
  const [dateFrom, setDateFrom] = useState(() => {
    const start = new Date();
    start.setDate(start.getDate() - 13);
    return start.toISOString().slice(0, 10);
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ personId: string | null; kind: StaffKind } | null>(null);
  const [taskQuery, setTaskQuery] = useState("");
  const [taskCategory, setTaskCategory] = useState("");

  const allowed = isAdmin(user);
  const url = `/api/tasks/staff-report?date_from=${dateFrom}&date_to=${dateTo}`;
  const { data, error } = useSWR<StaffReport>(allowed ? url : null, fetcher, { keepPreviousData: true });

  const selected = useMemo(
    () => data?.people.find((person) => person.id === selectedId) ?? data?.people[0] ?? null,
    [data, selectedId],
  );
  const drillPerson = useMemo(
    () => data?.people.find((person) => person.id === drill?.personId) ?? null,
    [data, drill],
  );
  const drillUrl = drill
    ? `/api/tasks/staff-report/tasks?kind=${drill.kind}&date_from=${dateFrom}&date_to=${dateTo}&assignee_id=${drill.personId || "none"}`
    : null;
  const { data: taskList, error: taskError } = useSWR<StaffTaskList>(allowed && drillUrl ? drillUrl : null, fetcher);
  const visibleTasks = useMemo(() => {
    const query = taskQuery.trim().toLowerCase();
    return (taskList?.tasks ?? []).filter((task) => {
      if (taskCategory && task.category !== taskCategory) return false;
      if (!query) return true;
      const blob = `${task.code} ${task.title} ${task.buyer_name || ""} ${task.telegram_topic_title || ""}`.toLowerCase();
      return blob.includes(query);
    });
  }, [taskList, taskQuery, taskCategory]);

  if (user && !allowed) {
    return (
      <>
        <PageHeader title="Успішність команди" />
        <div className="panel">
          <Empty>Цей звіт бачить тільки адміністратор.</Empty>
        </div>
      </>
    );
  }

  const maxDaily = Math.max(1, ...(data?.team.daily.flatMap((point) => [point.done, point.assigned]) ?? [1]));
  const maxLoad = Math.max(1, ...(data?.people.map((person) => person.done_period + person.open) ?? [1]));

  function setRange(days: number) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (days - 1));
    setDateTo(end.toISOString().slice(0, 10));
    setDateFrom(start.toISOString().slice(0, 10));
  }

  function openDrill(personId: string | null, kind: StaffKind) {
    setSelectedId(personId);
    setTaskQuery("");
    setTaskCategory("");
    setDrill((current) => (current?.personId === personId && current.kind === kind ? null : { personId, kind }));
  }

  return (
    <>
      <PageHeader
        title="Успішність команди"
        sub="Скільки задач на кожному, скільки закрито, що висить довше доби, і як швидко люди беруть роботу."
      />
      <ErrorNote>{error ? (error as Error).message : ""}</ErrorNote>

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="text-[11px] font-medium uppercase text-faint">
          Від
          <Input type="date" className="mt-1 h-9 w-40" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="text-[11px] font-medium uppercase text-faint">
          До
          <Input type="date" className="mt-1 h-9 w-40" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <div className="flex gap-1.5">
          {[7, 14, 30].map((days) => (
            <button
              key={days}
              type="button"
              onClick={() => setRange(days)}
              className="cursor-pointer rounded-md border border-line-strong bg-surface px-2.5 py-2 text-[12px] font-semibold text-muted hover:text-main"
            >
              {days} дн
            </button>
          ))}
        </div>
      </div>

      {data && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Висять зараз" value={data.team.open} hint={`${data.team.stuck} довше 24 год · термінових ${data.team.urgent_open}`} tone="text-amber-400" />
            <Kpi label="Виконано за період" value={data.team.done_period} hint={`нових за період ${data.team.assigned_period}`} tone="text-emerald-400" />
            <Kpi label="Успішність закриття" value={pct(data.team.success_rate)} hint="закриті проти відхилених" tone="text-accent" />
            <Kpi label="Без виконавця" value={data.team.unassigned_open} hint={`реакція ${hoursLabel(data.team.median_reaction_hours)} · у роботі ${hoursLabel(data.team.median_work_hours)}`} tone="text-rose-400" />
          </div>

          <section className="panel mb-5 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[15px] font-semibold text-main">Графік за період</h2>
              <div className="flex items-center gap-3 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1"><i className="inline-block size-2 rounded-sm bg-sky-400" /> Нові</span>
                <span className="inline-flex items-center gap-1"><i className="inline-block size-2 rounded-sm bg-emerald-400" /> Виконані</span>
              </div>
            </div>
            <div className="flex h-40 items-end gap-1">
              {data.team.daily.map((point) => {
                const assignedH = point.assigned ? Math.max(6, Math.round((point.assigned / maxDaily) * 100)) : 0;
                const doneH = point.done ? Math.max(6, Math.round((point.done / maxDaily) * 100)) : 0;
                return (
                  <div key={point.date} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={`${point.date}: нові ${point.assigned}, виконані ${point.done}`}>
                    <div className="flex h-32 w-full items-end justify-center gap-0.5">
                      <div className="w-[42%] rounded-t bg-sky-400/80" style={{ height: `${assignedH}%` }} />
                      <div className="w-[42%] rounded-t bg-emerald-400" style={{ height: `${doneH}%` }} />
                    </div>
                    <span className="text-[9px] text-faint">{dayLabel(point.date)}</span>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel mb-5 overflow-hidden">
            <div className="border-b border-divider px-4 py-3">
              <h2 className="text-[15px] font-semibold text-main">По працівниках</h2>
              <p className="text-[12px] text-muted">
                Нових — задачі, що з’явились у ці дати. Виконано — закриті в ці дати, навіть якщо задача прийшла раніше. Тому виконаних буває більше, ніж нових. Натисни цифру, щоб відкрити список.
              </p>
            </div>
            <div className="divide-y divide-divider">
              {data.people.map((person) => {
                const active = selected?.id === person.id;
                const doneW = (person.done_period / maxLoad) * 100;
                const openW = (person.open / maxLoad) * 100;
                return (
                  <div
                    key={person.id || person.name}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedId(person.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") setSelectedId(person.id);
                    }}
                    className={cn("flex w-full cursor-pointer flex-col gap-2 px-4 py-3 text-left hover:bg-surface-hover", active && "bg-accent/5")}
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <UserBadge userId={person.id || person.name} icon={person.icon} size={16} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13.5px] font-semibold text-main">{person.name}</div>
                        <div className="flex flex-wrap gap-x-2 text-[11px] text-faint">
                          <CountButton
                            label="нових"
                            value={person.assigned_period}
                            active={drill?.personId === person.id && drill.kind === "created"}
                            onClick={() => openDrill(person.id, "created")}
                          />
                          <CountButton
                            label="виконано"
                            value={person.done_period}
                            active={drill?.personId === person.id && drill.kind === "done"}
                            onClick={() => openDrill(person.id, "done")}
                          />
                          <CountButton
                            label="висять"
                            value={person.open}
                            active={drill?.personId === person.id && drill.kind === "open"}
                            onClick={() => openDrill(person.id, "open")}
                          />
                          {person.stuck > 0 && (
                            <CountButton
                              label="завислі"
                              value={person.stuck}
                              active={drill?.personId === person.id && drill.kind === "stuck"}
                              onClick={() => openDrill(person.id, "stuck")}
                            />
                          )}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-[16px] font-bold text-main">{pct(person.success_rate)}</div>
                        <div className="text-[10px] uppercase tracking-wider text-faint">успішність</div>
                      </div>
                    </div>
                    <div className="flex h-2.5 overflow-hidden rounded-full bg-inset">
                      <div className="h-full bg-emerald-400" style={{ width: `${doneW}%` }} />
                      <div className="h-full bg-amber-400" style={{ width: `${openW}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {drill && (
            <section className="panel mb-5 overflow-hidden">
              <div className="border-b border-divider px-4 py-3">
                <h2 className="text-[15px] font-semibold text-main">
                  {KIND_LABEL[drill.kind]} · {drillPerson?.name || "Не призначено"}
                </h2>
                <p className="text-[12px] text-muted">
                  {drill.kind === "open" || drill.kind === "stuck"
                    ? "Це поточні задачі, дати періоду на них не впливають."
                    : `За період ${dateFrom.split("-").reverse().join(".")}–${dateTo.split("-").reverse().join(".")}. Зміна дат зверху оновлює список.`}
                </p>
              </div>
              <div className="flex flex-wrap items-end gap-2 border-b border-divider px-4 py-3">
                {(Object.keys(KIND_LABEL) as StaffKind[]).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => setDrill({ personId: drill.personId, kind })}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1 text-[12px] font-semibold",
                      drill.kind === kind ? "border-accent bg-accent text-on-accent" : "border-line-strong text-muted hover:text-main",
                    )}
                  >
                    {KIND_LABEL[kind]}
                  </button>
                ))}
                <Select className="h-9 w-44" value={taskCategory} onChange={(event) => setTaskCategory(event.target.value)}>
                  <option value="">Усі категорії</option>
                  {Object.entries(CATEGORY_LABEL).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </Select>
                <Input
                  className="h-9 w-56"
                  placeholder="Код, назва, байєр, вітка"
                  value={taskQuery}
                  onChange={(event) => setTaskQuery(event.target.value)}
                />
              </div>
              {taskError && <ErrorNote>{(taskError as Error).message}</ErrorNote>}
              {visibleTasks.length === 0 ? (
                <div className="px-4 py-6">
                  <Empty>{taskList ? "За цим фільтром задач немає." : "Завантажую задачі…"}</Empty>
                </div>
              ) : (
                <div className="divide-y divide-divider">
                  <div className="px-4 py-2 text-[11px] text-faint">
                    Показано {visibleTasks.length} з {taskList?.total ?? visibleTasks.length}
                  </div>
                  {visibleTasks.map((task) => (
                    <div key={task.id} className="min-w-0 px-4 py-3">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                        <span className="font-mono text-[12px] font-bold text-accent">{task.code}</span>
                        <span className="min-w-0 text-[13.5px] font-semibold text-main [overflow-wrap:anywhere]">{task.title}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-faint">
                        <span>{STATUS_LABEL[task.status] || task.status}</span>
                        <span>{CATEGORY_LABEL[task.category] || task.category}</span>
                        {task.buyer_name && <span>Баєр: {task.buyer_name}</span>}
                        {task.telegram_topic_title && <span>Вітка: {task.telegram_topic_title}</span>}
                        <span>Впала {kyivStamp(task.created_at)}</span>
                        {task.completed_at && <span>Закрили {kyivStamp(task.completed_at)}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {selected && (
            <section className="panel p-4">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <UserBadge userId={selected.id || selected.name} icon={selected.icon} size={18} />
                <div>
                  <h2 className="text-[16px] font-semibold text-main">{selected.name}</h2>
                  <p className="text-[12px] text-muted">Деталі за обраний період і поточне навантаження.</p>
                </div>
              </div>
              <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Mini label="Вхідні" value={selected.inbox} />
                <Mini label="До виконання" value={selected.todo} />
                <Mini label="В роботі" value={selected.in_progress} />
                <Mini label="На перевірці" value={selected.review} />
                <Mini label="Термінові відкриті" value={selected.urgent_open} />
                <Mini label="Висять понад 24 год" value={selected.stuck} />
                <Mini label="Реакція" value={hoursLabel(selected.median_reaction_hours)} />
                <Mini label="Час у роботі" value={hoursLabel(selected.median_work_hours)} />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-faint">По категоріях</h3>
                  {selected.categories.length === 0 ? (
                    <p className="text-[12px] text-muted">За цей період категорій немає.</p>
                  ) : (
                    <div className="space-y-2">
                      {selected.categories.map((cat) => (
                        <div key={cat.category} className="flex items-center justify-between gap-3 text-[13px]">
                          <span className="min-w-0 truncate text-main">{CATEGORY_LABEL[cat.category] || cat.category}</span>
                          <span className="shrink-0 font-mono text-muted">відкрито {cat.open} · закрито {cat.done}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-faint">Закриття по днях</h3>
                  <div className="flex h-24 items-end gap-1">
                    {selected.daily_done.map((point) => {
                      const max = Math.max(1, ...selected.daily_done.map((item) => item.count));
                      const height = point.count ? Math.max(8, Math.round((point.count / max) * 100)) : 0;
                      return (
                        <div key={point.date} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={`${point.date}: ${point.count}`}>
                          <div className="flex h-16 w-full items-end">
                            <div className="w-full rounded-t bg-emerald-400" style={{ height: `${height}%` }} />
                          </div>
                          <span className="text-[9px] text-faint">{dayLabel(point.date)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}

function Kpi({ label, value, hint, tone }: { label: string; value: number | string; hint: string; tone: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">{label}</div>
      <div className={cn("mt-1 font-mono text-[28px] font-bold", tone)}>{value}</div>
      <div className="mt-1 text-[11.5px] text-muted">{hint}</div>
    </div>
  );
}

function CountButton({
  label,
  value,
  active,
  onClick,
}: {
  label: string;
  value: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className={cn(
        "cursor-pointer rounded px-1 font-semibold underline-offset-2 hover:underline",
        active ? "bg-accent/15 text-accent" : "text-main",
      )}
    >
      {label} {value}
    </button>
  );
}

function Mini({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-line bg-inset px-3 py-2">
      <div className="text-[10.5px] uppercase tracking-wider text-faint">{label}</div>
      <div className="mt-0.5 font-mono text-[16px] font-semibold text-main">{value}</div>
    </div>
  );
}
