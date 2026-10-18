"use client";
import { Bell, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { fmtDateTime } from "@/lib/utils";

interface Notification { type: string; severity: string; title: string; message: string; link: string | null; created_at: string }
interface NotifView { count: number; items: Notification[] }

const SEEN_KEY = "fbr_notif_seen";
const dot = (s: string) => (s === "danger" ? "var(--danger)" : s === "warning" ? "var(--warning)" : "var(--info)");

function readSeen(): number {
  try { return Number(localStorage.getItem(SEEN_KEY)) || 0; } catch { return 0; }
}

export function NotificationsBell() {
  const { data } = useSWR<NotifView>("/api/notifications", fetcher, { refreshInterval: 20000 });
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { setSeen(readSeen()); }, []);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const items = data?.items ?? [];
  const unread = items.filter((i) => new Date(i.created_at).getTime() > seen).length;

  function toggle() {
    setOpen((o) => {
      if (!o) { const now = Date.now(); try { localStorage.setItem(SEEN_KEY, String(now)); } catch {} setSeen(now); }
      return !o;
    });
  }

  return (
    <div ref={ref} className="relative">
      <button onClick={toggle} aria-label="Сповіщення" title="Сповіщення"
        className="relative rounded-md p-2 text-muted hover:bg-surface-hover hover:text-main cursor-pointer">
        <Bell size={17} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid min-w-[16px] place-items-center rounded-full bg-accent px-1 font-mono text-[10px] font-bold text-on-accent">{unread > 99 ? "99+" : unread}</span>
        )}
      </button>
      {open && (
        <div className="absolute bottom-0 left-full z-[100] ml-3 w-80 overflow-hidden rounded-lg border border-line-strong bg-surface shadow-[0_12px_40px_rgba(0,0,0,.85)]">
          <div className="flex items-center justify-between border-b border-divider px-4 py-2.5">
            <span className="text-[13px] font-semibold">Сповіщення {!!items.length && <span className="text-faint">({items.length})</span>}</span>
            <button onClick={() => setOpen(false)} className="text-muted hover:text-main cursor-pointer"><X size={15} /></button>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {!items.length ? (
              <p className="px-4 py-8 text-center text-[13px] text-muted">Усе спокійно</p>
            ) : items.map((n, i) => {
              const body = (
                <div className="flex items-start gap-3 px-4 py-3 hover:bg-surface-hover">
                  <i className="mt-1.5 size-2 shrink-0 rounded-full" style={{ background: dot(n.severity) }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[13px] font-semibold">{n.title}</span>
                      <span className="shrink-0 font-mono text-[10px] text-faint">{fmtDateTime(n.created_at)}</span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[12px] text-muted">{n.message}</p>
                  </div>
                </div>
              );
              return n.link
                ? <Link key={i} href={n.link} onClick={() => setOpen(false)} className="block border-b border-divider last:border-0">{body}</Link>
                : <div key={i} className="border-b border-divider last:border-0">{body}</div>;
            })}
          </div>
        </div>
      )}
    </div>
  );
}
