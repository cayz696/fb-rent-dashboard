"use client";
import { useState } from "react";
import useSWR from "swr";
import { Button, ErrorNote, Field, Input, Modal, Select, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { OFF_LABEL, STAGE_LABEL } from "@/lib/stages";
import type { Account, Client, OffReason, Stage } from "@/lib/types";

export const needsDialog = (t: Stage) => t === "issued" || t === "off" || t === "sold";

export async function doTransition(id: string, body: Record<string, unknown> & { to: Stage }) {
  return api<Account>(`/accounts/${id}/transition`, { body });
}

export function TransitionDialog({ account, target, onClose, onDone }: { account: Account; target: Stage; onClose: () => void; onDone: (a: Account) => void }) {
  const { data: clients } = useSWR<Client[]>(target === "issued" ? "/api/clients" : null, fetcher);
  const [clientId, setClientId] = useState(account.client_id ?? "");
  const [reason, setReason] = useState<OffReason>("ban");
  const [comment, setComment] = useState("");
  const [soldTo, setSoldTo] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true); setError("");
    try {
      const body =
        target === "issued" ? { to: target, client_id: clientId, confirm_manual: true }
        : target === "sold" ? { to: target, sold_to: soldTo.trim(), sale_price: price }
        : { to: target, off_reason: reason, comment };
      onDone(await doTransition(account.id, body));
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  const valid = target === "issued" ? !!clientId : target === "sold" ? !!soldTo.trim() && !!price : !!comment.trim();

  return (
    <Modal title={`${account.code} → ${STAGE_LABEL[target]}`} onClose={onClose}>
      {target === "issued" && (
        <Field label="Клієнт" hint="Ручна видача без заявки — буде записана в журнал як підтверджена адміном.">
          <Select value={clientId} onChange={(e) => setClientId(e.target.value)}>
            <option value="">— оберіть —</option>
            {clients?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
      )}
      {target === "sold" && (
        <>
          <Field label="Покупець" hint="Кому продано акаунт (окремий напрямок від оренди)."><Input autoFocus value={soldTo} onChange={(e) => setSoldTo(e.target.value)} /></Field>
          <Field label="Ціна продажу, $"><Input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
        </>
      )}
      {target === "off" && (
        <>
          <Field label="Причина">
            <Select value={reason} onChange={(e) => setReason(e.target.value as OffReason)}>
              {(Object.keys(OFF_LABEL) as OffReason[]).map((r) => <option key={r} value={r}>{OFF_LABEL[r]}</option>)}
            </Select>
          </Field>
          <Field label="Коментар (обов'язково)"><Textarea value={comment} onChange={(e) => setComment(e.target.value)} autoFocus /></Field>
        </>
      )}
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant={target === "off" ? "danger" : "primary"} onClick={submit} disabled={busy || !valid}>
          {target === "issued" ? "Видати" : target === "sold" ? "Продати" : "Перевести в Off"}
        </Button>
      </div>
    </Modal>
  );
}
