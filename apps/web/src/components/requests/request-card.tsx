"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Button, ErrorNote, Field, Input, Modal, Select, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import type { AccountList, Client, RequestItem, RequestStatus } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

export const REQ_STATUS: Record<RequestStatus, { label: string; color: string }> = {
  new: { label: "Нова", color: "var(--text-muted)" },
  proposed: { label: "Чекає апруву", color: "var(--warning)" },
  approved: { label: "Схвалена", color: "var(--success)" },
  rejected: { label: "Відхилена", color: "var(--stage-off-fg)" },
  done: { label: "Видано", color: "var(--success)" },
};

export function RequestCard({ r, admin, canEdit, onChange, compact }: { r: RequestItem; admin: boolean; canEdit: boolean; onChange: () => void; compact?: boolean }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [changing, setChanging] = useState(false);
  const open = r.status === "new" || r.status === "proposed";
  const p = r.parsed ?? {};

  async function act(path: string, method = "POST") {
    setBusy(true); setError("");
    try { await api(`/requests/${r.id}${path}`, { method, body: method === "POST" ? {} : undefined }); onChange(); }
    catch (e) { setError((e as Error).message); onChange(); } finally { setBusy(false); }
  }

  return (
    <div className="rounded-lg border border-line bg-inset p-4 text-[13px]">
      <div className="flex items-center justify-between gap-3">
        <span className="font-semibold">{r.client_name ?? "—"}</span>
        <span className="font-mono text-[11px] text-faint">{fmtDateTime(r.created_at)}</span>
      </div>
      <p className="mt-2 border-l-2 border-accent pl-3 text-muted">«{r.raw_text}»</p>
      <div className="mt-3 rounded-md border border-line bg-surface px-3 py-2 text-[12px] text-muted">
        <div>Видача: <b className="text-main">{p.qty ?? "?"} шт</b>{p.geo && <> • GEO {p.geo}</>}{p.limit && <> • Ліміт ${Number(p.limit)}</>}</div>
        <div className="mt-1 font-mono text-[12px]">
          Підібрано:{" "}
          {r.proposed.length ? r.proposed.map((a, i) => (
            <span key={a.id}><Link href={`/accounts/${a.id}`} className="text-accent hover:text-accent-light">{a.code}</Link>{i < r.proposed.length - 1 && ", "}</span>
          )) : <span className="text-faint">немає готових акаунтів</span>}
        </div>
        {!!p.shortage && <div className="mt-1 text-warning">Не вистачає готових акаунтів: {p.shortage}</div>}
      </div>
      {!compact && <div className="mt-2 text-[12px]" style={{ color: REQ_STATUS[r.status].color }}>{REQ_STATUS[r.status].label}{r.approved_by_name && ` · ${r.approved_by_name}`}</div>}
      <ErrorNote>{error}</ErrorNote>
      {open && (
        <div className="mt-3 flex flex-wrap gap-2">
          {admin && <Button variant="primary" size="sm" disabled={busy || !r.proposed.length} onClick={() => act("/approve")}>Апрув і видати</Button>}
          {canEdit && <Button size="sm" disabled={busy} onClick={() => setChanging(true)}>Змінити</Button>}
          {canEdit && <Button size="sm" disabled={busy} onClick={() => act("/propose")}>Підібрати знову</Button>}
          {admin && <Button variant="danger" size="sm" disabled={busy} onClick={() => act("/reject")}>Відхилити</Button>}
        </div>
      )}
      {changing && <ChangeAccounts r={r} onClose={() => setChanging(false)} onDone={() => { setChanging(false); onChange(); }} />}
    </div>
  );
}

function ChangeAccounts({ r, onClose, onDone }: { r: RequestItem; onClose: () => void; onDone: () => void }) {
  const { data } = useSWR<AccountList>("/api/accounts?stage=ready&limit=500", fetcher);
  const [sel, setSel] = useState<Set<string>>(new Set(r.proposed.map((a) => a.id)));
  const [error, setError] = useState("");
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  async function save() {
    try { await api(`/requests/${r.id}/accounts`, { method: "PUT", body: { account_ids: [...sel] } }); onDone(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Змінити акаунти для видачі" onClose={onClose}>
      <p className="text-[12px] text-muted">Потрібно {r.parsed?.qty ?? "?"} шт. Обрано: <b className="text-main">{sel.size}</b></p>
      <div className="max-h-72 space-y-1 overflow-y-auto">
        {data?.items.length === 0 && <p className="py-6 text-center text-muted">Немає акаунтів на етапі «Готовий»</p>}
        {data?.items.map((a) => (
          <label key={a.id} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 hover:bg-surface-hover">
            <input type="checkbox" className="accent-[var(--accent)]" checked={sel.has(a.id)} onChange={() => toggle(a.id)} />
            <span className="font-mono font-semibold text-accent">{a.code}</span>
            <span className="text-muted">{a.supplier_name ?? ""}</span>
            <span className="ml-auto font-mono text-[11px] text-faint">{a.spend_limit ? `$${Number(a.spend_limit)}` : ""}</span>
          </label>
        ))}
      </div>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save}>Зберегти вибір</Button></div>
    </Modal>
  );
}

export function CreateRequest({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { data: clients } = useSWR<Client[]>("/api/clients", fetcher);
  const [f, setF] = useState({ client_id: "", raw_text: "", qty: "1", limit: "", geo: "" });
  const [error, setError] = useState("");
  async function save() {
    try {
      await api("/requests", { body: { client_id: f.client_id, raw_text: f.raw_text.trim(), qty: Number(f.qty), limit: f.limit || null, geo: f.geo || null } });
      onDone();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title="Нова заявка" onClose={onClose}>
      <Field label="Клієнт">
        <Select value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })}>
          <option value="">— оберіть —</option>{clients?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </Field>
      <Field label="Текст запиту" hint="Як написав клієнт (для історії)"><Textarea value={f.raw_text} onChange={(e) => setF({ ...f, raw_text: e.target.value })} /></Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="К-сть"><Input type="number" min="1" max="100" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} /></Field>
        <Field label="Ліміт, $"><Input type="number" min="0" value={f.limit} onChange={(e) => setF({ ...f, limit: e.target.value })} /></Field>
        <Field label="GEO"><Input value={f.geo} onChange={(e) => setF({ ...f, geo: e.target.value })} /></Field>
      </div>
      <p className="text-[12px] text-muted">Система одразу підбере найстаріші за готовністю акаунти. Видача — тільки після апруву адміна.</p>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!f.client_id || !f.raw_text.trim() || Number(f.qty) < 1}>Створити</Button></div>
    </Modal>
  );
}
