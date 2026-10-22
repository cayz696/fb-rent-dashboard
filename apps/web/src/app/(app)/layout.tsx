"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { hasSectionAccess, useMe } from "@/lib/session";

const PATH_SECTION: [string, string][] = [
  ["/dashboard", "dashboard"],
  ["/buyers", "buyers"],
  ["/cards", "cards"],
  ["/accounts", "accounts"],
  ["/kanban", "kanban"],
  ["/import", "import"],
  ["/adspower", "adspower"],
  ["/requests", "requests"],
  ["/clients", "clients"],
  ["/suppliers", "suppliers"],
  ["/finance", "finance"],
  ["/reports", "reports"],
  ["/events", "events"],
  ["/agent", "agent"],
  ["/settings", "settings"],
];

function sectionFor(path: string): string | null {
  const hit = PATH_SECTION.find(([prefix]) => path === prefix || path.startsWith(prefix + "/"));
  return hit ? hit[1] : null;
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, unauthorized } = useMe();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => { if (unauthorized) router.replace("/login"); }, [unauthorized, router]);

  if (!user) return <div className="grid min-h-screen place-items-center text-[13px] text-muted">Завантаження…</div>;
  const section = sectionFor(path);
  const allowed = !section || hasSectionAccess(user, section);
  return (
    <div className="flex min-h-screen">
      <Sidebar user={user} />
      <main className="min-w-0 flex-1 px-8 py-8">
        {allowed ? children : <div className="panel p-8 text-[14px] text-muted">Немає доступу до цього розділу.</div>}
      </main>
    </div>
  );
}
