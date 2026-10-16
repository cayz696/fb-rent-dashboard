"use client";
import { useState } from "react";
import { Button, ErrorNote, Field, Input, Modal, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { Client } from "@/lib/types";

export function ClientForm({ client, onClose, onDone }: { client?: Client; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({
    name: client?.name ?? "", usernames: (client?.telegram_usernames ?? []).join(", "), chat: client?.telegram_chat_id?.toString() ?? "",
    terms: client?.terms ?? "", bm: client?.bm_id ?? "", fee: client?.fee_percent ?? "", balance: client?.balance ?? "0", status: client?.status ?? "active", notes: client?.notes ?? "",
  });
  const [error, setError] = useState("");
  async function save() {
    const body = {
      name: f.name.trim(), telegram_usernames: f.usernames.split(",").map((s) => s.trim().replace(/^@/, "")).filter(Boolean),
      telegram_chat_id: f.chat ? Number(f.chat) : null, terms: f.terms || null, bm_id: f.bm || null, fee_percent: f.fee || null, balance: f.balance || "0", status: f.status, notes: f.notes || null,
    };
    try {
      await api(client ? `/clients/${client.id}` : "/clients", { method: client ? "PUT" : "POST", body });
      onDone();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <Modal title={client ? `Клієнт: ${client.name}` : "Новий клієнт"} onClose={onClose}>
      <Field label="Назва"><Input autoFocus value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Telegram @username(и)" hint="через кому"><Input value={f.usernames} onChange={(e) => setF({ ...f, usernames: e.target.value })} /></Field>
        <Field label="Telegram chat ID"><Input inputMode="numeric" value={f.chat} onChange={(e) => setF({ ...f, chat: e.target.value })} /></Field>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="% від спенду" hint="ставка нарахування"><Input type="number" min="0" max="100" step="0.01" value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} /></Field>
        <Field label="Початк. баланс"><Input type="number" step="0.01" value={f.balance} onChange={(e) => setF({ ...f, balance: e.target.value })} /></Field>
        <Field label="Статус"><Input value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="BM ID клієнта" hint="Business Manager — для розшарювання доступу"><Input value={f.bm} onChange={(e) => setF({ ...f, bm: e.target.value })} /></Field>
        <Field label="Інші умови (текст)"><Input value={f.terms} onChange={(e) => setF({ ...f, terms: e.target.value })} /></Field>
      </div>
      <Field label="Нотатки"><Textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!f.name.trim()}>Зберегти</Button></div>
    </Modal>
  );
}
