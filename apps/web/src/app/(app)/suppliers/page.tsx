"use client";
import { Plus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/session";
import type { Batch, Supplier } from "@/lib/types";
import { money } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

function Inner() {
  const { user } = useMe();
  const admin = isAdmin(user);
  const params = useSearchParams();
  const { data: suppliers, mutate: mutS } = useSWR<Supplier[]>("/api/suppliers", fetcher);
  const { data: batches, mutate: mutB } = useSWR<Batch[]>("/api/batches", fetcher);
  const [modal, setModal] = useState<"supplier" | "batch" | null>(params.get("new") === "batch" ? "batch" : null);

  return (
    <>
      <PageHeader title="Постачальники і партії" sub="Закупівлі, собівартість, відсоток відвалу по партіях"
        right={admin && (
          <div className="flex gap-2">
            <Button onClick={() => setModal("supplier")}><Plus size={15} />Постачальник</Button>
            <Button variant="primary" onClick={() => setModal("batch")}><Plus size={15} />Додати партію</Button>
          </div>
        )} />

      <Card>
        <CardHeader title="Партії" />
        {batches && !batches.length ? <Empty>Партій ще немає. «Додати партію» створить потрібну кількість акаунтів зі статусом «Куплено».</Empty> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-divider bg-inset/50">
              <th className={th}>Дата</th><th className={th}>Постачальник</th><th className={th}>К-сть</th>
              {admin && <th className={th}>Ціна/шт</th>}<th className={th}>У Off</th><th className={th}>% відвалу</th>
            </tr></thead>
            <tbody>
              {batches?.map((b) => {
                const pct = b.accounts_total ? Math.round((b.accounts_off / b.accounts_total) * 100) : 0;
                return (
                  <tr key={b.id} className="border-b border-divider last:border-0 hover:bg-surface-hover">
                    <td className="px-5 py-3.5 font-mono text-muted">{b.bought_at}</td>
                    <td className="px-5 py-3.5">{b.supplier_name}</td>
                    <td className="px-5 py-3.5 font-mono">{b.accounts_total}<span className="text-faint"> / {b.qty}</span></td>
                    {admin && <td className="px-5 py-3.5 font-mono">{money(b.unit_cost)}</td>}
                    <td className="px-5 py-3.5 font-mono">{b.accounts_off}</td>
                    <td className="px-5 py-3.5 font-mono" style={{ color: pct > 30 ? "var(--stage-off-fg)" : undefined }}>{pct}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="mt-5">
        <CardHeader title="Постачальники" />
        {suppliers && !suppliers.length ? <Empty>Постачальників ще немає</Empty> : (
          <ul className="divide-y divide-divider">
            {suppliers?.map((s) => (
              <li key={s.id} className="flex justify-between px-5 py-3.5 text-[13px]">
                <span className="font-semibold">{s.name}</span><span className="text-muted">{s.contact ?? "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {modal === "supplier" && <SupplierModal onClose={() => setModal(null)} onDone={() => { setModal(null); mutS(); }} />}
      {modal === "batch" && <BatchModal suppliers={suppliers ?? []} onClose={() => setModal(null)} onDone={() => { setModal(null); mutB(); }} />}
    </>
  );
}

function SupplierModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(""); const [contact, setContact] = useState(""); const [notes, setNotes] = useState(""); const [error, setError] = useState("");
  async function save() {
    try { await api("/suppliers", { body: { name: name.trim(), contact: contact || null, notes: notes || null } }); onDone(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Новий постачальник" onClose={onClose}>
      <Field label="Назва"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Контакт"><Input value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
      <Field label="Нотатки"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!name.trim()}>Створити</Button></div>
    </Modal>
  );
}

function BatchModal({ suppliers, onClose, onDone }: { suppliers: Supplier[]; onClose: () => void; onDone: () => void }) {
  const [supplier, setSupplier] = useState(""); const [qty, setQty] = useState("10"); const [cost, setCost] = useState(""); const [error, setError] = useState("");
  async function save() {
    try { await api("/batches", { body: { supplier_id: supplier, qty: Number(qty), unit_cost: cost, create_accounts: true } }); onDone(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Нова партія" onClose={onClose}>
      <Field label="Постачальник">
        <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
          <option value="">— оберіть —</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Кількість"><Input type="number" min="1" max="1000" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label="Ціна за шт., $"><Input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} /></Field>
      </div>
      <p className="text-[12px] text-muted">Буде створено {Number(qty) || 0} акаунтів зі статусом «Куплено» та кодами FB-XXXX.</p>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!supplier || !cost || Number(qty) < 1}>Створити партію</Button></div>
    </Modal>
  );
}

export default function SuppliersPage() {
  return <Suspense><Inner /></Suspense>;
}
