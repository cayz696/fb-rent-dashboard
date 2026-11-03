"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { useMe } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, unauthorized } = useMe();
  const router = useRouter();
  useEffect(() => { if (unauthorized) router.replace("/login"); }, [unauthorized, router]);
  useEffect(() => {
    const saved = user?.theme || (typeof window !== "undefined" ? localStorage.getItem("sp_theme") : null) || "dark";
    const resolved = saved === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", resolved);
    if (user?.theme) {
      localStorage.setItem("sp_theme", resolved);
    }
  }, [user?.theme]);

  if (!user) return <div className="grid min-h-screen place-items-center text-[13px] text-muted">Завантаження…</div>;
  return (
    <div className="flex min-h-screen">
      <Sidebar user={user} />
      <main className="min-w-0 flex-1 px-8 py-8">{children}</main>
    </div>
  );
}
