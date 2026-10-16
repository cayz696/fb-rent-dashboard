"use client";
import { Plus } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Modal, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { STAGE_LABEL } from "@/lib/stages";
import type { ClientReport, Payment } from "@/lib/types";
import { fmtDate, money } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";

export function ClientFinance({ clientId }: { clientId: string }) {
  const { data: rep, mutate } = useSWR<ClientReport>(`/api/finance/clients/${clientId}`, fetcher);
  const { data: pays, mutate: mutPays } = useSWR<Payment[]>(`/api/finance/clients/${clientId}/payments`, fetcher);
  const [adding, setAdding] = useState(false);
  const refresh = () => { mutate(); mutPays(); };
  if (!rep) return null;

  return (
    <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader title="Нарахування по кабінетах" right={<span className="font-mono text-[12px] text-muted">{Number(rep.fee_percent) ? `${Number(rep.fee_percent)}% від спенду` : "% не задано"}</span>} />
        {!rep.accounts.length ? <Empty>Немає виданих кабінетів зі спендом</Empty> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-divider bg-inset/50"><th className={th}>Кабінет</th><th className={th}>Етап</th><th className={th}>Спенд</th><th className={th}>Нараховано</th></tr></thead>
            <tbody>
              {rep.accounts.map((a) => (
                <tr key={a.id} className="border-b border-divider last:border-0">
                  <td className="px-5 py-3 font-mono font-semibold text-accent">{a.code}</td>
                  <td className="px-5 py-3 text-muted">{STAGE_LABEL[a.stage]}</td>
                  <td className="px-5 py-3 font-mono">{money(a.spend_total)}</td>
                  <td className="px-5 py-3 font-mono">{money(a.accrued)}</td>
                </tr>
              ))}
              <tr className="bg-inset/50 font-semibold"><td className="px-5 py-3" colSpan={2}>Разом</td><td className="px-5 py-3 font-mono">{money(rep.spend_total)}</td><td className="px-5 py-3 font-mono">{money(rep.accrued)}</td></tr>
            </tbody>
          </table>
        )}
      </Card>

      <div className="space-y-5">
        <Card className="p-5">
          <div className="space-y-2 text-[13px]">
            {([["Початковий баланс", rep.initial_balance], ["Оплачено", rep.paid], ["Нараховано", `-${rep.accrued}`]] as const).map(([l, v]) => (
              <div key={l} className="flex justify-between"><span className="text-muted">{l}</span><span className="font-mono">{money(v)}</span></div>
            ))}
            <div className="mt-2 flex justify-between border-t border-divider pt-2 text-[15px] font-semibold">
              <span>Баланс</span><span className="font-mono" style={{ color: Number(rep.balance) < 0 ? "var(--stage-off-fg)" : "var(--success)" }}>{money(rep.balance)}</span>
            </div>
            {Number(rep.balance) < 0 && <p className="text-[12px] text-[var(--stage-off-fg)]">Клієнт винен нам {money(Math.abs(Number(rep.balance)))}</p>}
          </div>
        </Card>
        <Card>
          <CardHeader title="Оплати" right={<Button size="sm" variant="primary" onClick={() => setAdding(true)}><Plus size={14} />Оплата</Button>} />
          {pays && !pays.length ? <Empty>Оплат ще не було</Empty> : (
            <ul className="divide-y divide-divider text-[13px]">
              {pays?.map((p) => (
                <li key={p.id} className="flex items-center justify-between px-5 py-3">
                  <div><div className="font-mono font-semibold" style={{ color: Number(p.amount) < 0 ? "var(--stage-off-fg)" : "var(--success)" }}>{money(p.amount)}</div>{p.note && <div className="text-[12px] text-muted">{p.note}</div>}</div>
                  <div className="text-right text-[12px] text-faint"><div>{fmtDate(p.paid_at)}</div><div>{p.created_by_name}</div></div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {adding && <AddPayment clientId={clientId} onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh(); }} />}
    </div>
  );
}

function AddPayment({ clientId, onClose, onDone }: { clientId: string; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(""); const [note, setNote] = useState(""); const [paidAt, setPaidAt] = useState(""); const [error, setError] = useState("");
  async function save() {
    try { await api(`/finance/clients/${clientId}/payments`, { body: { amount, note: note || null, paid_at: paidAt || null } }); onDone(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Оплата / коригування" onClose={onClose}>
      <Field label="Сума, $" hint="Від'ємна — коригування (напр. повернення)"><Input autoFocus type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
      <Field label="Дата"><Input type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} /></Field>
      <Field label="Примітка"><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!amount || Number(amount) === 0}>Додати</Button></div>
    </Modal>
  );
}
