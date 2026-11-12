"use client";

import {
  Anchor,
  Cat,
  Coffee,
  Compass,
  Crown,
  Flag,
  Flame,
  Gem,
  Ghost,
  Headphones,
  Heart,
  Leaf,
  Rocket,
  Shield,
  Sparkles,
  Star,
  Sun,
  Target,
  Trophy,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export type UserIconKey =
  | "spark"
  | "bolt"
  | "flame"
  | "star"
  | "crown"
  | "gem"
  | "rocket"
  | "shield"
  | "compass"
  | "target"
  | "leaf"
  | "sun"
  | "heart"
  | "flag"
  | "anchor"
  | "headphones"
  | "coffee"
  | "ghost"
  | "cat"
  | "trophy";

export const USER_ICONS: { key: UserIconKey; label: string; icon: LucideIcon; color: string; bg: string }[] = [
  { key: "spark", label: "Іскра", icon: Sparkles, color: "#a855f7", bg: "rgba(168, 85, 247, 0.16)" },
  { key: "bolt", label: "Блискавка", icon: Zap, color: "#f59e0b", bg: "rgba(245, 158, 11, 0.16)" },
  { key: "flame", label: "Вогонь", icon: Flame, color: "#f43f5e", bg: "rgba(244, 63, 94, 0.16)" },
  { key: "star", label: "Зірка", icon: Star, color: "#eab308", bg: "rgba(234, 179, 8, 0.18)" },
  { key: "crown", label: "Корона", icon: Crown, color: "#d97706", bg: "rgba(217, 119, 6, 0.16)" },
  { key: "gem", label: "Діамант", icon: Gem, color: "#38bdf8", bg: "rgba(56, 189, 248, 0.16)" },
  { key: "rocket", label: "Ракета", icon: Rocket, color: "#818cf8", bg: "rgba(129, 140, 248, 0.16)" },
  { key: "shield", label: "Щит", icon: Shield, color: "#10b981", bg: "rgba(16, 185, 129, 0.16)" },
  { key: "compass", label: "Компас", icon: Compass, color: "#06b6d4", bg: "rgba(6, 182, 212, 0.16)" },
  { key: "target", label: "Ціль", icon: Target, color: "#e11d48", bg: "rgba(225, 29, 72, 0.14)" },
  { key: "leaf", label: "Лист", icon: Leaf, color: "#22c55e", bg: "rgba(34, 197, 94, 0.16)" },
  { key: "sun", label: "Сонце", icon: Sun, color: "#f59e0b", bg: "rgba(245, 158, 11, 0.18)" },
  { key: "heart", label: "Серце", icon: Heart, color: "#fb7185", bg: "rgba(251, 113, 133, 0.16)" },
  { key: "flag", label: "Прапор", icon: Flag, color: "#3b82f6", bg: "rgba(59, 130, 246, 0.16)" },
  { key: "anchor", label: "Якір", icon: Anchor, color: "#0284c7", bg: "rgba(2, 132, 199, 0.14)" },
  { key: "headphones", label: "Навушники", icon: Headphones, color: "#c084fc", bg: "rgba(192, 132, 252, 0.16)" },
  { key: "coffee", label: "Кава", icon: Coffee, color: "#b45309", bg: "rgba(180, 83, 9, 0.16)" },
  { key: "ghost", label: "Привид", icon: Ghost, color: "#64748b", bg: "rgba(100, 116, 139, 0.16)" },
  { key: "cat", label: "Кіт", icon: Cat, color: "#fb923c", bg: "rgba(251, 146, 60, 0.18)" },
  { key: "trophy", label: "Кубок", icon: Trophy, color: "#ca8a04", bg: "rgba(202, 138, 4, 0.16)" },
];

const ICON_BY_KEY = Object.fromEntries(USER_ICONS.map((item) => [item.key, item])) as Record<
  UserIconKey,
  (typeof USER_ICONS)[number]
>;

export function resolveUserIcon(userId: string, chosen?: string | null): UserIconKey {
  if (chosen && chosen in ICON_BY_KEY) return chosen as UserIconKey;
  let hash = 0;
  for (const char of userId) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return USER_ICONS[hash % USER_ICONS.length].key;
}

export function UserBadge({
  userId,
  icon,
  size = 16,
  className,
}: {
  userId?: string;
  icon?: string | null;
  size?: number;
  className?: string;
}) {
  const key = resolveUserIcon(userId || icon || "user", icon);
  const item = ICON_BY_KEY[key];
  const Icon = item.icon;
  return (
    <span
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full", className)}
      style={{ background: item.bg, color: item.color, width: size + 10, height: size + 10 }}
      title={item.label}
    >
      <Icon size={size} strokeWidth={2.25} />
    </span>
  );
}

export function IconPicker({
  value,
  onPick,
}: {
  value?: string | null;
  onPick: (key: UserIconKey) => void;
}) {
  return (
    <div className="grid grid-cols-5 gap-1.5">
      {USER_ICONS.map((item) => {
        const active = value === item.key;
        const Icon = item.icon;
        return (
          <button
            key={item.key}
            type="button"
            title={item.label}
            onClick={() => onPick(item.key)}
            className={cn(
              "flex cursor-pointer flex-col items-center gap-1 rounded-lg border px-1 py-1.5 text-[10px] transition",
              active ? "border-accent bg-accent/10 text-main" : "border-line text-muted hover:border-accent hover:text-main",
            )}
          >
            <span
              className="inline-flex size-8 items-center justify-center rounded-full"
              style={{ background: item.bg, color: item.color }}
            >
              <Icon size={16} strokeWidth={2.25} />
            </span>
            <span className="w-full truncate text-center">{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function AssigneePicker({
  users,
  value,
  disabled,
  onChange,
}: {
  users: { id: string; name: string; icon?: string | null }[];
  value: string | null;
  disabled?: boolean;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = users.find((user) => user.id === value) ?? null;

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-full items-center gap-2 rounded-lg border border-line bg-inset px-2 text-left text-[12px] text-main outline-none transition hover:border-accent disabled:cursor-default disabled:opacity-70"
      >
        {current ? (
          <UserBadge userId={current.id} icon={current.icon} size={14} />
        ) : (
          <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-dashed border-line-strong text-[11px] text-faint">
            —
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{current?.name ?? "Не призначено"}</span>
      </button>
      {open && !disabled && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 max-h-56 overflow-y-auto rounded-lg border border-line-strong bg-surface p-1 shadow-[0_12px_32px_rgba(0,0,0,0.28)]">
          <button
            type="button"
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
            className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-muted hover:bg-surface-hover hover:text-main"
          >
            <span className="inline-flex size-6 items-center justify-center rounded-full border border-dashed border-line-strong text-[11px]">—</span>
            Не призначено
          </button>
          {users.map((user) => (
            <button
              key={user.id}
              type="button"
              onClick={() => {
                onChange(user.id);
                setOpen(false);
              }}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] hover:bg-surface-hover",
                user.id === value ? "bg-accent/10 text-main" : "text-main",
              )}
            >
              <UserBadge userId={user.id} icon={user.icon} size={14} />
              <span className="truncate">{user.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
