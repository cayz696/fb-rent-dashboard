"use client";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  CheckSquare,
  Clock,
  Copy,
  CreditCard,
  ExternalLink,
  Filter,
  FolderKanban,
  ListTodo,
  MessageSquare,
  MessageSquarePlus,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Send,
  Settings2,
  Share2,
  ShieldAlert,
  Sparkles,
  Trash2,
  UserCheck,
  Wallet,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Chip, Empty, ErrorNote, Field, Input, Modal, Select, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import type {
  TaskCategory,
  TaskChecklistItem,
  TaskPriority,
  TasksOverview,
  TaskStatus,
  TeamTaskItem,
  TelegramConversationThread,
  TelegramGroupItem,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORY_META: Record<TaskCategory, { label: string; color: string; bg: string; icon: typeof Wallet }> = {
  issue_accounts: {
    label: "Видача акаунтів",
    color: "#38bdf8",
    bg: "rgba(56, 189, 248, 0.12)",
    icon: Wallet,
  },
  card_issue: {
    label: "Картки FBM / Білінг",
    color: "#f43f5e",
    color_border: "rgba(244, 63, 94, 0.35)",
    bg: "rgba(244, 63, 94, 0.12)",
    icon: CreditCard,
  } as never,
  bm_share: {
    label: "БМ / Піксель / Доступ",
    color: "#a855f7",
    bg: "rgba(168, 85, 247, 0.12)",
    icon: Share2,
  },
  account_check: {
    label: "Чек / AdsPower / 2FA",
    color: "#f59e0b",
    bg: "rgba(245, 158, 11, 0.12)",
    icon: ShieldAlert,
  },
  procurement: {
    label: "Закупівля / Фарм",
    color: "#10b981",
    bg: "rgba(16, 185, 129, 0.12)",
    icon: FolderKanban,
  },
  finance: {
    label: "Фінанси / Таблиці",
    color: "#eab308",
    bg: "rgba(234, 179, 8, 0.12)",
    icon: Sparkles,
  },
  general: {
    label: "Загальна задача",
    color: "#94a3b8",
    bg: "rgba(148, 163, 184, 0.12)",
    icon: ListTodo,
  },
};

const PRIORITY_META: Record<TaskPriority, { label: string; fg: string; bg: string }> = {
  urgent: { label: "Терміново 🔥", fg: "#fb7185", bg: "rgba(244, 63, 94, 0.16)" },
  high: { label: "Високий", fg: "#fbbf24", bg: "rgba(245, 158, 11, 0.15)" },
  medium: { label: "Середній", fg: "#60a5fa", bg: "rgba(59, 130, 246, 0.14)" },
  low: { label: "Низький", fg: "#94a3b8", bg: "rgba(148, 163, 184, 0.12)" },
};

const STATUS_COLUMNS: { key: TaskStatus; title: string; subtitle: string; accent: string }[] = [
  { key: "inbox", title: "Вхідні з Telegram", subtitle: "Нові розібрані ШІ", accent: "#a855f7" },
  { key: "todo", title: "До виконання", subtitle: "У черзі команди", accent: "#38bdf8" },
  { key: "in_progress", title: "В роботі", subtitle: "Виконуються зараз", accent: "#f59e0b" },
  { key: "done", title: "Виконано", subtitle: "За добу · старші в архіві", accent: "#10b981" },
];

const SAMPLE_PROMPTS = [
  {
    label: "🚨 Деклайн картки FBM",
    sender: "WebLumi",
    name: "Igor WebLumi",
    text: "Хлопці, терміново! По WebLumi карта ••9443 б'є деклайн на $45, трафік зупинився, перевірте ліміт або заміність картку плз!",
  },
  {
    label: "📦 Запит на видачу аків",
    sender: "WebTxmmy",
    name: "Tommy Buyer",
    text: "Дайте 10 аків США з лімітом 250$ під вечірній залив, розшарте одразу на БМ 582910495827162",
  },
  {
    label: "🔗 Розшарка БМ і Пікселя",
    sender: "WebDD",
    name: "Denys WebDD",
    text: "Розшарте плз піксель і БМ 194857362518493 на кабінети FB-0002 та FB-0003 для WebDD",
  },
  {
    label: "🛡 Чекпоінт / Селфі в AdsPower",
    sender: "farm_lead",
    name: "Максим Фарм",
    text: "Профіль FB-0004 вилетів на селфі та просить код 2FA, зайдіть через AdsPower пройдіть чек",
  },
  {
    label: "💬 Звичайний шум чату (ШІ ігнорує)",
    sender: "WebLumi",
    name: "Igor WebLumi",
    text: "Ок, дякую бро 👍",
  },
];

export default function TasksPage() {
  const { user } = useMe();
  const router = useRouter();
  const editable = canWrite(user);

  const [activeTab, setActiveTab] = useState<"board" | "stream" | "settings">("board");
  const [viewMode, setViewModeState] = useState<"kanban" | "list">("kanban");
  const [boardScope, setBoardScope] = useState<"active" | "archive">("active");
  const [threadsOpen, setThreadsOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("fbr_tasks_view");
    if (saved === "list" || saved === "kanban") setViewModeState(saved);
  }, []);

  function setViewMode(mode: "kanban" | "list") {
    setViewModeState(mode);
    localStorage.setItem("fbr_tasks_view", mode);
  }

  // Фільтри дошки
  const [searchQ, setSearchQ] = useState("");
  const [filterCat, setFilterCat] = useState<string>("");
  const [filterPriority, setFilterPriority] = useState<string>("");
  const [filterTeam, setFilterTeam] = useState<string>("");
  const [filterAssignee, setFilterAssignee] = useState<string>("");

  // Модальні вікна
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [addingGroup, setAddingGroup] = useState(false);
  const [threadForTask, setThreadForTask] = useState<TelegramConversationThread | null>(null);
  const [showAllThreads, setShowAllThreads] = useState(false);
  const [promoteError, setPromoteError] = useState("");

  const queryParams = new URLSearchParams();
  if (filterCat) queryParams.set("category", filterCat);
  if (filterPriority) queryParams.set("priority", filterPriority);
  if (filterTeam) queryParams.set("team_id", filterTeam);
  if (filterAssignee) queryParams.set("assignee_id", filterAssignee);
  if (searchQ.trim()) queryParams.set("q", searchQ.trim());

  const { data, error, mutate } = useSWR<TasksOverview>(
    `/api/tasks/overview${queryParams.toString() ? `?${queryParams.toString()}` : ""}`,
    fetcher,
    { refreshInterval: 1000, dedupingInterval: 500 },
  );

  // Стан для ШІ-симулятора повідомлень із Telegram
  const [simGroupId, setSimGroupId] = useState<string>("");
  const [simSender, setSimSender] = useState("WebLumi");
  const [simSenderName, setSimSenderName] = useState("Igor WebLumi");
  const [simText, setSimText] = useState("");
  const [simForce, setSimForce] = useState(false);
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<Record<string, unknown> | null>(null);

  // Стан для підключення Telegram (Telethon)
  const [tgApiId, setTgApiId] = useState("");
  const [tgApiHash, setTgApiHash] = useState("");
  const [tgPhone, setTgPhone] = useState("");
  const [tgCode, setTgCode] = useState("");
  const [tgPassword, setTgPassword] = useState("");
  const [tgBusy, setTgBusy] = useState(false);
  const [tgNotice, setTgNotice] = useState("");
  const [tgError, setTgError] = useState("");
  const [discoveredDialogs, setDiscoveredDialogs] = useState<
    { chat_id: number; title: string; username: string | null; chat_type: string; already_added: boolean }[]
  >([]);

  // Стан для налаштувань ШІ
  const [aiProvider, setAiProvider] = useState<string>("");
  const [aiModel, setAiModel] = useState<string>("");
  const [aiApiKey, setAiApiKey] = useState<string>("");
  const [aiThreshold, setAiThreshold] = useState<number>(60);
  const [aiPrompt, setAiPrompt] = useState<string>("");
  const [aiSavedMsg, setAiSavedMsg] = useState("");

  const selectedTask = data?.tasks.find((t) => t.id === selectedTaskId) || null;

  const allTasks = data?.tasks ?? [];
  const isClosed = (t: TeamTaskItem) => t.status === "done" || t.status === "rejected";
  const activeTasks = allTasks.filter((t) => !isClosed(t));
  const archivedTasks = allTasks.filter(isClosed);
  const dayAgo = Date.now() - 24 * 3600 * 1000;
  const recentlyDone = allTasks.filter(
    (t) => t.status === "done" && Date.parse(t.completed_at || t.updated_at) >= dayAgo,
  );
  const tableTasks = boardScope === "archive" ? archivedTasks : activeTasks;
  const openThreads = (data?.threads ?? []).filter(
    (th) => !th.linked_task_id && th.resolution_state === "needs_action",
  );

  async function quickStatusChange(task: TeamTaskItem, newStatus: TaskStatus) {
    await api(`/tasks/${task.id}`, { method: "PATCH", body: { status: newStatus } });
    mutate();
  }

  async function quickAssignChange(task: TeamTaskItem, assigneeId: string) {
    await api(`/tasks/${task.id}`, {
      method: "PATCH",
      body: { assignee_id: assigneeId || null },
    });
    mutate();
  }

  async function handleConvertToRequest(task: TeamTaskItem) {
    const res = await api<{ ok: boolean; request_id: string; proposed_count: number }>(
      `/tasks/${task.id}/convert-to-request`,
      { method: "POST", body: {} },
    );
    await mutate();
    router.push(`/requests`);
    return res;
  }

  async function runSimulateMessage() {
    if (!simText.trim()) return;
    setSimLoading(true);
    setSimResult(null);
    try {
      const targetGroup = simGroupId || data?.groups[0]?.id || undefined;
      const res = await api<Record<string, unknown>>("/tasks/simulate-message", {
        method: "POST",
        body: {
          group_id: targetGroup,
          sender_username: simSender.trim() || "buyer",
          sender_name: simSenderName.trim() || "Баєр",
          raw_text: simText.trim(),
          force_create_task: simForce,
        },
      });
      setSimResult(res);
      setSimText("");
      mutate();
    } finally {
      setSimLoading(false);
    }
  }

  async function promoteLogToTask(logId: number) {
    setPromoteError("");
    try {
      await api(`/tasks/messages/${logId}/create-task`, { method: "POST", body: {} });
      mutate();
    } catch (e) {
      setPromoteError((e as Error).message || "Не вдалося створити задачу");
    }
  }

  async function handleSendTgCode() {
    setTgBusy(true);
    setTgError("");
    setTgNotice("");
    try {
      await api("/tasks/telegram/send-code", {
        method: "POST",
        body: { api_id: Number(tgApiId), api_hash: tgApiHash, phone: tgPhone },
      });
      setTgNotice("Код підтвердження надіслано у ваш Telegram! Введіть його нижче.");
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    } finally {
      setTgBusy(false);
    }
  }

  async function handleVerifyTgCode() {
    setTgBusy(true);
    setTgError("");
    setTgNotice("");
    try {
      await api("/tasks/telegram/verify-code", {
        method: "POST",
        body: { code: tgCode, password: tgPassword || undefined },
      });
      setTgNotice("Особистий Telegram-акаунт успішно підключено!");
      setTgCode("");
      setTgPassword("");
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    } finally {
      setTgBusy(false);
    }
  }

  async function handleDisconnectTg() {
    setTgBusy(true);
    try {
      await api("/tasks/telegram/disconnect", { method: "POST", body: {} });
      setDiscoveredDialogs([]);
      mutate();
    } finally {
      setTgBusy(false);
    }
  }

  async function handleLoadDialogs() {
    setTgBusy(true);
    setTgError("");
    try {
      const list = await api<typeof discoveredDialogs>("/tasks/telegram/dialogs");
      setDiscoveredDialogs(list);
    } catch (e) {
      setTgError((e as Error).message);
    } finally {
      setTgBusy(false);
    }
  }

  async function handleSyncTgNow() {
    setTgBusy(true);
    setTgError("");
    setTgNotice("");
    try {
      const res = await api<{ groups_checked: number; new_messages: number; tasks_created: number }>(
        "/tasks/telegram/sync",
        { method: "POST", body: {} },
      );
      setTgNotice(
        `Синхронізовано ${res.groups_checked} груп: нових повідомлень ${res.new_messages}, створено задач ${res.tasks_created}.`,
      );
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    } finally {
      setTgBusy(false);
    }
  }

  async function toggleGroupFlag(g: TelegramGroupItem, field: "is_monitored" | "auto_create_tasks") {
    if (!editable) return;
    try {
      await api(`/tasks/groups/${g.id}`, {
        method: "PATCH",
        body: { [field]: !g[field] },
      });
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    }
  }

  async function updateGroupBinding(g: TelegramGroupItem, payload: Record<string, unknown>) {
    if (!editable) return;
    try {
      await api(`/tasks/groups/${g.id}`, { method: "PATCH", body: payload });
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    }
  }

  async function handleDeleteGroup(g: TelegramGroupItem) {
    await api(`/tasks/groups/${g.id}?delete_tasks=true`, { method: "DELETE" });
    setDiscoveredDialogs((prev) =>
      prev.map((x) => (x.chat_id === g.chat_id ? { ...x, already_added: false } : x)),
    );
    mutate();
  }

  async function saveAiSettings() {
    if (!data || !editable) return;
    setAiSavedMsg("");
    try {
      await api("/tasks/ai-config", {
        method: "PUT",
        body: {
          provider: aiProvider || data.ai_config.provider,
          model: aiModel || data.ai_config.model,
          api_key: aiApiKey ? aiApiKey : undefined,
          confidence_threshold: aiThreshold || data.ai_config.confidence_threshold,
          system_prompt: aiPrompt || data.ai_config.system_prompt,
        },
      });
      setAiApiKey("");
      setAiSavedMsg("Налаштування ШІ збережено");
      mutate();
    } catch (e) {
      setTgError((e as Error).message);
    }
  }

  const stats = data?.stats;
  const tgState = data?.telegram_state;

  return (
    <div className="space-y-6">
      {error && <ErrorNote>Не вдалося завантажити задачник: {(error as Error).message}</ErrorNote>}
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[22px] font-bold tracking-tight sm:text-[28px]">Задачник Команди</h1>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-purple-500/40 bg-purple-500/10 px-3 py-0.5 text-[12px] font-semibold text-purple-300">
              <Sparkles size={13} /> Telegram MTProto + ШІ Контекст
            </span>
          </div>
          <p className="mt-1 text-[13px] text-muted">
            Автоматичний парсинг робочих груп у Telegram, розпізнавання контексту через ШІ та розподіл задач по команді й баєрах.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {tgState?.status === "connected" && editable && (
            <Button variant="ghost" onClick={handleSyncTgNow} disabled={tgBusy}>
              <RefreshCw size={14} className={tgBusy ? "animate-spin" : ""} />
              Синхронізувати ТГ
            </Button>
          )}
          <Button
            variant="ghost"
            onClick={() => setActiveTab("stream")}
            className="border-purple-500/40 text-purple-200 hover:bg-purple-500/15"
          >
            <Bot size={15} />
            Тест ШІ-Парсера
          </Button>
          {editable && (
            <Button variant="primary" onClick={() => setCreatingTask(true)}>
              <Plus size={15} />
              Нова задача
            </Button>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-6">
        <div className="panel p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>Вхідні з Telegram</span>
            <MessageSquare size={14} className="text-purple-400" />
          </div>
          <div className="mt-2 font-mono text-[26px] font-bold text-main">{stats?.inbox ?? 0}</div>
          <div className="mt-1 text-[11.5px] text-faint">Нові розібрані ШІ</div>
        </div>

        <div className="panel p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>В активній роботі</span>
            <Clock size={14} className="text-amber-400" />
          </div>
          <div className="mt-2 font-mono text-[26px] font-bold text-amber-400">
            {(stats?.todo ?? 0) + (stats?.in_progress ?? 0)}
          </div>
          <div className="mt-1 text-[11.5px] text-faint">
            Черга: {stats?.todo ?? 0} · В роботі: {stats?.in_progress ?? 0}
          </div>
        </div>

        <div className="panel p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>Термінові (Urgent)</span>
            <AlertTriangle size={14} className="text-rose-400" />
          </div>
          <div className="mt-2 font-mono text-[26px] font-bold text-rose-400">{stats?.urgent ?? 0}</div>
          <div className="mt-1 text-[11.5px] text-faint">Деклайни / стоп трафіку</div>
        </div>

        <div className="panel p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>Виконано</span>
            <CheckCircle2 size={14} className="text-emerald-400" />
          </div>
          <div className="mt-2 font-mono text-[26px] font-bold text-emerald-400">{stats?.done ?? 0}</div>
          <div className="mt-1 text-[11.5px] text-faint">Усього задач: {stats?.total ?? 0}</div>
        </div>

        <div className="panel p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>ШІ-Фільтр потоку</span>
            <Sparkles size={14} className="text-sky-400" />
          </div>
          <div className="mt-2 font-mono text-[26px] font-bold text-sky-400">{stats?.messages_total ?? 0}</div>
          <div className="mt-1 text-[11.5px] text-faint">Відсіяно шуму: {stats?.noise_filtered ?? 0} повід.</div>
        </div>

        <div
          onClick={() => setActiveTab("settings")}
          className="panel cursor-pointer p-4 transition hover:border-accent"
        >
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>Шлюз Telegram</span>
            <Radio size={14} className={tgState?.status === "connected" ? "text-emerald-400" : "text-purple-400"} />
          </div>
          <div className="mt-2 truncate text-[15px] font-bold text-main">
            {tgState?.status === "connected"
              ? tgState.account_name || tgState.phone
              : `${data?.groups.filter((g) => g.is_monitored).length ?? 0} груп активні`}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[11.5px] text-accent">
            <span>{tgState?.status === "connected" ? "MTProto Онлайн" : "Налаштувати акаунт →"}</span>
          </div>
        </div>
      </div>

      {/* Main Navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-divider pb-3">
        <div className="flex flex-wrap gap-2">
          <Chip active={activeTab === "board"} onClick={() => setActiveTab("board")}>
            <span className="flex items-center gap-1.5">
              <CheckSquare size={14} /> Дошка задач ({stats?.total ?? 0})
            </span>
          </Chip>
          <Chip active={activeTab === "stream"} onClick={() => setActiveTab("stream")}>
            <span className="flex items-center gap-1.5">
              <MessageSquarePlus size={14} /> Потік з Telegram & ШІ-Парсер ({stats?.messages_total ?? 0})
            </span>
          </Chip>
          <Chip active={activeTab === "settings"} onClick={() => setActiveTab("settings")}>
            <span className="flex items-center gap-1.5">
              <Settings2 size={14} /> Підключення Telegram & Групи ({data?.groups.length ?? 0})
            </span>
          </Chip>
        </div>

        {activeTab === "board" && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-line bg-inset p-1">
              {([
                ["active", `Активні (${activeTasks.length})`],
                ["archive", `Архів: виконані (${archivedTasks.length})`],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setBoardScope(key)}
                  className={cn(
                    "cursor-pointer rounded px-2.5 py-1 text-[12px] font-medium transition",
                    boardScope === key ? "bg-accent text-on-accent" : "text-muted hover:text-main",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {boardScope === "active" && (
              <div className="flex items-center gap-1 rounded-lg border border-line bg-inset p-1">
                {([
                  ["kanban", "Канбан"],
                  ["list", "Таблиця"],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setViewMode(key)}
                    className={cn(
                      "cursor-pointer rounded px-2.5 py-1 text-[12px] font-medium transition",
                      viewMode === key ? "bg-accent text-on-accent" : "text-muted hover:text-main",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          TAB 1: ДОШКА ЗАДАЧ (КАНБАН / СПИСОК) + КОНТЕКСТ ОСТАННІХ ДІАЛОГІВ ТГ
         ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === "board" && (
        <div className="space-y-5">
          {/* Блок: Останні повідомлення та контекст по гілках Telegram для свідомої постановки задач */}
          {boardScope === "active" && (data?.threads?.length ?? 0) > 0 && (
            <div className="panel space-y-3.5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Bot size={18} className="text-purple-400" />
                  <div>
                    <h2 className="text-[15px] font-semibold text-main">
                      Розмови без задачі: {openThreads.length}
                    </h2>
                    <p className="text-[12px] text-muted">
                      Переписки з чатів за 3 дні, де клієнт щось попросив, а задачі ще немає. Відкрийте, перегляньте і за потреби натисніть «Поставити задачу».
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {threadsOpen && (
                    <Button size="sm" variant="ghost" onClick={() => setShowAllThreads((v) => !v)}>
                      {showAllThreads ? "Лише без задачі" : `Усі розмови (${data?.threads.length ?? 0})`}
                    </Button>
                  )}
                  <Button size="sm" variant={threadsOpen ? "ghost" : "primary"} onClick={() => setThreadsOpen((v) => !v)}>
                    {threadsOpen ? "Згорнути" : "Переглянути"}
                  </Button>
                </div>
              </div>

              {threadsOpen && (
              <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
                {(showAllThreads ? data?.threads ?? [] : openThreads).length === 0 && (
                  <Empty>Усі розмови вже мають задачу або вирішені в чаті</Empty>
                )}
                {(showAllThreads ? data?.threads ?? [] : openThreads).map((th) => {
                  const cat = CATEGORY_META[th.category] || CATEGORY_META.general;
                  const stateStyle =
                    th.resolution_state === "needs_action"
                      ? { label: "Потребує уваги / задачі", fg: "#fbbf24", bg: "rgba(245, 158, 11, 0.14)" }
                      : th.resolution_state === "waiting_client"
                        ? { label: "Очікує клієнта", fg: "#60a5fa", bg: "rgba(59, 130, 246, 0.14)" }
                        : { label: "Вирішено саппортом у чаті", fg: "#34d399", bg: "rgba(16, 185, 129, 0.14)" };

                  return (
                    <div
                      key={th.thread_key}
                      className="flex flex-col justify-between gap-3 rounded-xl border border-line-strong bg-inset/70 p-3.5"
                    >
                      <div className="space-y-2.5">
                        {/* Шапка діалогу */}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
                            <span className="rounded bg-surface px-2 py-0.5 font-semibold text-main">
                              💬 {th.chat_title}
                              {th.topic_id ? ` · Гілка #${th.topic_id}` : ""}
                            </span>
                            <span className="font-mono font-semibold text-accent">{th.client_display}</span>
                          </div>
                          <span
                            className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                            style={{ color: stateStyle.fg, background: stateStyle.bg }}
                          >
                            {stateStyle.label}
                          </span>
                        </div>

                        {/* ШІ-висновок по всій гілці */}
                        <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[13.5px] font-semibold text-main">{th.suggested_title}</span>
                            <span
                              className="shrink-0 rounded px-2 py-0.5 text-[10.5px] font-medium"
                              style={{ color: cat.color, background: cat.bg }}
                            >
                              {cat.label}
                            </span>
                          </div>
                          <div className="mt-1 text-[12px] text-muted">{th.context_summary}</div>
                        </div>

                        {/* Стрічка останніх повідомлень цього діалогу */}
                        <div className="max-h-44 space-y-1.5 overflow-y-auto rounded-lg border border-line bg-surface p-2.5 text-[12px]">
                          <div className="text-[10.5px] font-semibold uppercase tracking-wider text-faint">
                            Останні повідомлення діалогу ({th.messages_count}):
                          </div>
                          {th.messages.slice(-6).map((m) => (
                            <div
                              key={m.id}
                              className={cn(
                                "rounded px-2.5 py-1.5",
                                m.is_support
                                  ? "border-l-2 border-emerald-500/60 bg-emerald-500/5 text-muted"
                                  : "border-l-2 border-accent bg-inset text-main",
                              )}
                            >
                              <div className="flex items-center justify-between text-[10.5px]">
                                <span className={cn("font-semibold", m.is_support ? "text-emerald-400" : "text-accent")}>
                                  {m.is_support
                                    ? `🛠 Саппорт (${m.sender_name || m.sender_username || "SP"})`
                                    : `👤 Клієнт (@${m.sender_username || m.sender_name || "user"})`}
                                </span>
                                {m.sent_at && (
                                  <span className="font-mono text-faint">
                                    {new Date(m.sent_at).toLocaleTimeString("uk-UA", { timeZone: "Europe/Kyiv",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })}
                                  </span>
                                )}
                              </div>
                              <div className="mt-0.5 whitespace-pre-wrap break-words text-[12px] leading-snug">
                                {m.raw_text.length > 220 ? m.raw_text.slice(0, 220) + "…" : m.raw_text}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Нижня панель дій по діалогу */}
                      <div className="flex items-center justify-between gap-2 border-t border-divider pt-2">
                        <div className="flex flex-wrap gap-1.5 text-[11px]">
                          {th.buyer_tag && (
                            <span className="rounded border border-line-strong bg-surface px-2 py-0.5 font-mono text-main">
                              👤 {th.buyer_tag}
                            </span>
                          )}
                          {th.ad_account_ids.slice(0, 2).map((aid) => (
                            <span
                              key={aid}
                              className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-amber-300"
                            >
                              ID: {aid}
                            </span>
                          ))}
                        </div>

                        {th.linked_task_id && th.linked_task_code ? (
                          <button
                            onClick={() => setSelectedTaskId(th.linked_task_id)}
                            className="cursor-pointer rounded-md border border-accent bg-accent/15 px-3 py-1 font-mono text-[12px] font-bold text-accent hover:bg-accent/25"
                          >
                            Відкрити {th.linked_task_code} →
                          </button>
                        ) : (
                          editable && (
                            <Button size="sm" variant="primary" onClick={() => setThreadForTask(th)}>
                              <Plus size={14} /> Поставити задачу з контексту
                            </Button>
                          )
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              )}
            </div>
          )}

          {/* Панель фільтрів */}
          <div className="panel flex flex-wrap items-center gap-3 p-3.5">
            <div className="relative w-full min-w-0 flex-1 sm:min-w-[220px]">
              <Search size={14} className="pointer-events-none absolute left-3 top-2.5 text-faint" />
              <Input
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="Пошук по коду (TSK-0001), тексту, баєру, картці ••9443..."
                className="pl-8"
              />
            </div>

            <Select value={filterCat} onChange={(e) => setFilterCat(e.target.value)} className="w-full min-w-0 sm:w-auto sm:min-w-[175px]">
              <option value="">Усі категорії</option>
              {Object.entries(CATEGORY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>

            <Select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value)}
              className="w-full min-w-0 sm:w-auto sm:min-w-[150px]"
            >
              <option value="">Будь-який пріоритет</option>
              <option value="urgent">Терміново 🔥</option>
              <option value="high">Високий</option>
              <option value="medium">Середній</option>
              <option value="low">Низький</option>
            </Select>

            <Select value={filterTeam} onChange={(e) => setFilterTeam(e.target.value)} className="w-full min-w-0 sm:w-auto sm:min-w-[175px]">
              <option value="">Усі команди</option>
              {data?.teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>

            <Select
              value={filterAssignee}
              onChange={(e) => setFilterAssignee(e.target.value)}
              className="w-full min-w-0 sm:w-auto sm:min-w-[165px]"
            >
              <option value="">Усі виконавці</option>
              {data?.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>

            {(searchQ || filterCat || filterPriority || filterTeam || filterAssignee) && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setSearchQ("");
                  setFilterCat("");
                  setFilterPriority("");
                  setFilterTeam("");
                  setFilterAssignee("");
                }}
              >
                Скинути
              </Button>
            )}
          </div>

          {/* КАНБАН-ДОШКА */}
          {boardScope === "active" && viewMode === "kanban" ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-4">
              {STATUS_COLUMNS.map((col) => {
                const colTasks =
                  col.key === "done"
                    ? [...allTasks.filter((t) => t.status === "review"), ...recentlyDone]
                    : allTasks.filter((t) => t.status === col.key);
                return (
                  <div key={col.key} className="flex flex-col rounded-xl border border-line bg-inset/60 p-3">
                    <div className="mb-3 flex items-center justify-between px-1">
                      <div className="flex items-center gap-2">
                        <span className="size-2.5 rounded-full" style={{ background: col.accent }} />
                        <div>
                          <div className="text-[14px] font-semibold text-main">{col.title}</div>
                          <div className="text-[11px] text-faint">{col.subtitle}</div>
                        </div>
                      </div>
                      <span className="rounded-full border border-line-strong bg-surface px-2.5 py-0.5 font-mono text-[12px] font-semibold text-muted">
                        {colTasks.length}
                      </span>
                    </div>

                    <div className="flex flex-1 flex-col gap-3">
                      {colTasks.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-line py-10 text-center text-[12px] text-faint">
                          Немає задач у цій колонці
                        </div>
                      ) : (
                        colTasks.map((task) => {
                          const cat = CATEGORY_META[task.category] || CATEGORY_META.general;
                          const prio = PRIORITY_META[task.priority] || PRIORITY_META.medium;
                          const CatIcon = cat.icon;
                          const ctx = task.ai_context || {};

                          return (
                            <div
                              key={task.id}
                              onClick={() => setSelectedTaskId(task.id)}
                              className="group relative flex cursor-pointer flex-col gap-2.5 rounded-lg border border-line-strong bg-surface p-3.5 transition hover:border-accent hover:shadow-[0_6px_24px_rgba(0,0,0,0.45)]"
                            >
                              {/* Top row: Code + Priority + AI confidence */}
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-mono text-[11.5px] font-bold text-accent">{task.code}</span>
                                  {task.source === "telegram" && (
                                    <span className="inline-flex items-center gap-1 rounded bg-purple-500/15 px-1.5 py-0.5 text-[10.5px] font-medium text-purple-300">
                                      <Bot size={11} /> ШІ {ctx.confidence ? `${ctx.confidence}%` : ""}
                                    </span>
                                  )}
                                </div>
                                <span
                                  className="rounded px-2 py-0.5 text-[11px] font-semibold"
                                  style={{ color: prio.fg, background: prio.bg }}
                                >
                                  {prio.label}
                                </span>
                              </div>

                              {/* Category pill */}
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span
                                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11.5px] font-medium"
                                  style={{ color: cat.color, background: cat.bg }}
                                >
                                  <CatIcon size={12} />
                                  {cat.label}
                                </span>
                                {task.buyer_name && (
                                  <span className="rounded-md border border-line-strong bg-surface-hover px-2 py-0.5 font-mono text-[11px] font-semibold text-main">
                                    👤 {task.buyer_name}
                                  </span>
                                )}
                              </div>

                              {/* Title */}
                              <div className="text-[14px] font-semibold leading-snug text-main group-hover:text-accent-light">
                                {task.title}
                              </div>

                              {/* Останні повідомлення діалогу або оригінальна цитата з Telegram */}
                              {ctx.thread_messages && ctx.thread_messages.length > 0 ? (
                                <div className="space-y-1 rounded-md border border-line bg-inset p-2 text-[11.5px]">
                                  <div className="text-[10px] font-semibold uppercase tracking-wider text-faint">
                                    Контекст діалогу ({ctx.thread_messages.length} повід.):
                                  </div>
                                  {ctx.thread_messages.slice(-3).map((tm) => (
                                    <div key={tm.id} className="line-clamp-2 leading-snug">
                                      <span
                                        className={cn(
                                          "font-semibold",
                                          tm.is_support ? "text-emerald-400" : "text-accent",
                                        )}
                                      >
                                        {tm.is_support ? "🛠 Саппорт: " : `👤 @${tm.sender_username || tm.sender_name || "Клієнт"}: `}
                                      </span>
                                      <span className="text-muted">{tm.raw_text}</span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                task.raw_source_text && (
                                  <div className="line-clamp-3 whitespace-pre-wrap rounded border-l-2 border-purple-500/50 bg-inset px-2.5 py-1.5 text-[12px] italic text-muted">
                                    «{task.raw_source_text}»
                                  </div>
                                )
                              )}

                              {/* Extracted AI entities tags */}
                              <div className="flex flex-wrap gap-1.5 text-[11px]">
                                {ctx.card_last4?.map((c4) => (
                                  <span
                                    key={c4}
                                    className="rounded border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 font-mono text-rose-300"
                                  >
                                    💳 ••{c4}
                                  </span>
                                ))}
                                {ctx.account_codes?.map((ac) => (
                                  <span
                                    key={ac}
                                    className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-amber-300"
                                  >
                                    🛡 {ac}
                                  </span>
                                ))}
                                {ctx.bm_id && (
                                  <span className="rounded border border-purple-500/30 bg-purple-500/10 px-1.5 py-0.5 font-mono text-purple-300">
                                    BM: {ctx.bm_id.slice(0, 10)}…
                                  </span>
                                )}
                                {ctx.qty && (
                                  <span className="rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 font-mono text-sky-300">
                                    {ctx.qty} шт {ctx.geo ? `· ${ctx.geo}` : ""} {ctx.limit ? `· $${ctx.limit}` : ""}
                                  </span>
                                )}
                              </div>

                              {/* Telegram Group + Sender info */}
                              {task.telegram_chat_title && (
                                <div className="flex items-center justify-between text-[11px] text-faint">
                                  <span className="truncate">💬 {task.telegram_chat_title}</span>
                                  {task.telegram_sender && (
                                    <span className="ml-2 shrink-0 font-mono text-muted">{task.telegram_sender}</span>
                                  )}
                                </div>
                              )}

                              {/* Checklist progress */}
                              {task.checklist_total > 0 && (
                                <div className="space-y-1">
                                  <div className="flex items-center justify-between text-[11px] text-muted">
                                    <span>Етапи виконання</span>
                                    <span className="font-mono">
                                      {task.checklist_done}/{task.checklist_total}
                                    </span>
                                  </div>
                                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-inset">
                                    <div
                                      className="h-full rounded-full bg-accent transition-all"
                                      style={{
                                        width: `${Math.round((task.checklist_done / task.checklist_total) * 100)}%`,
                                      }}
                                    />
                                  </div>
                                </div>
                              )}

                              {/* Bottom controls: Assignee + Quick Action */}
                              <div
                                className="mt-1 flex items-center justify-between gap-2 border-t border-divider pt-2.5"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <select
                                  value={task.assignee_id || ""}
                                  onChange={(e) => quickAssignChange(task, e.target.value)}
                                  className="max-w-[140px] truncate rounded border border-line bg-inset px-2 py-1 text-[11.5px] text-muted outline-none focus:border-accent"
                                >
                                  <option value="">Не призначено</option>
                                  {data?.users.map((u) => (
                                    <option key={u.id} value={u.id}>
                                      👤 {u.name}
                                    </option>
                                  ))}
                                </select>

                                <div className="flex items-center gap-1">
                                  {task.category === "issue_accounts" && !task.linked_request_id && (
                                    <button
                                      onClick={() => handleConvertToRequest(task)}
                                      title="Створити Заявку на видачу та автоматично підібрати Ready-акаунти"
                                      className="cursor-pointer rounded border border-sky-500/40 bg-sky-500/15 px-2 py-1 text-[11px] font-semibold text-sky-300 hover:bg-sky-500/25"
                                    >
                                      → У Заявку
                                    </button>
                                  )}
                                  {task.status === "inbox" && (
                                    <button
                                      onClick={() => quickStatusChange(task, "in_progress")}
                                      className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-1 text-[11px] font-medium text-main hover:border-accent"
                                    >
                                      В роботу →
                                    </button>
                                  )}
                                  {task.status === "todo" && (
                                    <button
                                      onClick={() => quickStatusChange(task, "in_progress")}
                                      className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-1 text-[11px] font-medium text-main hover:border-accent"
                                    >
                                      Почати →
                                    </button>
                                  )}
                                  {task.status === "in_progress" && (
                                    <button
                                      onClick={() => quickStatusChange(task, "done")}
                                      className="cursor-pointer rounded border border-emerald-500/40 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-300 hover:bg-emerald-500/25"
                                    >
                                      ✓ Готово
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* ТАБЛИЧНИЙ ВИД */
            <Card className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="border-b border-divider text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-3">Код</th>
                    <th className="px-4 py-3">Задача / Джерело Telegram</th>
                    <th className="px-4 py-3">Категорія</th>
                    <th className="px-4 py-3">Баєр / Команда</th>
                    <th className="px-4 py-3">Пріоритет</th>
                    <th className="px-4 py-3">Чекліст</th>
                    <th className="px-4 py-3">Виконавець</th>
                    <th className="px-4 py-3">Статус</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {tableTasks.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center text-muted">
                        {boardScope === "archive" ? "В архіві поки порожньо" : "Активних задач немає"}
                      </td>
                    </tr>
                  )}
                  {tableTasks.map((task) => {
                    const cat = CATEGORY_META[task.category] || CATEGORY_META.general;
                    const prio = PRIORITY_META[task.priority] || PRIORITY_META.medium;
                    return (
                      <tr
                        key={task.id}
                        onClick={() => setSelectedTaskId(task.id)}
                        className="cursor-pointer transition hover:bg-surface-hover"
                      >
                        <td className="px-4 py-3 font-mono font-bold text-accent">{task.code}</td>
                        <td className="max-w-md px-4 py-3">
                          <div className="font-semibold text-main">{task.title}</div>
                          {task.telegram_chat_title && (
                            <div className="mt-0.5 truncate text-[11.5px] text-faint">
                              💬 {task.telegram_chat_title} · {task.telegram_sender}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className="inline-flex rounded px-2 py-0.5 text-[11.5px] font-medium"
                            style={{ color: cat.color, background: cat.bg }}
                          >
                            {cat.label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {task.buyer_name ? (
                            <span className="font-mono font-semibold text-main">{task.buyer_name}</span>
                          ) : (
                            <span className="text-faint">—</span>
                          )}
                          {task.team_name && <div className="text-[11px] text-faint">{task.team_name}</div>}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className="rounded px-2 py-0.5 text-[11px] font-semibold"
                            style={{ color: prio.fg, background: prio.bg }}
                          >
                            {prio.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-[12px] text-muted">
                          {task.checklist_done}/{task.checklist_total}
                        </td>
                        <td className="px-4 py-3 text-muted">{task.assignee_name || "Не призначено"}</td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <Select
                            value={task.status}
                            onChange={(e) => quickStatusChange(task, e.target.value as TaskStatus)}
                            className="h-8 text-[12px]"
                          >
                            <option value="inbox">Вхідні (ТГ)</option>
                            <option value="todo">До виконання</option>
                            <option value="in_progress">В роботі</option>
                            <option value="done">Виконано</option>
                            <option value="rejected">Відхилено</option>
                          </Select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════
          TAB 2: ПОТІК ПОВІДОМЛЕНЬ З TELEGRAM & ШІ-СИМУЛЯТОР
         ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === "stream" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          {/* Ліва колонка: Тестер / Симулятор ШІ-Парсера */}
          <div className="space-y-4 xl:col-span-5">
            <Card>
              <CardHeader
                title="ШІ-Парсер контексту повідомлень"
                icon={<Bot size={17} className="text-purple-400" />}
              />
              <div className="space-y-4 p-5">
                <p className="text-[12.5px] text-muted">
                  Вставте будь-яке повідомлення з робочої Telegram-групи (або оберіть готовий приклад нижче), щоб перевірити, як ШІ розпізнає баєра, картку FBM, коди акаунтів, БМ та формує задачу з чеклістом.
                </p>

                <div className="space-y-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">
                    Швидкі приклади з чатів:
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {SAMPLE_PROMPTS.map((sp) => (
                      <button
                        key={sp.label}
                        onClick={() => {
                          setSimSender(sp.sender);
                          setSimSenderName(sp.name);
                          setSimText(sp.text);
                        }}
                        className="cursor-pointer rounded-md border border-line-strong bg-surface-hover px-2.5 py-1 text-[11.5px] text-main transition hover:border-accent"
                      >
                        {sp.label}
                      </button>
                    ))}
                  </div>
                </div>

                <Field label="Telegram-група (джерело)">
                  <Select value={simGroupId} onChange={(e) => setSimGroupId(e.target.value)}>
                    {data?.groups.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.title} {g.team_name ? `(${g.team_name})` : ""}
                      </option>
                    ))}
                  </Select>
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Нікнейм у ТГ (@username)">
                    <Input value={simSender} onChange={(e) => setSimSender(e.target.value)} placeholder="WebLumi" />
                  </Field>
                  <Field label="Ім'я відправника">
                    <Input
                      value={simSenderName}
                      onChange={(e) => setSimSenderName(e.target.value)}
                      placeholder="Igor Buyer"
                    />
                  </Field>
                </div>

                <Field label="Текст повідомлення у групі">
                  <Textarea
                    rows={4}
                    value={simText}
                    onChange={(e) => setSimText(e.target.value)}
                    placeholder="Наприклад: Хлопці, по WebLumi карта ••9443 б'є деклайн на 20$, заміність терміново плз!"
                  />
                </Field>

                <label className="flex items-center gap-2 text-[12.5px] text-muted">
                  <input
                    type="checkbox"
                    checked={simForce}
                    onChange={(e) => setSimForce(e.target.checked)}
                    className="size-4 accent-purple-500"
                  />
                  Примусово створити задачу (навіть якщо ШІ вважає це звичайним повідомленням)
                </label>

                <Button
                  variant="primary"
                  onClick={runSimulateMessage}
                  disabled={simLoading || !simText.trim()}
                  className="w-full"
                >
                  <Sparkles size={15} />
                  {simLoading ? "ШІ аналізує контекст..." : "Проаналізувати через ШІ та відправити в потік"}
                </Button>

                {simResult && (
                  <div className="space-y-2 rounded-lg border border-purple-500/40 bg-purple-500/10 p-3.5 text-[12.5px]">
                    <div className="flex items-center justify-between font-semibold text-purple-200">
                      <span>Результат ШІ-аналізу:</span>
                      {simResult.task_created ? (
                        <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-emerald-300">
                          Створено {String(simResult.task_code)}
                        </span>
                      ) : (
                        <span className="rounded bg-slate-500/20 px-2 py-0.5 text-slate-300">
                          Відсіяно як шум чату
                        </span>
                      )}
                    </div>
                    <div className="text-main">
                      <strong>Вердикт:</strong>{" "}
                      {String((simResult.ai_result as Record<string, unknown>)?.title || "")}
                    </div>
                    <div className="text-muted">
                      {String((simResult.ai_result as Record<string, unknown>)?.reasoning || "")}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Права колонка: Живий потік повідомлень з Telegram */}
          <div className="xl:col-span-7">
            <Card>
              <CardHeader
                title="Потік повідомлень із робочих груп Telegram"
                icon={<MessageSquare size={17} className="text-sky-400" />}
                right={
                  <span className="font-mono text-[12px] text-muted">
                    Одразу з підключених чатів · {data?.recent_messages.length ?? 0}
                  </span>
                }
              />
              {data?.telegram_state?.status === "error" && (
                <div className="px-5 pt-3">
                  <ErrorNote>
                    {data.telegram_state.error || "Telegram відключено."} Нові повідомлення не надходять, доки акаунт не підключити знову у вкладці «Підключення Telegram».
                  </ErrorNote>
                </div>
              )}
              {promoteError && <div className="px-5 pt-3"><ErrorNote>{promoteError}</ErrorNote></div>}
              <div className="divide-y divide-divider">
                {!data?.recent_messages.length ? (
                  <Empty>Повідомлень із груп поки немає</Empty>
                ) : (
                  data.recent_messages.map((msg) => {
                    const intentCat =
                      msg.ai_intent && msg.ai_intent in CATEGORY_META
                        ? CATEGORY_META[msg.ai_intent as TaskCategory]
                        : null;
                    return (
                      <div key={msg.id} className="flex flex-col gap-2 p-4 transition hover:bg-surface-hover/50">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="rounded bg-inset px-2 py-0.5 text-[11.5px] font-semibold text-main">
                              💬 {msg.chat_title || `Chat ${msg.chat_id}`}
                            </span>
                            <span className="font-mono text-[12px] text-accent">
                              @{msg.sender_username || msg.sender_name || "user"}
                            </span>
                            <span className="text-[11px] text-faint">
                              {new Date(msg.sent_at).toLocaleString("uk-UA", { timeZone: "Europe/Kyiv",
                                day: "2-digit",
                                month: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            {msg.is_actionable ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                                <Zap size={11} /> Задача ({msg.ai_confidence ?? 85}%)
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-slate-500/15 px-2.5 py-0.5 text-[11px] text-faint">
                                Пропущено ШІ (шум)
                              </span>
                            )}

                            {msg.task_code && msg.task_id ? (
                              <button
                                onClick={() => {
                                  setSelectedTaskId(msg.task_id);
                                }}
                                className="cursor-pointer rounded border border-accent/50 bg-accent/15 px-2 py-0.5 font-mono text-[11.5px] font-bold text-accent hover:bg-accent/25"
                              >
                                {msg.task_code} →
                              </button>
                            ) : (
                              editable && (
                                <button
                                  onClick={() => promoteLogToTask(msg.id)}
                                  className="cursor-pointer rounded border border-line-strong bg-surface-hover px-2 py-0.5 text-[11px] text-muted hover:border-accent hover:text-main"
                                >
                                  + Створити задачу
                                </button>
                              )
                            )}
                          </div>
                        </div>

                        <div className="rounded-md bg-inset px-3 py-2 text-[13px] text-main">{msg.raw_text}</div>

                        {intentCat && (
                          <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
                            <span
                              className="rounded px-2 py-0.5 font-medium"
                              style={{ color: intentCat.color, background: intentCat.bg }}
                            >
                              Категорія ШІ: {intentCat.label}
                            </span>
                            {Boolean((msg.ai_extracted as Record<string, unknown>)?.reasoning) && (
                              <span className="text-faint">
                                {String((msg.ai_extracted as Record<string, unknown>)?.reasoning)}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════
          TAB 3: ПІДКЛЮЧЕННЯ TELEGRAM-АКАУНТА (TELETHON) & ГРУПИ & ШІ
         ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === "settings" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          {/* Ліва колонка: Підключення особистого Telegram-акаунта + Налаштування ШІ */}
          <div className="space-y-6 xl:col-span-5">
            {/* Картка підключення особистого Telegram акаунта */}
            <Card>
              <CardHeader
                title="Особистий Telegram-акаунт (MTProto Userbot)"
                icon={<Send size={16} className="text-sky-400" />}
                right={
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold",
                      tgState?.status === "connected"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : tgState?.status === "code_sent"
                          ? "bg-amber-500/15 text-amber-300"
                          : "bg-slate-500/15 text-muted",
                    )}
                  >
                    {tgState?.status === "connected"
                      ? "ПІДКЛЮЧЕНО"
                      : tgState?.status === "code_sent"
                        ? "ОЧІКУЄ КОД"
                        : "НЕ ПІДКЛЮЧЕНО"}
                  </span>
                }
              />
              <div className="space-y-4 p-5">
                <p className="text-[12.5px] text-muted">
                  Підключіть робочий Telegram-акаунт через офіційний протокол MTProto (Telethon), щоб система могла читати повідомлення у вибраних групах з баєрами та клієнтами в реальному часі без необхідності робити бота адміном.
                </p>

                {tgError && <ErrorNote>{tgError}</ErrorNote>}
                {tgNotice && (
                  <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-[12.5px] text-emerald-300">
                    {tgNotice}
                  </div>
                )}

                {tgState?.status === "connected" ? (
                  <div className="space-y-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-[14px] font-semibold text-main">
                          {tgState.account_name}{" "}
                          {tgState.account_username ? `(@${tgState.account_username})` : ""}
                        </div>
                        <div className="font-mono text-[12px] text-muted">Телефон: {tgState.phone}</div>
                      </div>
                      <Button size="sm" variant="danger" onClick={handleDisconnectTg} disabled={!editable || tgBusy}>
                        Відключити
                      </Button>
                    </div>

                    <div className="flex flex-wrap gap-2 pt-2">
                      <Button size="sm" variant="primary" onClick={handleLoadDialogs} disabled={!editable || tgBusy}>
                        Завантажити мої групи з ТГ
                      </Button>
                      <Button size="sm" variant="ghost" onClick={handleSyncTgNow} disabled={!editable || tgBusy}>
                        <RefreshCw size={13} className={tgBusy ? "animate-spin" : ""} />
                        Зчитати нові повідомлення
                      </Button>
                    </div>

                    {discoveredDialogs.length > 0 && (
                      <div className="mt-3 max-h-60 space-y-1.5 overflow-y-auto rounded border border-line bg-inset p-2.5">
                        <div className="text-[11px] font-semibold uppercase text-faint">
                          Знайдені групи у вашому Telegram ({discoveredDialogs.length}):
                        </div>
                        {discoveredDialogs.map((d) => (
                          <div
                            key={d.chat_id}
                            className="flex items-center justify-between gap-2 rounded bg-surface px-2.5 py-1.5 text-[12px]"
                          >
                            <div className="truncate">
                              <span className="font-medium text-main">{d.title}</span>
                              <span className="ml-2 font-mono text-[11px] text-faint">{d.chat_id}</span>
                            </div>
                            {d.already_added ? (
                              <div className="flex shrink-0 items-center gap-2">
                                <span className="text-[11px] text-emerald-400">✓ Додано</span>
                                {(() => {
                                  const matchedGroup = data?.groups.find((gr) => gr.chat_id === d.chat_id);
                                  return matchedGroup ? (
                                    <button
                                      onClick={() => handleDeleteGroup(matchedGroup)}
                                      title="Видалити групу та її задачі"
                                      className="cursor-pointer rounded border border-rose-500/40 bg-rose-500/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-rose-300 hover:bg-rose-500/25"
                                    >
                                      × Прибрати
                                    </button>
                                  ) : null;
                                })()}
                              </div>
                            ) : (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={async () => {
                                  await api("/tasks/groups", {
                                    method: "POST",
                                    body: {
                                      chat_id: d.chat_id,
                                      title: d.title,
                                      username: d.username,
                                      chat_type: d.chat_type,
                                      is_monitored: true,
                                      auto_create_tasks: true,
                                    },
                                  });
                                  setDiscoveredDialogs((prev) =>
                                    prev.map((x) => (x.chat_id === d.chat_id ? { ...x, already_added: true } : x)),
                                  );
                                  mutate();
                                }}
                              >
                                + Підключити
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-md border border-line bg-inset p-3 text-[12px] text-muted">
                      1. Перейдіть на{" "}
                      <a
                        href="https://my.telegram.org"
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent underline"
                      >
                        my.telegram.org
                      </a>{" "}
                      → <strong>API development tools</strong>.<br />
                      2. Скопіюйте <code>App api_id</code> та <code>App api_hash</code> і введіть свій номер телефону.
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Telegram API ID">
                        <Input
                          value={tgApiId}
                          onChange={(e) => setTgApiId(e.target.value)}
                          placeholder={String(tgState?.api_id || "20401928")}
                          disabled={!editable}
                        />
                      </Field>
                      <Field label="Telegram API Hash">
                        <Input
                          type="password"
                          value={tgApiHash}
                          onChange={(e) => setTgApiHash(e.target.value)}
                          placeholder={tgState?.api_hash_masked || "a1b2c3d4e5..."}
                          disabled={!editable}
                        />
                      </Field>
                    </div>

                    <Field label="Номер телефону акаунта Telegram">
                      <Input
                        value={tgPhone}
                        onChange={(e) => setTgPhone(e.target.value)}
                        placeholder={tgState?.phone || "+380..."}
                        disabled={!editable}
                      />
                    </Field>

                    <Button
                      variant="primary"
                      onClick={handleSendTgCode}
                      disabled={!editable || tgBusy || !tgApiId || !tgApiHash || !tgPhone}
                      className="w-full"
                    >
                      Надіслати код у Telegram
                    </Button>

                    {tgState?.status === "code_sent" && (
                      <div className="space-y-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5">
                        <div className="text-[12.5px] font-semibold text-amber-200">
                          Крок 2: Введіть код із повідомлення від Telegram
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <Field label="Код підтвердження">
                            <Input
                              value={tgCode}
                              onChange={(e) => setTgCode(e.target.value)}
                              placeholder="12345"
                            />
                          </Field>
                          <Field label="Хмарний пароль 2FA (якщо є)">
                            <Input
                              type="password"
                              value={tgPassword}
                              onChange={(e) => setTgPassword(e.target.value)}
                              placeholder="Опціонально"
                            />
                          </Field>
                        </div>
                        <Button
                          variant="primary"
                          onClick={handleVerifyTgCode}
                          disabled={!editable || tgBusy || !tgCode.trim()}
                          className="w-full"
                        >
                          Підтвердити та запустити парсер
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* Картка налаштування ШІ-Контексту */}
            <Card>
              <CardHeader
                title="ШІ-Аналізатор Контексту (LLM + Доменний NLP)"
                icon={<Sparkles size={16} className="text-purple-400" />}
              />
              <div className="space-y-4 p-5">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Режим ШІ-двигуна">
                    <Select
                      value={aiProvider || data?.ai_config.provider || "hybrid"}
                      onChange={(e) => setAiProvider(e.target.value)}
                      disabled={!editable}
                    >
                      <option value="hybrid">Гібридний (LLM + Доменний NLP)</option>
                      <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                      <option value="gemini">Google Gemini (gemini-2.0-flash)</option>
                      <option value="domain_nlp">Вбудований Арбітражний NLP (без ключа)</option>
                    </Select>
                  </Field>

                  <Field label="Модель LLM">
                    <Input
                      value={aiModel || data?.ai_config.model || "gpt-4o-mini"}
                      onChange={(e) => setAiModel(e.target.value)}
                      placeholder="gpt-4o-mini або gemini-2.0-flash"
                      disabled={!editable}
                    />
                  </Field>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="API Ключ (OpenAI / Gemini)"
                    hint={
                      data?.ai_config.has_api_key
                        ? `Збережено: ${data.ai_config.api_key_masked}`
                        : "Без ключа працює вбудований NLP-парсер"
                    }
                  >
                    <Input
                      type="password"
                      value={aiApiKey}
                      onChange={(e) => setAiApiKey(e.target.value)}
                      placeholder={data?.ai_config.api_key_masked || "sk-... або AIza..."}
                      disabled={!editable}
                    />
                  </Field>

                  <Field label={`Поріг впевненості ШІ (${aiThreshold || data?.ai_config.confidence_threshold || 60}%)`}>
                    <Input
                      type="number"
                      min={20}
                      max={95}
                      value={aiThreshold || data?.ai_config.confidence_threshold || 60}
                      onChange={(e) => setAiThreshold(Number(e.target.value))}
                      disabled={!editable}
                    />
                  </Field>
                </div>

                <Field label="Системний промпт (правила розуміння контексту вашої команди)">
                  <Textarea
                    rows={5}
                    value={aiPrompt || data?.ai_config.system_prompt || ""}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    disabled={!editable}
                  />
                </Field>

                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-emerald-400">{aiSavedMsg}</span>
                  <Button variant="primary" onClick={saveAiSettings} disabled={!editable}>
                    Зберегти налаштування ШІ
                  </Button>
                </div>
              </div>
            </Card>
          </div>

          {/* Права колонка: Список Telegram-груп під моніторингом */}
          <div className="xl:col-span-7">
            <Card>
              <CardHeader
                title="Робочі групи Telegram під моніторингом"
                icon={<UsersGroupIcon />}
                right={
                  editable && (
                    <Button size="sm" variant="primary" onClick={() => setAddingGroup(true)}>
                      <Plus size={14} /> Додати групу
                    </Button>
                  )
                }
              />
              <div className="divide-y divide-divider">
                {!data?.groups.length ? (
                  <Empty>Немає доданих груп для моніторингу</Empty>
                ) : (
                  data.groups.map((g) => (
                    <div key={g.id} className="space-y-3 p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "size-2.5 rounded-full",
                                g.is_monitored ? "bg-emerald-400" : "bg-slate-500",
                              )}
                            />
                            <h3 className="text-[15px] font-semibold text-main">{g.title}</h3>
                            <span className="font-mono text-[11.5px] text-faint">ID: {g.chat_id}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-3 text-[12px] text-muted">
                            <span>Повідомлень розібрано: {g.messages_parsed}</span>
                            <span>·</span>
                            <span>Створено задач: {g.tasks_created}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleGroupFlag(g, "is_monitored")}
                            disabled={!editable}
                            className={cn(
                              "rounded-md border px-2.5 py-1 text-[11.5px] font-semibold transition",
                              editable ? "cursor-pointer" : "cursor-not-allowed opacity-60",
                              g.is_monitored
                                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                                : "border-line-strong bg-surface-hover text-muted",
                            )}
                          >
                            {g.is_monitored ? "● Парсинг активний" : "○ На паузі"}
                          </button>

                          <button
                            onClick={() => toggleGroupFlag(g, "auto_create_tasks")}
                            disabled={!editable}
                            className={cn(
                              "rounded-md border px-2.5 py-1 text-[11.5px] font-medium transition",
                              editable ? "cursor-pointer" : "cursor-not-allowed opacity-60",
                              g.auto_create_tasks
                                ? "border-purple-500/40 bg-purple-500/15 text-purple-300"
                                : "border-line-strong bg-surface-hover text-muted",
                            )}
                          >
                            {g.auto_create_tasks ? "Авто-задачі: УВІМК" : "Тільки лог"}
                          </button>

                          {editable && (
                            <button
                              onClick={() => handleDeleteGroup(g)}
                              title="Видалити групу з моніторингу разом зі створеними з неї задачами"
                              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-rose-500/40 bg-rose-500/15 px-2.5 py-1 text-[11.5px] font-semibold text-rose-300 transition hover:bg-rose-500/25"
                            >
                              <Trash2 size={13} />
                              Видалити
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <Field label="Прив'язка до Команди баєрів">
                          <Select
                            value={g.team_id || ""}
                            disabled={!editable}
                            onChange={(e) => updateGroupBinding(g, { team_id: e.target.value || null })}
                          >
                            <option value="">Без прив'язки до команди</option>
                            {data?.teams.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name}
                              </option>
                            ))}
                          </Select>
                        </Field>

                        <Field label="Відповідальний виконавець за замовчуванням">
                          <Select
                            value={g.default_assignee_id || ""}
                            disabled={!editable}
                            onChange={(e) => updateGroupBinding(g, { default_assignee_id: e.target.value || null })}
                          >
                            <option value="">Авто / Без призначення</option>
                            {data?.users.map((u) => (
                              <option key={u.id} value={u.id}>
                                {u.name} ({u.role})
                              </option>
                            ))}
                          </Select>
                        </Field>
                      </div>

                      {g.topic_filter && (
                        <div className="rounded border border-line bg-inset px-3 py-2 text-[12px] text-muted">
                          <span className="font-semibold text-main">Контекстне правило ШІ для групи: </span>
                          {g.topic_filter}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* Модальне вікно деталей задачі */}
      {selectedTask && data && (
        <TaskDetailModal
          task={selectedTask}
          overview={data}
          editable={editable}
          onClose={() => setSelectedTaskId(null)}
          onChanged={() => mutate()}
          onConvertRequest={() => handleConvertToRequest(selectedTask)}
        />
      )}

      {/* Модальне вікно створення нової задачі */}
      {creatingTask && data && (
        <CreateTaskModal
          overview={data}
          onClose={() => setCreatingTask(false)}
          onCreated={() => {
            setCreatingTask(false);
            mutate();
          }}
        />
      )}

      {/* Модальне вікно додавання Telegram-групи */}
      {addingGroup && data && (
        <AddTelegramGroupModal
          overview={data}
          onClose={() => setAddingGroup(false)}
          onCreated={() => {
            setAddingGroup(false);
            mutate();
          }}
        />
      )}

      {/* Модальне вікно постановки задачі з контексту діалогу Telegram */}
      {threadForTask && data && (
        <CreateTaskFromThreadModal
          thread={threadForTask}
          overview={data}
          onClose={() => setThreadForTask(null)}
          onCreated={() => {
            setThreadForTask(null);
            mutate();
          }}
        />
      )}
    </div>
  );
}

function UsersGroupIcon() {
  return <MessageSquare size={16} className="text-emerald-400" />;
}

/* ─────────────────────────────────────────────────────────────────────────────
   Модальне вікно перегляду та редагування задачі (Чекліст, ШІ-контекст, Коментарі)
   ───────────────────────────────────────────────────────────────────────────── */
function TaskDetailModal({
  task,
  overview,
  editable,
  onClose,
  onChanged,
  onConvertRequest,
}: {
  task: TeamTaskItem;
  overview: TasksOverview;
  editable: boolean;
  onClose: () => void;
  onChanged: () => void;
  onConvertRequest: () => void;
}) {
  const [newStepText, setNewStepText] = useState("");
  const [commentText, setCommentText] = useState("");
  const [copiedReply, setCopiedReply] = useState(false);

  const cat = CATEGORY_META[task.category] || CATEGORY_META.general;
  const ctx = task.ai_context || {};

  async function patchTask(payload: Record<string, unknown>) {
    await api(`/tasks/${task.id}`, { method: "PATCH", body: payload });
    onChanged();
  }

  async function toggleChecklistItem(item: TaskChecklistItem) {
    const next = task.checklist.map((c) => (c.id === item.id ? { ...c, done: !c.done } : c));
    await patchTask({ checklist: next });
  }

  async function addChecklistItem() {
    if (!newStepText.trim()) return;
    const next = [
      ...task.checklist,
      { id: `chk-${Date.now()}`, text: newStepText.trim(), done: false },
    ];
    setNewStepText("");
    await patchTask({ checklist: next });
  }

  async function submitComment() {
    if (!commentText.trim()) return;
    await api(`/tasks/${task.id}/comments`, {
      method: "POST",
      body: { text: commentText.trim() },
    });
    setCommentText("");
    onChanged();
  }

  async function handleDelete() {
    await api(`/tasks/${task.id}`, { method: "DELETE" });
    onChanged();
    onClose();
  }

  function copySuggestedReply() {
    if (!ctx.suggested_reply) return;
    navigator.clipboard.writeText(ctx.suggested_reply);
    setCopiedReply(true);
    setTimeout(() => setCopiedReply(false), 2000);
  }

  return (
    <Modal title={`${task.code} — ${task.title}`} onClose={onClose} width="max-w-3xl">
      <div className="max-h-[80vh] space-y-5 overflow-y-auto pr-1">
        {/* Top Metadata Grid */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Статус">
            <Select
              value={task.status}
              disabled={!editable}
              onChange={(e) => patchTask({ status: e.target.value })}
            >
              <option value="inbox">Вхідні з Telegram</option>
              <option value="todo">До виконання</option>
              <option value="in_progress">В роботі</option>
              <option value="review">На перевірці</option>
              <option value="done">Виконано</option>
              <option value="rejected">Відхилено</option>
            </Select>
          </Field>

          <Field label="Пріоритет">
            <Select
              value={task.priority}
              disabled={!editable}
              onChange={(e) => patchTask({ priority: e.target.value })}
            >
              <option value="urgent">Терміново 🔥</option>
              <option value="high">Високий</option>
              <option value="medium">Середній</option>
              <option value="low">Низький</option>
            </Select>
          </Field>

          <Field label="Категорія">
            <Select
              value={task.category}
              disabled={!editable}
              onChange={(e) => patchTask({ category: e.target.value })}
            >
              {Object.entries(CATEGORY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Відповідальний">
            <Select
              value={task.assignee_id || ""}
              disabled={!editable}
              onChange={(e) => patchTask({ assignee_id: e.target.value || null })}
            >
              <option value="">Не призначено</option>
              {overview.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Баєр (FBM)">
            <Select
              value={task.buyer_id || ""}
              disabled={!editable}
              onChange={(e) => patchTask({ buyer_id: e.target.value || null })}
            >
              <option value="">Не прив'язано</option>
              {overview.buyers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Команда">
            <Select
              value={task.team_id || ""}
              disabled={!editable}
              onChange={(e) => patchTask({ team_id: e.target.value || null })}
            >
              <option value="">Не прив'язано</option>
              {overview.teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {/* Блок оригінального повідомлення з Telegram та ШІ-контексту */}
        {(task.raw_source_text || ctx.reasoning) && (
          <div className="space-y-3 rounded-xl border border-purple-500/35 bg-purple-500/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[12.5px] font-semibold text-purple-300">
                <Bot size={15} />
                <span>Розбір контексту ШІ ({ctx.confidence ?? 85}% впевненості)</span>
                {task.telegram_chat_title && (
                  <span className="text-muted">· Група: «{task.telegram_chat_title}»</span>
                )}
              </div>
              {task.telegram_message_link && (
                <a
                  href={task.telegram_message_link}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline"
                >
                  Відкрити в Telegram <ExternalLink size={12} />
                </a>
              )}
            </div>

            {ctx.thread_messages && ctx.thread_messages.length > 0 ? (
              <div className="max-h-60 space-y-1.5 overflow-y-auto rounded-lg border border-line bg-inset p-3 text-[12.5px]">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">
                  Історія повідомлень діалогу ({ctx.thread_messages.length}):
                </div>
                {ctx.thread_messages.map((tm) => (
                  <div
                    key={tm.id}
                    className={cn(
                      "rounded px-2.5 py-1.5",
                      tm.is_support
                        ? "border-l-2 border-emerald-500/60 bg-emerald-500/5 text-muted"
                        : "border-l-2 border-accent bg-surface text-main",
                    )}
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className={cn("font-semibold", tm.is_support ? "text-emerald-400" : "text-accent")}>
                        {tm.is_support
                          ? `🛠 Саппорт (${tm.sender_name || tm.sender_username || "SP"})`
                          : `👤 Клієнт (@${tm.sender_username || tm.sender_name || "user"})`}
                      </span>
                      {tm.sent_at && (
                        <span className="font-mono text-faint">
                          {new Date(tm.sent_at).toLocaleString("uk-UA", { timeZone: "Europe/Kyiv",
                            day: "2-digit",
                            month: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 whitespace-pre-wrap break-words">{tm.raw_text}</div>
                  </div>
                ))}
              </div>
            ) : (
              task.raw_source_text && (
                <div className="whitespace-pre-wrap rounded-md border border-line bg-inset p-3 text-[13px] text-main">
                  <div className="mb-1 font-mono text-[11px] text-accent">
                    {task.telegram_sender || "Повідомлення з чату"}:
                  </div>
                  «{task.raw_source_text}»
                </div>
              )
            )}

            <div className="flex flex-wrap gap-2 text-[12px]">
              {ctx.card_last4?.map((c) => (
                <span key={c} className="rounded bg-rose-500/15 px-2 py-0.5 font-mono text-rose-300">
                  Картка FBM: ••{c}
                </span>
              ))}
              {ctx.account_codes?.map((a) => (
                <span key={a} className="rounded bg-amber-500/15 px-2 py-0.5 font-mono text-amber-300">
                  Акаунт: {a}
                </span>
              ))}
              {ctx.bm_id && (
                <span className="rounded bg-purple-500/15 px-2 py-0.5 font-mono text-purple-300">
                  BM ID: {ctx.bm_id}
                </span>
              )}
              {ctx.qty && (
                <span className="rounded bg-sky-500/15 px-2 py-0.5 font-mono text-sky-300">
                  Кількість: {ctx.qty} шт {ctx.geo ? `(${ctx.geo})` : ""} {ctx.limit ? `ліміт ${ctx.limit}` : ""}
                </span>
              )}
            </div>

            {ctx.suggested_reply && (
              <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-[12.5px]">
                <div className="min-w-0 flex-1">
                  <span className="font-semibold text-muted">Чернетка відповіді в ТГ: </span>
                  <span className="text-main">{ctx.suggested_reply}</span>
                </div>
                <Button size="sm" variant="ghost" onClick={copySuggestedReply}>
                  {copiedReply ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                  {copiedReply ? "Скопійовано" : "Копіювати"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Чекліст виконання */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
              Чекліст виконання ({task.checklist_done}/{task.checklist_total})
            </span>
            {task.category === "issue_accounts" && !task.linked_request_id && editable && (
              <Button size="sm" variant="primary" onClick={onConvertRequest}>
                <ArrowRight size={13} /> Перетворити в Заявку на видачу акаунтів
              </Button>
            )}
          </div>

          <div className="space-y-1.5 rounded-lg border border-line bg-inset p-3">
            {task.checklist.map((item) => (
              <label
                key={item.id}
                className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-[13px] transition hover:bg-surface"
              >
                <input
                  type="checkbox"
                  checked={item.done}
                  disabled={!editable}
                  onChange={() => toggleChecklistItem(item)}
                  className="size-4 accent-purple-500"
                />
                <span className={cn(item.done ? "line-through text-faint" : "text-main")}>{item.text}</span>
              </label>
            ))}

            {editable && (
              <div className="mt-2 flex gap-2 pt-1">
                <Input
                  value={newStepText}
                  onChange={(e) => setNewStepText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addChecklistItem()}
                  placeholder="Додати підзадачу / крок..."
                  className="h-8 text-[12.5px]"
                />
                <Button size="sm" variant="ghost" onClick={addChecklistItem}>
                  Додати
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Коментарі та журнал по задачі */}
        <div className="space-y-2.5">
          <div className="text-[12px] font-semibold uppercase tracking-wider text-muted">
            Коментарі та історія ({task.comments.length})
          </div>
          <div className="space-y-2 rounded-lg border border-line bg-inset p-3">
            {task.comments.map((c) => (
              <div key={c.id} className="rounded bg-surface px-3 py-2 text-[12.5px]">
                <div className="flex items-center justify-between text-[11px] text-faint">
                  <span className="font-semibold text-accent">{c.author}</span>
                  <span>{new Date(c.created_at).toLocaleString("uk-UA")}</span>
                </div>
                <div className="mt-1 text-main">{c.text}</div>
              </div>
            ))}
            {editable && (
              <div className="flex gap-2 pt-2">
                <Input
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submitComment()}
                  placeholder="Написати коментар для команди..."
                />
                <Button variant="primary" onClick={submitComment}>
                  Надіслати
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-divider pt-3">
          {editable ? (
            <Button size="sm" variant="danger" onClick={handleDelete}>
              <Trash2 size={14} /> Видалити задачу
            </Button>
          ) : (
            <div />
          )}
          <Button variant="ghost" onClick={onClose}>
            Закрити
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Модальне вікно ручного створення задачі (з авто-збагаченням через ШІ)
   ───────────────────────────────────────────────────────────────────────────── */
function CreateTaskModal({
  overview,
  onClose,
  onCreated,
}: {
  overview: TasksOverview;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<TaskCategory>("general");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [assigneeId, setAssigneeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [buyerId, setBuyerId] = useState("");
  const [useAi, setUseAi] = useState(true);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api("/tasks", {
        method: "POST",
        body: {
          title: title.trim(),
          description: description.trim() || null,
          category,
          priority,
          status: "todo",
          assignee_id: assigneeId || null,
          team_id: teamId || null,
          buyer_id: buyerId || null,
          use_ai_enrichment: useAi,
        },
      });
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Нова задача для команди" onClose={onClose}>
      <div className="space-y-4">
        <Field label="Назва задачі або текст повідомлення з Telegram">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Напр.: Перевірити деклайн по картці ••9443 для WebLumi"
          />
        </Field>

        <Field label="Детальний опис / примітки">
          <Textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Додаткові деталі, БМ ID, коди акаунтів..."
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Категорія">
            <Select value={category} onChange={(e) => setCategory(e.target.value as TaskCategory)}>
              {Object.entries(CATEGORY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Пріоритет">
            <Select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)}>
              <option value="urgent">Терміново 🔥</option>
              <option value="high">Високий</option>
              <option value="medium">Середній</option>
              <option value="low">Низький</option>
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Виконавець">
            <Select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
              <option value="">Не призначено</option>
              {overview.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Команда">
            <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">Без команди</option>
              {overview.teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Баєр">
            <Select value={buyerId} onChange={(e) => setBuyerId(e.target.value)}>
              <option value="">Без баєра</option>
              {overview.buyers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <label className="flex items-center gap-2 text-[12.5px] text-muted">
          <input
            type="checkbox"
            checked={useAi}
            onChange={(e) => setUseAi(e.target.checked)}
            className="size-4 accent-purple-500"
          />
          Автоматично згенерувати чекліст кроків та знайти сутності через ШІ
        </label>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Скасувати
          </Button>
          <Button variant="primary" onClick={submit} disabled={busy || !title.trim()}>
            Створити задачу
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Модальне вікно додавання Telegram-групи
   ───────────────────────────────────────────────────────────────────────────── */
function AddTelegramGroupModal({
  overview,
  onClose,
  onCreated,
}: {
  overview: TasksOverview;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [chatId, setChatId] = useState("-100");
  const [teamId, setTeamId] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!title.trim() || !chatId.trim()) return;
    setBusy(true);
    try {
      await api("/tasks/groups", {
        method: "POST",
        body: {
          chat_id: Number(chatId),
          title: title.trim(),
          team_id: teamId || null,
          default_assignee_id: assigneeId || null,
          topic_filter: topicFilter.trim() || null,
          is_monitored: true,
          auto_create_tasks: true,
        },
      });
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Додати Telegram-групу для моніторингу" onClose={onClose}>
      <div className="space-y-4">
        <Field label="Назва робочої групи в Telegram">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Напр.: CPA Samurai Team | Запити на акаунти"
          />
        </Field>

        <Field label="Telegram Chat ID (починається з -100...)" hint="Або натисніть «Завантажити мої групи з ТГ» після підключення акаунта">
          <Input value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="-1002198451234" />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Прив'язати до Команди">
            <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">Без прив'язки</option>
              {overview.teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Відповідальний за замовчуванням">
            <Select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
              <option value="">Не обрано</option>
              {overview.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Додаткова підказка контексту для ШІ по цій групі">
          <Textarea
            rows={2}
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value)}
            placeholder="Напр.: У цій групі баєри пишуть про деклайни карток та видачу кабінетів..."
          />
        </Field>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Скасувати
          </Button>
          <Button variant="primary" onClick={submit} disabled={busy || !title.trim()}>
            Додати групу
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Модальне вікно постановки задачі з контексту діалогу Telegram
   ───────────────────────────────────────────────────────────────────────────── */
function CreateTaskFromThreadModal({
  thread,
  overview,
  onClose,
  onCreated,
}: {
  thread: TelegramConversationThread;
  overview: TasksOverview;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState(thread.suggested_title);
  const [description, setDescription] = useState(thread.context_summary);
  const [category, setCategory] = useState<TaskCategory>(thread.category);
  const [priority, setPriority] = useState<TaskPriority>(thread.priority);
  const [assigneeId, setAssigneeId] = useState("");
  const [teamId, setTeamId] = useState(thread.team_id || "");
  const [buyerId, setBuyerId] = useState(thread.buyer_id || "");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api("/tasks/from-thread", {
        method: "POST",
        body: {
          chat_id: thread.chat_id,
          topic_id: thread.topic_id,
          title: title.trim(),
          description: description.trim() || null,
          category,
          priority,
          assignee_id: assigneeId || null,
          team_id: teamId || null,
          buyer_id: buyerId || null,
        },
      });
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Поставити задачу з діалогу: ${thread.chat_title}${thread.topic_id ? ` · Гілка #${thread.topic_id}` : ""}`}
      onClose={onClose}
      width="max-w-2xl"
    >
      <div className="max-h-[80vh] space-y-4 overflow-y-auto pr-1">
        {/* Перегляд останніх повідомлень діалогу */}
        <div className="space-y-1.5 rounded-lg border border-line bg-inset p-3 text-[12px]">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Останні повідомлення цього діалогу ({thread.messages_count}), які будуть прикріплені до задачі:
          </div>
          <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
            {thread.messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  "rounded px-2.5 py-1.5",
                  m.is_support
                    ? "border-l-2 border-emerald-500/60 bg-emerald-500/5 text-muted"
                    : "border-l-2 border-accent bg-surface text-main",
                )}
              >
                <div className="flex items-center justify-between text-[10.5px]">
                  <span className={cn("font-semibold", m.is_support ? "text-emerald-400" : "text-accent")}>
                    {m.is_support
                      ? `🛠 Саппорт (${m.sender_name || m.sender_username || "SP"})`
                      : `👤 Клієнт (@${m.sender_username || m.sender_name || "user"})`}
                  </span>
                  {m.sent_at && (
                    <span className="font-mono text-faint">
                      {new Date(m.sent_at).toLocaleString("uk-UA", { timeZone: "Europe/Kyiv",
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 whitespace-pre-wrap break-words">{m.raw_text}</div>
              </div>
            ))}
          </div>
        </div>

        <Field label="Назва задачі (сформовано ШІ з контексту діалогу — можна відредагувати)">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>

        <Field label="Опис контексту для виконавця">
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Категорія">
            <Select value={category} onChange={(e) => setCategory(e.target.value as TaskCategory)}>
              {Object.entries(CATEGORY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Пріоритет">
            <Select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)}>
              <option value="urgent">Терміново 🔥</option>
              <option value="high">Високий</option>
              <option value="medium">Середній</option>
              <option value="low">Низький</option>
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Відповідальний">
            <Select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
              <option value="">Не призначено</option>
              {overview.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Команда">
            <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">Без команди</option>
              {overview.teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Баєр">
            <Select value={buyerId} onChange={(e) => setBuyerId(e.target.value)}>
              <option value="">Без баєра</option>
              {overview.buyers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Скасувати
          </Button>
          <Button variant="primary" onClick={submit} disabled={busy || !title.trim()}>
            <Plus size={14} /> Поставити задачу в роботу
          </Button>
        </div>
      </div>
    </Modal>
  );
}
