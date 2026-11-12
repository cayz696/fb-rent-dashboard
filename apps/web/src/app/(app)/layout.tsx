"use client";
import { Menu, Smartphone } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { NotificationsBell } from "@/components/layout/notifications";
import { Sidebar } from "@/components/layout/sidebar";
import { Modal } from "@/components/ui";
import { firstAllowedHref, hasSectionAccess, sectionKeyFromPath, useMe } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, unauthorized } = useMe();
  const router = useRouter();
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [installOpen, setInstallOpen] = useState(false);
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
      <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-2 border-b border-line bg-surface/95 px-3 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur md:hidden">
        <button
          type="button"
          className="inline-flex size-10 items-center justify-center rounded-lg border border-line bg-surface text-main"
          aria-label="Меню"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <Menu size={18} />
        </button>
        <span className="min-w-0 truncate text-[14px] font-semibold">Skull Partners</span>
        <div className="flex items-center">
          <button
            type="button"
            className="inline-flex size-10 items-center justify-center rounded-lg text-muted"
            aria-label="Додати на головний екран"
            title="Відкривати як застосунок"
            onClick={() => setInstallOpen(true)}
          >
            <Smartphone size={18} />
          </button>
          <NotificationsBell />
        </div>
      </div>
      {menuOpen && (
        <button
          type="button"
          aria-label="Закрити меню"
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <Sidebar user={user} mobileOpen={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <main className="min-w-0 flex-1 px-4 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[calc(4.25rem+env(safe-area-inset-top))] md:px-8 md:py-8 md:pt-8">{children}</main>
      {installOpen && (
        <Modal title="Відкривати з головного екрана" onClose={() => setInstallOpen(false)} width="max-w-md">
          <p className="text-[13px] text-muted">Після цього дашборд відкривається окремим вікном, без адресного рядка браузера.</p>
          <ol className="list-decimal space-y-2 pl-5 text-[13.5px]">
            <li>На iPhone: у Safari натисніть «Поділитися», потім «На Початковий екран».</li>
            <li>На Android: меню Chrome (три крапки), потім «Додати на головний екран» або «Встановити застосунок».</li>
          </ol>
          <p className="text-[12.5px] text-muted">Іконка сповіщень унизу меню на комп’ютері і справа зверху на телефоні. Коли задачу призначають на вас, там з’являється «Вам призначено».</p>
        </Modal>
      )}
    </div>
  );
}
