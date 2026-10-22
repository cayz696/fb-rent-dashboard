"use client";
import { Check, GitBranch, Laptop, Plus, Shield } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { ALL_SECTIONS, isAdmin, useMe } from "@/lib/session";
import { CMD_LABEL, CMD_STATUS } from "@/components/accounts/adspower";
import type { Account, BridgeCommand, BridgeStatus, AccountList, CloverStatus, Role, SystemStatus, Unmatched, UserAdmin } from "@/lib/types";
import { fmtDateTime, money } from "@/lib/utils";

const th = "px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-faint";
const ROLES: Record<Role, string> = { admin: "Адмін", operator: "Оператор", viewer: "Перегляд" };

export default function SettingsPage() {
  const { user } = useMe();
  if (!isAdmin(user)) return <><PageHeader title="Налаштування" /><div className="panel"><Empty>Розділ доступний лише адміну.</Empty></div></>;
  return (
    <>
      <PageHeader title="Налаштування" />
      <div className="space-y-5">
        <Users meId={user!.id} />
        <DesktopGithubCard />
        <Clover />
        <Bridge />
        <Card>
          <CardHeader title="Інтеграції, що підключаються пізніше" />
          <ul className="divide-y divide-divider text-[13px]">
            {[["Telegram", "Останній етап: userbot для читання чатів + бот адміна"], ["ШІ-агент", "MVP-5: чат і інструменти"]].map(([n, t]) => (
              <li key={n} className="flex justify-between px-5 py-3.5"><span className="font-medium">{n}</span><span className="text-muted">{t}</span></li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

function Users({ meId }: { meId: string }) {
  const { data, mutate } = useSWR<UserAdmin[]>("/api/users", fetcher);
  const [creating, setCreating] = useState(false);
  const [pwFor, setPwFor] = useState<UserAdmin | null>(null);
  const [sectionsFor, setSectionsFor] = useState<UserAdmin | null>(null);
  const [error, setError] = useState("");

  async function patch(u: UserAdmin, body: object) {
    setError("");
    try { await api(`/users/${u.id}`, { method: "PATCH", body }); mutate(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <Card>
      <CardHeader title="Користувачі, ролі та обмежені права доступу" right={<Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} />Користувач</Button>} />
      <div className="px-5 pt-3"><ErrorNote>{error}</ErrorNote></div>
      <div className="overflow-x-auto"><table className="w-full text-[13px]">
        <thead><tr className="border-b border-divider bg-inset/50"><th className={th}>Логін</th><th className={th}>Ім&apos;я</th><th className={th}>Роль</th><th className={th}>Доступні розділи</th><th className={th}>2FA</th><th className={th}>Статус</th><th className={th}></th></tr></thead>
        <tbody>
          {data?.map((u) => (
            <tr key={u.id} className="border-b border-divider last:border-0">
              <td className="px-5 py-3 font-mono">{u.username}</td>
              <td className="px-5 py-3">{u.name}</td>
              <td className="px-5 py-3">
                <Select className="h-8 w-32" value={u.role} onChange={(e) => patch(u, { role: e.target.value })} aria-label={`Роль ${u.username}`}>
                  {(Object.keys(ROLES) as Role[]).map((r) => <option key={r} value={r}>{ROLES[r]}</option>)}
                </Select>
              </td>
              <td className="px-5 py-3">
                {u.role === "admin" || !u.allowed_sections ? (
                  <span className="rounded bg-inset px-2 py-0.5 text-[11px] text-muted">Усі за роллю ({ROLES[u.role]})</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {u.allowed_sections.map((sec) => {
                      const label = ALL_SECTIONS.find((s) => s.key === sec)?.label ?? sec;
                      return <span key={sec} className="rounded bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent">{label}</span>;
                    })}
                  </div>
                )}
              </td>
              <td className="px-5 py-3 text-muted">{u.totp_enabled ? "увімкнено" : "не налаштовано"}</td>
              <td className="px-5 py-3">{u.is_active ? <span className="text-success">активний</span> : <span className="text-faint">вимкнений</span>}</td>
              <td className="px-5 py-3">
                <div className="flex justify-end gap-2">
                  {u.role !== "admin" && (
                    <Button size="sm" onClick={() => setSectionsFor(u)}><Shield size={13} />Права</Button>
                  )}
                  <Button size="sm" onClick={() => setPwFor(u)}>Пароль</Button>
                  <Button size="sm" disabled={!u.totp_enabled} onClick={() => confirm(`Скинути 2FA для ${u.username}? Користувач налаштує її заново при наступному вході.`) && patch(u, { reset_2fa: true })}>Скинути 2FA</Button>
                  <Button size="sm" variant={u.is_active ? "danger" : "ghost"} disabled={u.id === meId} onClick={() => patch(u, { is_active: !u.is_active })}>{u.is_active ? "Вимкнути" : "Увімкнути"}</Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {creating && <CreateUser onClose={() => setCreating(false)} onDone={() => { setCreating(false); mutate(); }} />}
      {pwFor && <Password u={pwFor} onClose={() => setPwFor(null)} onDone={() => { setPwFor(null); mutate(); }} />}
      {sectionsFor && <EditSectionsModal u={sectionsFor} onClose={() => setSectionsFor(null)} onDone={() => { setSectionsFor(null); mutate(); }} />}
    </Card>
  );
}

function CreateUser({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ username: "", name: "", role: "operator" as Role, password: "" });
  const [limitSections, setLimitSections] = useState(false);
  const [selected, setSelected] = useState<string[]>(["overview", "buyers", "cards"]);
  const [error, setError] = useState("");

  function toggleSection(key: string) {
    setSelected((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]);
  }

  async function save() {
    try {
      await api("/users", {
        body: {
          ...f,
          allowed_sections: f.role === "admin" || !limitSections ? null : selected,
        },
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <Modal title="Новий користувач" onClose={onClose}>
      <Field label="Логін"><Input autoFocus value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
      <Field label="Ім'я"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Роль" hint="Оператор — етапи без видачі й фінансів. Перегляд — лише читання.">
        <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>{(Object.keys(ROLES) as Role[]).map((r) => <option key={r} value={r}>{ROLES[r]}</option>)}</Select>
      </Field>
      {f.role !== "admin" && (
        <div className="rounded-lg border border-line bg-inset/50 p-3">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] font-medium">
            <input type="checkbox" checked={limitSections} onChange={(e) => setLimitSections(e.target.checked)} className="h-4 w-4 accent-accent" />
            Обмежити доступ лише до вибраних вкладок дашборду
          </label>
          {limitSections && (
            <div className="mt-2.5 grid grid-cols-2 gap-1.5 border-t border-divider pt-2.5">
              {ALL_SECTIONS.map((s) => (
                <label key={s.key} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[12px] hover:bg-surface-hover">
                  <input type="checkbox" checked={selected.includes(s.key)} onChange={() => toggleSection(s.key)} className="h-3.5 w-3.5 accent-accent" />
                  <span>{s.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}
      <Field label="Початковий пароль" hint="Мінімум 8 символів. 2FA користувач налаштує при першому вході."><Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={f.username.length < 3 || !f.name || f.password.length < 8 || (limitSections && selected.length === 0)}>Створити</Button></div>
    </Modal>
  );
}

function EditSectionsModal({ u, onClose, onDone }: { u: UserAdmin; onClose: () => void; onDone: () => void }) {
  const [limitSections, setLimitSections] = useState<boolean>(Array.isArray(u.allowed_sections) && u.allowed_sections.length > 0);
  const [selected, setSelected] = useState<string[]>(u.allowed_sections ?? ["overview", "buyers", "cards"]);
  const [error, setError] = useState("");

  function toggleSection(key: string) {
    setSelected((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]);
  }

  async function save() {
    try {
      await api(`/users/${u.id}`, {
        method: "PATCH",
        body: { allowed_sections: limitSections ? selected : null },
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title={`Права доступу: ${u.username}`} onClose={onClose}>
      <label className="flex cursor-pointer items-center gap-2 text-[13px] font-medium">
        <input type="checkbox" checked={limitSections} onChange={(e) => setLimitSections(e.target.checked)} className="h-4 w-4 accent-accent" />
        Індивідуальний список дозволених розділів
      </label>
      {limitSections ? (
        <div className="grid grid-cols-2 gap-1.5 rounded-lg border border-line bg-inset/50 p-3">
          {ALL_SECTIONS.map((s) => (
            <label key={s.key} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[12.5px] hover:bg-surface-hover">
              <input type="checkbox" checked={selected.includes(s.key)} onChange={() => toggleSection(s.key)} className="h-3.5 w-3.5 accent-accent" />
              <span>{s.label}</span>
            </label>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-muted">Користувач бачитиме стандартні розділи відповідно до своєї ролі ({ROLES[u.role]}).</p>
      )}
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Скасувати</Button>
        <Button variant="primary" onClick={save} disabled={limitSections && selected.length === 0}><Check size={14} />Зберегти права</Button>
      </div>
    </Modal>
  );
}

function DesktopGithubCard() {
  const { data: st } = useSWR<SystemStatus>("/api/system/status", fetcher);

  return (
    <Card>
      <CardHeader
        title="Версія на цій машині"
        right={
          st?.commit ? (
            <span className="rounded bg-inset px-2 py-0.5 font-mono text-[11px] text-muted">
              <GitBranch size={11} className="mr-1 inline" />
              {st.branch || "main"} @ {st.commit}
            </span>
          ) : undefined
        }
      />
      <div className="space-y-3 p-5 text-[13px]">
        <div className="flex items-start gap-3 rounded-lg border border-line bg-inset/40 p-3.5">
          <Laptop size={18} className="mt-0.5 shrink-0 text-accent" />
          <div className="space-y-1">
            <div className="font-medium">Оновлення коду не запускається з браузера</div>
            <p className="text-[12px] text-muted">
              На машині з дашбордом виконайте <code className="font-mono">desktop/update.sh</code>. Скрипт приймає лише remote на github.com, робить <code className="font-mono">git pull --ff-only</code> і міграції.
              {st?.remote_url ? <> Зараз origin: <code className="font-mono">{st.remote_url}</code>.</> : " Remote origin ще не налаштований локально."}
            </p>
            {st?.last_commit_msg && <div className="text-[11px] text-faint">Останній коміт: {st.last_commit_msg}</div>}
          </div>
        </div>
      </div>
    </Card>
  );
}

function Password({ u, onClose, onDone }: { u: UserAdmin; onClose: () => void; onDone: () => void }) {
  const [pw, setPw] = useState(""); const [error, setError] = useState("");
  async function save() { try { await api(`/users/${u.id}`, { method: "PATCH", body: { password: pw } }); onDone(); } catch (e) { setError((e as Error).message); } }
  return (
    <Modal title={`Новий пароль: ${u.username}`} onClose={onClose}>
      <Field label="Пароль"><Input autoFocus type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={pw.length < 8}>Зберегти</Button></div>
    </Modal>
  );
}

function Clover() {
  const { data: st } = useSWR<CloverStatus>("/api/clover/status", fetcher, { refreshInterval: 30000 });
  const { data: un, mutate } = useSWR<Unmatched[]>("/api/clover/unmatched", fetcher, { refreshInterval: 30000 });
  const [linking, setLinking] = useState<Unmatched | null>(null);
  const endpoint = typeof window !== "undefined" ? `${window.location.origin}/api/clover/spend` : "/api/clover/spend";

  return (
    <Card>
      <CardHeader title="Clover Spend Export" right={
        <span className="font-mono text-[12px]" style={{ color: !st?.last_received ? "var(--text-faint)" : st.stale ? "var(--stage-off-fg)" : "var(--success)" }}>
          {!st?.last_received ? "даних ще не було" : `${st.stale ? "застарілі · " : "ок · "}${fmtDateTime(st.last_received)}`}
        </span>} />
      <div className="space-y-3 p-5 text-[13px]">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted">Ендпоінт для Clover</div>
          <code className="mt-1 block rounded-md border border-line bg-inset px-3 py-2 font-mono text-[12px]">POST {endpoint}</code>
          <p className="mt-2 text-[12px] text-muted">Авторизація: заголовок <code className="font-mono">X-Clover-Secret</code> або <code className="font-mono">?token=</code>. Секрет задається змінною <code className="font-mono">CLOVER_SPEND_SECRET</code> у <code className="font-mono">.env</code> сервера. Формат payload уточнимо за реальним прикладом — сирі дані зберігаються ({st?.snapshots ?? 0} записів).</p>
        </div>
      </div>
      <div className="border-t border-divider">
        <div className="px-5 py-3 text-[13px] font-semibold">Нерозпізнані кабінети {!!un?.length && <span className="ml-1 font-mono text-warning">{un.length}</span>}</div>
        {un && !un.length ? <Empty>Усі кабінети з Clover зіставлені з акаунтами</Empty> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-y border-divider bg-inset/50"><th className={th}>Ad account ID</th><th className={th}>Сьогодні</th><th className={th}>Загалом</th><th className={th}>Записів</th><th className={th}>Останній</th><th className={th}></th></tr></thead>
            <tbody>
              {un?.map((u) => (
                <tr key={u.ad_account_id} className="border-b border-divider last:border-0">
                  <td className="px-5 py-3 font-mono">{u.ad_account_id}</td>
                  <td className="px-5 py-3 font-mono">{money(u.spend_today)}</td><td className="px-5 py-3 font-mono text-muted">{money(u.spend_total)}</td>
                  <td className="px-5 py-3 font-mono text-muted">{u.snapshots}</td><td className="px-5 py-3 font-mono text-[12px] text-muted">{fmtDateTime(u.last_received)}</td>
                  <td className="px-5 py-3 text-right"><Button size="sm" variant="primary" onClick={() => setLinking(u)}>Прив'язати</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {linking && <LinkModal u={linking} onClose={() => setLinking(null)} onDone={() => { setLinking(null); mutate(); }} />}
    </Card>
  );
}

function LinkModal({ u, onClose, onDone }: { u: Unmatched; onClose: () => void; onDone: () => void }) {
  const [q, setQ] = useState("");
  const { data } = useSWR<AccountList>(`/api/accounts?q=${encodeURIComponent(q)}&limit=30`, fetcher, { keepPreviousData: true });
  const [acc, setAcc] = useState<Account | null>(null);
  const [error, setError] = useState("");
  async function save() { try { await api("/clover/link", { body: { ad_account_id: u.ad_account_id, account_id: acc!.id } }); onDone(); } catch (e) { setError((e as Error).message); } }
  return (
    <Modal title={`Прив'язати кабінет ${u.ad_account_id}`} onClose={onClose}>
      <Input autoFocus placeholder="Пошук акаунта за кодом, клієнтом…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="max-h-60 space-y-1 overflow-y-auto">
        {data?.items.map((a) => (
          <button key={a.id} onClick={() => setAcc(a)} className={`flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-left hover:bg-surface-hover ${acc?.id === a.id ? "bg-surface-active ring-1 ring-accent" : ""}`}>
            <span className="font-mono font-semibold text-accent">{a.code}</span><span className="text-muted">{a.client_name ?? a.supplier_name ?? ""}</span>
            <span className="ml-auto font-mono text-[11px] text-faint">{a.ad_account_id ?? ""}</span>
          </button>
        ))}
      </div>
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2"><Button onClick={onClose}>Скасувати</Button><Button variant="primary" onClick={save} disabled={!acc}>Прив'язати</Button></div>
    </Modal>
  );
}

function Bridge() {
  const { data: st } = useSWR<BridgeStatus>("/api/bridge/status", fetcher, { refreshInterval: 10000 });
  const { data: cmds } = useSWR<BridgeCommand[]>("/api/bridge/commands?limit=15", fetcher, { refreshInterval: 10000 });
  return (
    <Card>
      <CardHeader title="AdsPower bridge" right={
        <span className="font-mono text-[12px]" style={{ color: !st?.last_seen ? "var(--text-faint)" : st.online ? "var(--success)" : "var(--stage-off-fg)" }}>
          {!st?.last_seen ? "ще не підключався" : `${st.online ? "онлайн" : "офлайн"} · ${fmtDateTime(st.last_seen)}`}
        </span>} />
      <div className="space-y-2 p-5 text-[13px] text-muted">
        <p>Bridge запускається на машині з AdsPower (<code className="font-mono">python -m bridge.main</code> у <code className="font-mono">apps/bridge</code>), сам підключається до сервера по WebSocket і виконує лише білий список команд. У черзі: <b className="font-mono text-main">{st?.pending ?? 0}</b></p>
        <p>Токен — змінна <code className="font-mono">BRIDGE_TOKEN</code> у <code className="font-mono">.env</code> сервера й bridge; ключ AdsPower API зберігається лише на машині bridge.</p>
      </div>
      {cmds && !!cmds.length && (
        <div className="overflow-x-auto border-t border-divider">
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-divider bg-inset/50"><th className={th}>Час</th><th className={th}>Команда</th><th className={th}>Ціль</th><th className={th}>Хто</th><th className={th}>Статус</th></tr></thead>
            <tbody>
              {cmds.map((c) => (
                <tr key={c.id} className="border-b border-divider last:border-0">
                  <td className="whitespace-nowrap px-5 py-2.5 font-mono text-[12px] text-muted">{fmtDateTime(c.created_at)}</td>
                  <td className="px-5 py-2.5">{CMD_LABEL[c.command] ?? c.command}</td>
                  <td className="px-5 py-2.5 font-mono text-[12px] text-muted">{c.args.name ?? c.args.profile_id ?? "—"}</td>
                  <td className="px-5 py-2.5 text-muted">{c.created_by_name ?? "—"}</td>
                  <td className="px-5 py-2.5 font-mono" style={{ color: CMD_STATUS[c.status].color }}>{CMD_STATUS[c.status].label}{c.status === "error" && <span className="ml-2 text-[11px]">{String(c.result?.error ?? "")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
