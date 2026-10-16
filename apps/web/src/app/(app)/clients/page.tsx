"use client";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ClientForm } from "@/components/clients/form";
import { Button, Card, Empty, PageHeader } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/session";
import type { Client } from "@/lib/types";
import { money } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export default function ClientsPage() {
  const { user } = useMe();
  const { data, mutate } = useSWR<Client[]>("/api/clients", fetcher);
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title="Клієнти" sub={`${data?.length ?? 0} клієнтів`}
        right={isAdmin(user) && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={15} />Новий клієнт</Button>} />
      <Card>
        {data && !data.length ? <Empty>Клієнтів ще немає</Empty> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-divider bg-inset/50">
              <th className={th}>Клієнт</th><th className={th}>Telegram</th><th className={th}>Видано</th><th className={th}>Умови</th><th className={th}>Баланс</th>
            </tr></thead>
            <tbody>
              {data?.map((c) => (
                <tr key={c.id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                  <td className="px-5 py-3.5"><Link href={`/clients/${c.id}`} className="font-semibold text-main hover:text-accent">{c.name}</Link></td>
                  <td className="px-5 py-3.5 font-mono text-[12px] text-muted">{c.telegram_usernames.map((u) => `@${u}`).join(", ") || "—"}</td>
                  <td className="px-5 py-3.5 font-mono">{c.accounts_issued}</td>
                  <td className="px-5 py-3.5 text-muted">{c.terms ?? "—"}</td>
                  <td className="px-5 py-3.5 font-mono">{money(c.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {creating && <ClientForm onClose={() => setCreating(false)} onDone={() => { setCreating(false); mutate(); }} />}
    </>
  );
}
