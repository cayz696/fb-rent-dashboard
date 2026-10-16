"use client";
import { useState } from "react";
import useSWR from "swr";
import { EventList } from "@/components/accounts/events";
import { Card, PageHeader, Select } from "@/components/ui";
import { fetcher, qs } from "@/lib/api";
import type { AccountEvent } from "@/lib/types";

export default function EventsPage() {
  const [type, setType] = useState("");
  const { data } = useSWR<AccountEvent[]>(`/api/events${qs({ type, limit: "200" })}`, fetcher, { refreshInterval: 15000 });
  return (
    <>
      <PageHeader title="Журнал подій" sub="Глобальний журнал змін акаунтів (лише додавання, без редагування)"
        right={
          <Select className="w-48" value={type} onChange={(e) => setType(e.target.value)} aria-label="Тип події">
            <option value="">Усі події</option>
            <option value="stage_change">Зміни етапу</option>
            <option value="created">Створення</option>
            <option value="updated">Редагування</option>
          </Select>
        } />
      <Card><EventList events={data ?? []} showAccount /></Card>
    </>
  );
}
