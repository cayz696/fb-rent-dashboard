"use client";
import {
  Activity,
  BarChart3,
  BookText,
  Building2,
  CircleDollarSign,
  Columns3,
  CreditCard,
  GitBranch,
  LayoutGrid,
  LogOut,
  MessageSquare,
  MonitorPlay,
  Settings,
  Sparkles,
  Upload,
  UserCheck,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import useSWR from "swr";
import { NotificationsBell } from "@/components/layout/notifications";
import { api, fetcher } from "@/lib/api";
import { hasSectionAccess, isAdmin } from "@/lib/session";
import type { BridgeStatus, Dashboard, FbmCards, SystemStatus, User } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Sidebar({ user }: { user: User }) {
  const path = usePathname();
  const router = useRouter();
  const canDash = hasSectionAccess(user, "dashboard");
  const canCards = hasSectionAccess(user, "cards");
  const canSettings = isAdmin(user) && hasSectionAccess(user, "settings");
  const { data: d } = useSWR<Dashboard>(canDash ? "/api/dashboard" : null, fetcher, { refreshInterval: 30000 });
  const { data: fbm } = useSWR<FbmCards>(canCards ? "/api/fbm/cards" : null, fetcher, { refreshInterval: 60000 });
  const { data: bridge } = useSWR<BridgeStatus>("/api/bridge/status", fetcher, { refreshInterval: 15000 });
  const { data: sys } = useSWR<SystemStatus>(canSettings ? "/api/system/status" : null, fetcher, { refreshInterval: 120000 });

  const gateways: [string, string, string][] = [
    [
      "FBM Cards",
      !fbm?.configured ? "не налаштовано" : fbm.total > 0 ? `${fbm.total} карток` : "немає даних",
      !fbm?.configured ? "var(--text-faint)" : fbm.total > 0 ? "var(--success)" : "var(--warning)",
    ],
    [
      "AdsPower Bridge",
      !bridge?.last_seen ? "не підключено" : bridge.online ? "онлайн" : "офлайн",
      !bridge?.last_seen ? "var(--text-faint)" : bridge.online ? "var(--success)" : "var(--danger)",
    ],
    ["Автофіксація (3–4г)", "активна", "var(--success)"],
  ];

  const allItems = [
    { key: "dashboard", href: "/dashboard", label: "Дашборд", icon: LayoutGrid },
    { key: "buyers", href: "/buyers", label: "Юзери та Команди", icon: UserCheck },
    { key: "cards", href: "/cards", label: "Картки FBM", icon: CreditCard, count: fbm?.total || undefined },
    {
      key: "accounts",
      href: "/accounts",
      label: "Акаунти",
      icon: Wallet,
      count: d ? Object.entries(d.funnel).reduce((s, [, v]) => s + v, 0) : undefined,
    },
    { key: "kanban", href: "/kanban", label: "Етапи (Канбан)", icon: Columns3 },
    { key: "import", href: "/import", label: "Імпорт замовлення", icon: Upload },
    { key: "adspower", href: "/adspower", label: "AdsPower", icon: MonitorPlay },
    { key: "requests", href: "/requests", label: "Заявки", icon: MessageSquare, badge: d?.requests_queue || undefined },
    { key: "clients", href: "/clients", label: "Клієнти", icon: Users },
    { key: "suppliers", href: "/suppliers", label: "Постачальники", icon: Building2 },
    { key: "finance", href: "/finance", label: "Фінанси", icon: CircleDollarSign },
    { key: "reports", href: "/reports", label: "Звітність", icon: BarChart3 },
    { key: "events", href: "/events", label: "Журнал подій", icon: BookText },
    { key: "agent", href: "/agent", label: "ШІ-Агент", icon: Sparkles },
    { key: "settings", href: "/settings", label: "Налаштування", icon: Settings },
  ];

  const items = allItems.filter((item) => hasSectionAccess(user, item.key));

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[280px] shrink-0 flex-col gap-4 border-r border-line bg-surface px-4 py-5 overflow-visible">
      <div className="flex items-center gap-3 px-2">
        <div className="relative size-11 overflow-hidden rounded-xl border border-purple-500/40 shadow-[0_0_16px_rgba(168,85,247,0.35)] shrink-0 bg-black">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.png"
            alt="Skull Partners Logo"
            className="size-full object-cover"
          />
        </div>
        <div>
          <div className="text-[15px] font-semibold leading-tight text-main">Skull Partners</div>
          <div className="text-[12px] text-muted">Ops Control Panel</div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto pr-1">
        {items.map(({ href, label, icon: Icon, count, badge }) => {
          const active = path === href || path.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md border border-transparent px-3.5 py-2.5 text-[15px] transition",
                active
                  ? "border-line-strong bg-surface-active font-semibold text-main"
                  : "text-muted hover:bg-surface-hover hover:text-main",
              )}
            >
              <Icon size={18} className={active ? "text-accent" : ""} />
              <span className="flex-1 truncate">{label}</span>
              {count !== undefined && <span className="font-mono text-[12.5px] text-faint">{count}</span>}
              {badge !== undefined && (
                <span className="rounded-full bg-accent px-2.5 py-0.5 font-mono text-[11.5px] font-bold text-on-accent">
                  {badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto shrink-0 space-y-2.5">
        <div className="space-y-1.5 rounded-lg border border-line bg-inset p-3 text-[12px]">
          <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-faint">
            <span>Статус шлюзів</span>
            <Activity size={13} />
          </div>
          {gateways.map(([n, t, c]) => (
            <div key={n} className="flex items-center justify-between text-muted">
              <span>{n}</span>
              <span className="flex items-center gap-1.5 font-mono text-[11px]" style={{ color: c }}>
                <i className="size-1.5 rounded-full" style={{ background: c }} />
                {t}
              </span>
            </div>
          ))}
          {canSettings && (
            <div className="mt-2 border-t border-divider pt-2 text-[11px] text-faint">
              <span className="flex items-center gap-1 font-mono">
                <GitBranch size={11} /> {sys?.commit || "local"}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between rounded-lg px-2 text-[13px]">
          <div className="min-w-0">
            <div className="truncate font-medium">{user.name}</div>
            <div className="font-mono text-[11px] text-faint">
              {user.role}
              {user.allowed_sections?.length ? ` · ${user.allowed_sections.length} розд.` : ""}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationsBell />
            <button
              onClick={logout}
              title="Вийти"
              aria-label="Вийти"
              className="cursor-pointer rounded-md p-2 text-muted hover:bg-surface-hover hover:text-main"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
