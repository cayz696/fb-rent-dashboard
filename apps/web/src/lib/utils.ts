import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...i: ClassValue[]) => twMerge(clsx(i));

const TZ = "Europe/Kyiv";
export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString("uk-UA", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("uk-UA", { timeZone: TZ });
export const money = (v: string | number | null | undefined) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
};

export function timeLeft(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "завершена";
  const h = Math.floor(ms / 3.6e6), m = Math.floor((ms % 3.6e6) / 6e4);
  return h > 0 ? `${h}г ${m}хв` : `${m}хв`;
}
