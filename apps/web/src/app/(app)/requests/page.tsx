"use client";
import { Plus } from "lucide-react";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { CreateRequest, RequestCard } from "@/components/requests/request-card";
import { Button, Chip, Empty, PageHeader } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { canWrite, isAdmin, useMe } from "@/lib/session";
import type { RequestItem } from "@/lib/types";

const TABS = [
  { key: "open", label: "Відкриті", q: "status=new&status=proposed" },
  { key: "done", label: "Видані", q: "status=done" },
  { key: "rejected", label: "Відхилені", q: "status=rejected" },
  { key: "all", label: "Усі", q: "" },
];

export default function RequestsPage() {
  const { user } = useMe();
  const [tab, setTab] = useState("open");
  const [creating, setCreating] = useState(false);
  const q = TABS.find((t) => t.key === tab)!.q;
  const { data, mutate } = useSWR<RequestItem[]>(`/api/requests${q ? `?${q}` : ""}`, fetcher, { refreshInterval: 20000 });
  const refresh = () => { mutate(); globalMutate("/api/dashboard"); globalMutate((k) => typeof k === "string" && k.startsWith("/api/accounts")); };

  return (
    <>
      <PageHeader title="Заявки" sub="Заявки на видачу акаунтів. Telegram-джерело підключиться пізніше — заявки створюються вручну."
        right={canWrite(user) && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={15} />Нова заявка</Button>} />
      <div className="mb-4 flex gap-2">{TABS.map((t) => <Chip key={t.key} active={tab === t.key} onClick={() => setTab(t.key)}>{t.label}</Chip>)}</div>
      {data && !data.length ? <div className="panel"><Empty>Заявок немає</Empty></div> : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {data?.map((r) => <RequestCard key={r.id} r={r} admin={isAdmin(user)} canEdit={canWrite(user)} onChange={refresh} />)}
        </div>
      )}
      {creating && <CreateRequest onClose={() => setCreating(false)} onDone={() => { setCreating(false); refresh(); }} />}
    </>
  );
}
