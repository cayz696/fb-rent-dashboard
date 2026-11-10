"use client";
import { Menu } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { firstAllowedHref, hasSectionAccess, sectionKeyFromPath, useMe } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, unauthorized } = useMe();
  const router = useRouter();
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
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
    const savedZoom = Number.isFinite(parsed) ? Math.min(125, Math.max(75, parsed)) : 100;
    const zoom = window.innerWidth < 768 ? 100 : savedZoom;
    document.documentElement.style.setProperty("--app-zoom", String(zoom / 100));
    (document.documentElement.style as unknown as Record<string, string>).zoom = `${zoom}%`;
  }, []);

  useEffect(() => { setMenuOpen(false); }, [path]);

  if (!user) return <div className="grid min-h-screen place-items-center text-[13px] text-muted">Завантаження…</div>;
  return (
    <div className="app-shell-height flex">
      <button
        type="button"
        className="fixed left-3 top-3 z-50 inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface text-main shadow-md md:hidden"
        aria-label="Меню"
        onClick={() => setMenuOpen((open) => !open)}
      >
        <Menu size={18} />
      </button>
      {menuOpen && (
        <button
          type="button"
          aria-label="Закрити меню"
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <Sidebar user={user} mobileOpen={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <main className="min-w-0 flex-1 px-4 pb-8 pt-16 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
