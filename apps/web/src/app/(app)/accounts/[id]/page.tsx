"use client";
import { ArrowLeft, ArrowRight, LineChart, RotateCcw, Tag, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { AdsPowerCard } from "@/components/accounts/adspower";
import { AccountFbmCard } from "@/components/accounts/fbm-card";
import { EventList } from "@/components/accounts/events";
import { SpendChart } from "@/components/accounts/spend-chart";
import { doTransition, needsDialog, TransitionDialog } from "@/components/accounts/transition";
import { Button, Card, CardHeader, ErrorNote, Field, Input, Mono, StageBadge, Textarea } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import { forwardStage, STAGE_LABEL } from "@/lib/stages";
import type { Account, AccountEvent, Stage } from "@/lib/types";
import { fmtDateTime, money, timeLeft } from "@/lib/utils";

const EDIT = ["ad_account_id", "adspower_profile_id", "bm_label", "card_last4", "timezone", "spend_limit", "notes"] as const;

export default function AccountCard() {
  const { id } = useParams<{ id: string }>();
  const { user } = useMe();
  const { data: acc, mutate } = useSWR<Account>(`/api/accounts/${id}`, fetcher);
  const { data: events, mutate: mutateEvents } = useSWR<AccountEvent[]>(`/api/accounts/${id}/events`, fetcher);
  const [form, setForm] = useState<Record<string, string>>({});
  const [dialog, setDialog] = useState<Stage | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const write = canWrite(user);

  useEffect(() => {
    if (acc) setForm(Object.fromEntries(EDIT.map((k) => [k, (acc[k] as string | null) ?? ""])));
  }, [acc]);

  if (!acc) return <p className="text-muted">Завантаження…</p>;

  const refresh = (a?: Account) => { if (a) mutate(a, { revalidate: false }); mutate(); mutateEvents(); setDialog(null); };

  async function go(to: Stage) {
    setError("");
    if (needsDialog(to)) return setDialog(to);
    try { refresh(await doTransition(acc!.id, { to })); } catch (e) { setError((e as Error).message); }
  }

  async function save() {
    setError(""); setSaved(false);
    const body: Record<string, string | null> = {};
    for (const k of EDIT) body[k] = form[k] === "" ? null : form[k];
    try { refresh(await api<Account>(`/accounts/${acc!.id}`, { method: "PATCH", body })); setSaved(true); } catch (e) { setError((e as Error).message); }
  }

  const next = forwardStage(acc.stage);
  const canIssue = acc.next_stages.includes("issued") && user?.role === "admin";
  const canSell = acc.next_stages.includes("sold") && user?.role === "admin";
  const dirty = EDIT.some((k) => (form[k] ?? "") !== ((acc[k] as string | null) ?? ""));

  return (
    <>
      <Link href="/accounts" className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-main"><ArrowLeft size={14} />Усі акаунти</Link>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h1 className="font-mono text-[28px] font-bold text-accent">{acc.code}</h1>
          <StageBadge stage={acc.stage} offReason={acc.off_reason} />
        </div>
        {write && (
          <div className="flex flex-wrap gap-2">
            {next && next !== "issued" && acc.next_stages.includes(next) && (
              <Button variant="primary" onClick={() => go(next)}>{STAGE_LABEL[next]}<ArrowRight size={15} /></Button>
            )}
            {canIssue && <Button variant="primary" onClick={() => go("issued")}>Видати клієнту…</Button>}
            {canSell && <Button onClick={() => go("sold")}><Tag size={15} />Продати…</Button>}
            {acc.next_stages.includes("returned") && <Button onClick={() => go("returned")}><Undo2 size={15} />Повернено від клієнта</Button>}
            {acc.next_stages.includes("ready") && acc.stage !== "checking" && next !== "ready" && <Button onClick={() => go("ready")}><RotateCcw size={15} />В Готові</Button>}
            {acc.next_stages.includes("off") && <Button variant="danger" onClick={() => go("off")}>В Off…</Button>}
          </div>
        )}
      </div>
      <ErrorNote>{error}</ErrorNote>

      <div className="mt-2 grid grid-cols-2 gap-4 xl:grid-cols-5">
        {[
          acc.stage === "sold"
            ? ["Продано", `${acc.sold_to ?? "—"}${acc.sale_price ? " · " + money(acc.sale_price) : ""}`]
            : ["Клієнт", acc.client_name ?? "—"],
          ["Спенд сьогодні", acc.spend_today !== null ? money(acc.spend_today) : "—"],
          ["Ліміт", acc.spend_limit ? money(acc.spend_limit) : "—"],
          ["Всього / Оголошення", `${acc.spend_total !== null ? money(acc.spend_total) : "—"}${acc.ads_active !== null ? ` · ${acc.ads_active}${acc.ads_issues ? ` (+${acc.ads_issues} err)` : ""}` : ""}`],
          acc.stage === "checking" && acc.check_until
            ? ["Перевірка 24г", `ще ${timeLeft(acc.check_until)}`]
            : user?.role === "admin" ? ["Собівартість", money(acc.purchase_cost)] : ["Створено", fmtDateTime(acc.created_at)],
        ].map(([l, v]) => (
          <div key={l} className="panel kpi-glow p-5">
            <div className="text-[13px] text-muted">{l}</div>
            <div className="mt-2 font-mono text-[22px] font-semibold">{v}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-5">
          <AdsPowerCard acc={acc} canWrite={write} onChanged={() => { mutate(); mutateEvents(); }} />
          <AccountFbmCard acc={acc} />
          <Card>
            <CardHeader title="Прив'язки й дані" />
            <div className="space-y-4 p-5">
              <Field label="Ad account ID" hint="Ключ зшивки з Clover"><Input disabled={!write} value={form.ad_account_id ?? ""} onChange={(e) => setForm({ ...form, ad_account_id: e.target.value })} /></Field>
              <Field label="Профіль AdsPower"><Input disabled={!write} value={form.adspower_profile_id ?? ""} onChange={(e) => setForm({ ...form, adspower_profile_id: e.target.value })} /></Field>
              <Field label="БМ (назва / позначка)"><Input disabled={!write} value={form.bm_label ?? ""} onChange={(e) => setForm({ ...form, bm_label: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Карта, last4" hint="Лише 4 останні цифри"><Input disabled={!write} inputMode="numeric" maxLength={4} value={form.card_last4 ?? ""} onChange={(e) => setForm({ ...form, card_last4: e.target.value.replace(/\D/g, "") })} /></Field>
                <Field label="Ліміт, $"><Input disabled={!write} type="number" min="0" value={form.spend_limit ?? ""} onChange={(e) => setForm({ ...form, spend_limit: e.target.value })} /></Field>
              </div>
              <Field label="Часовий пояс"><Input disabled={!write} value={form.timezone ?? ""} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></Field>
              <Field label="Нотатка (лише для адмінів)" hint="Не зберігайте тут паролі, повні номери карт, cookies чи TOTP-секрети.">
                <Textarea disabled={!write} value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </Field>
              {write && (
                <div className="flex items-center gap-3">
                  <Button variant="primary" onClick={save} disabled={!dirty}>Зберегти</Button>
                  {saved && !dirty && <span className="text-[12px] text-success">Збережено</span>}
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Спенд 7 / 30 днів" icon={<LineChart size={16} />} />
            <SpendChart accountId={acc.id} hasAdId={!!acc.ad_account_id} />
          </Card>
          <Card>
            <CardHeader title="Журнал подій" right={<span className="font-mono text-[12px] text-faint">{events?.length ?? 0}</span>} />
            <EventList events={events ?? []} />
          </Card>
        </div>
      </div>

      {dialog && <TransitionDialog account={acc} target={dialog} onClose={() => setDialog(null)} onDone={refresh} />}
    </>
  );
}
