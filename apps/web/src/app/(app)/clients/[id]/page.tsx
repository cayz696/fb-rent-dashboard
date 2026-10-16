"use client";
import { ArrowLeft, Pencil } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { ClientFinance } from "@/components/clients/finance";
import { ClientForm } from "@/components/clients/form";
import { AccountsTable } from "@/components/accounts/table";
import { Button, Card, CardHeader, PageHeader } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/session";
import type { AccountList, Client } from "@/lib/types";
import { money } from "@/lib/utils";

export default function ClientCard() {
  const { id } = useParams<{ id: string }>();
  const { user } = useMe();
  const { data: c, mutate } = useSWR<Client>(`/api/clients/${id}`, fetcher);
  const { data: accs } = useSWR<AccountList>(`/api/accounts?client_id=${id}&limit=200`, fetcher);
  const [edit, setEdit] = useState(false);
  if (!c) return <p className="text-muted">Завантаження…</p>;
  return (
    <>
      <Link href="/clients" className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-main"><ArrowLeft size={14} />Клієнти</Link>
      <PageHeader title={c.name}
        sub={<span className="font-mono">{c.telegram_usernames.map((u) => `@${u}`).join(", ") || "Telegram не вказано"}</span>}
        right={isAdmin(user) && <Button onClick={() => setEdit(true)}><Pencil size={14} />Редагувати</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[["Видано зараз", String(c.accounts_issued)], ["Баланс", money(c.current_balance ?? c.balance)], ["% від спенду", Number(c.fee_percent) ? `${Number(c.fee_percent)}%` : "—"], ["Статус", c.status]].map(([l, v]) => (
          <div key={l} className="panel kpi-glow p-5"><div className="text-[13px] text-muted">{l}</div><div className="mt-2 font-mono text-[20px] font-semibold">{v}</div></div>
        ))}
      </div>
      {c.notes && <p className="panel mb-5 p-4 text-[13px] text-muted">{c.notes}</p>}
      <Card>
        <CardHeader title="Акаунти клієнта" />
        <AccountsTable items={accs?.items ?? []} />
      </Card>
      {isAdmin(user) && <ClientFinance clientId={id} />}
      {edit && <ClientForm client={c} onClose={() => setEdit(false)} onDone={() => { setEdit(false); mutate(); }} />}
    </>
  );
}
