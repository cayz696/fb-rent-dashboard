"use client";
import useSWR from "swr";
import { fetcher } from "./api";
import type { User } from "./types";

export const ALL_SECTIONS = [
  { key: "dashboard", label: "Дашборд", href: "/dashboard" },
  { key: "buyers", label: "Юзери та Команди", href: "/buyers" },
  { key: "cards", label: "Картки FBM", href: "/cards" },
  { key: "accounts", label: "Акаунти", href: "/accounts" },
  { key: "kanban", label: "Етапи (Канбан)", href: "/kanban" },
  { key: "import", label: "Імпорт замовлення", href: "/import" },
  { key: "adspower", label: "AdsPower", href: "/adspower" },
  { key: "requests", label: "Заявки", href: "/requests" },
  { key: "clients", label: "Клієнти", href: "/clients" },
  { key: "suppliers", label: "Постачальники", href: "/suppliers" },
  { key: "finance", label: "Фінанси", href: "/finance" },
  { key: "reports", label: "Звітність (Точка прибутку)", href: "/reports" },
  { key: "events", label: "Журнал подій", href: "/events" },
  { key: "agent", label: "ШІ-Агент", href: "/agent" },
  { key: "settings", label: "Налаштування", href: "/settings" },
] as const;

export function useMe() {
  const { data, error, isLoading, mutate } = useSWR<User>("/api/me", fetcher, {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });
  return { user: data, unauthorized: !!error, loading: isLoading, mutate };
}

export const canWrite = (u?: User) => u?.role === "admin" || u?.role === "operator";
export const isAdmin = (u?: User) => u?.role === "admin";

export function hasSectionAccess(u: User | undefined, sectionKey: string): boolean {
  if (!u) return false;
  if (u.role === "admin" && (!u.allowed_sections || u.allowed_sections.length === 0)) {
    return true;
  }
  if (u.allowed_sections && u.allowed_sections.length > 0) {
    return u.allowed_sections.includes(sectionKey);
  }
  // Якщо у не-адміна не задано кастомний список вкладок — застосовуємо стандартні обмеження ролі
  if (sectionKey === "settings" || sectionKey === "finance" || sectionKey === "reports") {
    return false;
  }
  return true;
}
