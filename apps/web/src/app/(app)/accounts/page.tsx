"use client";
import { ArrowRight, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { AccountsTable } from "@/components/accounts/table";
import { Button, Card, ErrorNote, Field, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, fetcher, qs } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import { forwardStage, STAGE_LABEL } from "@/lib/stages";
import type { Account, AccountList, Batch, Client, Stage, Supplier } from "@/lib/types";

const STAGES = Object.keys(STAGE_LABEL) as Stage[];
const PAGE = 25;

export default function AccountsPage() {
  const { user } = useMe();
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [clientId, setClientId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [adsGroup, setAdsGroup] = useState("");
  const [signal, setSignal] = useState(false);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [bulkMsg, setBulkMsg] = useState("");

  const key = `/api/accounts${qs({ q, stage: stage ? [stage] : [], client_id: clientId, supplier_id: supplierId, batch_id: batchId, adspower_group: adsGroup, signal, limit: String(PAGE), offset: String(page * PAGE) })}`;
  const { data, mutate } = useSWR<AccountList>(key, fetcher, { keepPreviousData: true });
  const { data: clients } = useSWR<Client[]>("/api/clients", fetcher);
  const { data: suppliers } = useSWR<Supplier[]>("/api/suppliers", fetcher);
  const { data: batches } = useSWR<Batch[]>("/api/batches", fetcher);
  const { data: adsGroups } = useSWR<{ group: string | null; count: number }[]>("/api/accounts/groups", fetcher);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const write = canWrite(user);
  const sel = useMemo(() => items.filter((a) => selected.has(a.id)), [items, selected]);
  const bulkNext = sel.filter((a) => forwardStage(a.stage) && forwardStage(a.stage) !== "issued");

  const reset = (fn: () => void) => { fn(); setPage(0); setSelected(new Set()); };

  async function bulkForward() {
    let ok = 0, fail = 0;
    for (const a of bulkNext) {
      try { await api(`/accounts/${a.id}/transition`, { body: { to: forwardStage(a.stage) } }); ok++; } catch { fail++; }
    }
    setBulkMsg(`Переведено: ${ok}${fail ? `, помилок: ${fail}` : ""}`);
    setSelected(new Set());
    mutate();
  }

  return (
    <>
      <PageHeader title="Акаунти" sub={`${total} за поточним фільтром`}
        right={write && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={15} />Новий акаунт</Button>} />

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-divider p-4">
          <div className="relative min-w-64 flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <Input className="pl-9" placeholder="Код, ad account ID, профіль AdsPower, клієнт…" value={q} onChange={(e) => reset(() => setQ(e.target.value))} />
          </div>
          <Select className="w-40" value={stage} onChange={(e) => reset(() => setStage(e.target.value))} aria-label="Етап">
            <option value="">Усі етапи</option>
            {STAGES.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
          </Select>
          <Select className="w-40" value={clientId} onChange={(e) => reset(() => setClientId(e.target.value))} aria-label="Клієнт">
            <option value="">Усі клієнти</option>
            {clients?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select className="w-44" value={supplierId} onChange={(e) => reset(() => setSupplierId(e.target.value))} aria-label="Постачальник">
            <option value="">Усі постачальники</option>
            {suppliers?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select className="w-44" value={batchId} onChange={(e) => reset(() => setBatchId(e.target.value))} aria-label="Партія">
            <option value="">Усі партії</option>
            {batches?.map((b) => <option key={b.id} value={b.id}>{b.supplier_name} · {b.bought_at} · {b.qty}шт</option>)}
          </Select>
          <Select className="w-48" value={adsGroup} onChange={(e) => reset(() => setAdsGroup(e.target.value))} aria-label="Група AdsPower">
            <option value="">Усі групи AdsPower</option>
            {adsGroups?.map((g) => <option key={g.group ?? "none"} value={g.group ?? ""}>{g.group ?? "— без групи —"} ({g.count})</option>)}
          </Select>
          <label className="flex items-center gap-2 text-[13px] text-muted cursor-pointer">
            <input type="checkbox" className="accent-[var(--accent)]" checked={signal} onChange={(e) => reset(() => setSignal(e.target.checked))} />Лише сигнали
          </label>
        </div>

        {write && sel.length > 0 && (
          <div className="flex items-center gap-3 border-b border-divider bg-[var(--warning-bg)] px-5 py-2.5 text-[13px]">
            <span>Обрано: <b>{sel.length}</b></span>
            <Button size="sm" variant="primary" disabled={!bulkNext.length} onClick={bulkForward}>
              <ArrowRight size={14} />На наступний етап ({bulkNext.length})
            </Button>
            <button className="text-muted hover:text-main cursor-pointer" onClick={() => setSelected(new Set())}>Зняти вибір</button>
          </div>
        )}
        {bulkMsg && <p className="border-b border-divider px-5 py-2 text-[13px] text-muted">{bulkMsg}</p>}

        <AccountsTable items={items} showCost={user?.role === "admin"}
          selected={write ? selected : undefined} onToggle={write ? (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }) : undefined}
          onToggleAll={() => setSelected((s) => items.every((a) => s.has(a.id)) ? new Set() : new Set(items.map((a) => a.id)))} />

        {total > PAGE && (
          <div className="flex items-center justify-between border-t border-divider px-5 py-3 text-[13px] text-muted">
            <span>{page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} з {total}</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</Button>
              <Button size="sm" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Далі</Button>
            </div>
          </div>
        )}
      </Card>

      {creating && <CreateAccount suppliers={suppliers ?? []} isAdmin={user?.role === "admin"} onClose={() => setCreating(false)} onDone={() => { setCreating(false); mutate(); }} />}
    </>
  );
}

function CreateAccount({ suppliers, isAdmin, onClose, onDone }: { suppliers: Supplier[]; isAdmin: boolean; onClose: () => void; onDone: () => void }) {
  const [supplier, setSupplier] = useState("");
  const [cost, setCost] = useState("");
  const [error, setError] = useState("");
  async function save() {
    try {
      await api<Account>("/accounts", { body: { supplier_id: supplier || null, purchase_cost: cost || null } });
      onDone();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Новий акаунт" onClose={onClose}>
      <p className="text-[13px] text-muted">Код (FB-XXXX) призначиться автоматично. Для купівлі пачкою краще додати партію в «Постачальниках».</p>
      <Field label="Постачальник">
        <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
          <option value="">—</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </Field>
      {isAdmin && <Field label="Собівартість, $"><Input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} /></Field>}
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save}>Створити</Button></div>
    </Modal>
  );
}
