"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { firstAllowedHref, hasSectionAccess, sectionKeyFromPath, useMe } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, unauthorized } = useMe();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => { if (unauthorized) router.replace("/login"); }, [unauthorized, router]);
  useEffect(() => {
    if (!user) return;
    const section = sectionKeyFromPath(path);
    if (section && !hasSectionAccess(user, section)) {
      router.replace(firstAllowedHref(user));
    }
  }, [user, path, router]);
  useEffect(() => {
    const saved = user?.theme || (typeof window !== "undefined" ? localStorage.getItem("sp_theme") : null) || "dark";
    const resolved = saved === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", resolved);
    if (user?.theme) {
      localStorage.setItem("sp_theme", resolved);
    }
  }, [user?.theme]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem("sp_ui_zoom");
    const parsed = raw ? parseInt(raw, 10) : 100;
    const zoom = Number.isFinite(parsed) ? Math.min(125, Math.max(75, parsed)) : 100;
    document.documentElement.style.setProperty("--app-zoom", String(zoom / 100));
    (document.documentElement.style as unknown as Record<string, string>).zoom = `${zoom}%`;
  }, []);

  if (!user) return <div className="grid min-h-screen place-items-center text-[13px] text-muted">Завантаження…</div>;
  return (
    <div className="app-shell-height flex">
      <Sidebar user={user} />
      <main className="min-w-0 flex-1 px-8 py-8">{children}</main>
    </div>
  );
}
