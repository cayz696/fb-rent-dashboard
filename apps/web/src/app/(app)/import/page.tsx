"use client";
import { AlertTriangle, CheckCircle2, Download, FileUp, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import { Button, Card, CardHeader, ErrorNote, Field, Input, PageHeader, Select } from "@/components/ui";
import { api, fetcher, upload } from "@/lib/api";
import { canWrite, useMe } from "@/lib/session";
import type { BridgeStatus, ImportPreview, ImportResult, Supplier } from "@/lib/types";

export default function ImportPage() {
  const { user } = useMe();
  const { data: suppliers } = useSWR<Supplier[]>("/api/suppliers", fetcher);
  const { data: bridge } = useSWR<BridgeStatus>("/api/bridge/status", fetcher, { refreshInterval: 10000 });
  const [file, setFile] = useState<File | null>(null);
  const [supplier, setSupplier] = useState("");
  const [via, setVia] = useState<"file" | "bridge">("file");
  const [proxy, setProxy] = useState({ type: "http", host: "", port: "", user: "", password: "" });
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  if (user && !canWrite(user)) return <><PageHeader title="Імпорт замовлення" /><Card className="p-10 text-center text-muted">Доступно для admin та operator.</Card></>;

  function pick(f: File | null) {
    setFile(f); setPreview(null); setResult(null); setError("");
    if (f) run(() => upload<ImportPreview>("/import/order/preview", f).then(setPreview));
  }
  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function download(r: ImportResult) {
    const blob = new Blob([r.adspower_file], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = r.filename; a.click(); URL.revokeObjectURL(url);
  }
  function doImport() {
    if (!file) return;
    run(async () => {
      const params: Record<string, string> = { via };
      if (supplier) params.supplier_id = supplier;
      if (via === "bridge" && proxy.host.trim()) {
        params.proxy_type = proxy.type; params.proxy_host = proxy.host.trim(); params.proxy_port = proxy.port.trim();
        if (proxy.user.trim()) params.proxy_user = proxy.user.trim();
        if (proxy.password) params.proxy_password = proxy.password;
      }
      const r = await upload<ImportResult>("/import/order", file, params);
      setResult(r);
      if (via === "file") download(r);  // у режимі bridge файл не потрібен — профілі створює міст
    });
  }

  return (
    <>
      <PageHeader title="Імпорт замовлення" sub="Файл order_*.txt зі стоку → акаунти в системі + готовий файл для масового імпорту в AdsPower. Замінює ручний крок з ChatGPT." />
      <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <Card className="self-start p-5 space-y-4">
          <div onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0] ?? null); }}
            className="cursor-pointer rounded-lg border-2 border-dashed border-line-strong bg-inset p-8 text-center hover:border-accent">
            <FileUp size={28} className="mx-auto text-faint" />
            <p className="mt-3 text-[13px] text-muted">{file ? file.name : "Перетягніть order_*.txt або натисніть"}</p>
            <input ref={inputRef} type="file" accept=".txt" className="hidden" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          </div>
          <Field label="Постачальник (необов'язково)">
            <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">—</option>{suppliers?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <div className="space-y-2">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted">Спосіб заводу в AdsPower</span>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setVia("file")} className={`rounded-md border px-3 py-2 text-left text-[12px] ${via === "file" ? "border-accent bg-surface-active" : "border-line-strong bg-surface-hover text-muted"}`}>
                <div className="font-semibold text-main">Файл (ручний)</div>Завантажити .txt і імпортувати в AdsPower самому
              </button>
              <button onClick={() => setVia("bridge")} disabled={!bridge?.online}
                className={`rounded-md border px-3 py-2 text-left text-[12px] disabled:opacity-40 ${via === "bridge" ? "border-accent bg-surface-active" : "border-line-strong bg-surface-hover text-muted"}`}>
                <div className="font-semibold text-main">Через міст {bridge?.online ? <span className="text-success">●</span> : <span className="text-faint">офлайн</span>}</div>Bridge сам створить профілі
              </button>
            </div>
          </div>
          {via === "bridge" && (
            <div className="space-y-2 rounded-md border border-line bg-inset p-3">
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted">Проксі (необов'язково, спільний для партії)</span>
              <div className="grid grid-cols-[90px_1fr_80px] gap-2">
                <Select className="h-8" value={proxy.type} onChange={(e) => setProxy({ ...proxy, type: e.target.value })}>
                  <option value="http">http</option><option value="https">https</option><option value="socks5">socks5</option>
                </Select>
                <Input className="h-8" placeholder="host" value={proxy.host} onChange={(e) => setProxy({ ...proxy, host: e.target.value })} />
                <Input className="h-8" placeholder="port" value={proxy.port} onChange={(e) => setProxy({ ...proxy, port: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Input className="h-8" placeholder="логін (опц.)" value={proxy.user} onChange={(e) => setProxy({ ...proxy, user: e.target.value })} />
                <Input className="h-8" type="password" placeholder="пароль (опц.)" value={proxy.password} onChange={(e) => setProxy({ ...proxy, password: e.target.value })} />
              </div>
              <p className="text-[11px] text-faint">Проксі піде лише в AdsPower-профіль (через міст), у базі не зберігається. Порожньо → без проксі.</p>
            </div>
          )}
          <ErrorNote>{error}</ErrorNote>
          <Button variant="primary" className="w-full" disabled={busy || !preview || preview.new === 0} onClick={doImport}>
            <Upload size={15} />{via === "bridge" ? `Імпортувати ${preview?.new ?? 0} і створити профілі` : `Імпортувати ${preview?.new ?? 0} та завантажити файл`}
          </Button>
          <p className="text-[12px] text-faint">Паролі, cookies і 2FA не зберігаються в системі (ТЗ §4) — вони лише у файлі AdsPower, який завантажиться в браузер. Після імпорту в AdsPower видаліть файл.</p>
        </Card>

        <div className="space-y-5">
          {result && (
            <Card className="border border-[var(--success-border)] p-5">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 text-success" size={20} />
                <div className="text-[14px]">
                  <p className="font-semibold">Створено {result.created} акаунтів{result.skipped_duplicates ? `, пропущено дублів: ${result.skipped_duplicates}` : ""}.</p>
                  {result.queued_to_bridge > 0 && <p className="mt-1 text-success">У чергу мосту на створення профілів: {result.queued_to_bridge}. Стежте за статусом у картці акаунта.</p>}
                  {result.queued_to_bridge === 0 && <p className="mt-1 text-muted">Файл <span className="font-mono">{result.filename}</span> завантажено — імпортуйте його в AdsPower (Масовий імпорт). Далі виділіть акаунти й переведіть на «AdsPower».</p>}
                  <p className="mt-2 font-mono text-[12px] text-accent">{result.codes.join(", ")}</p>
                  <Button size="sm" className="mt-3" onClick={() => { const b = new Blob([result.adspower_file], { type: "text/plain" }); const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = result.filename; a.click(); URL.revokeObjectURL(u); }}>
                    <Download size={14} />Завантажити файл ще раз
                  </Button>
                  <Link href="/accounts" className="ml-3 text-[13px] text-accent hover:text-accent-light">До акаунтів →</Link>
                </div>
              </div>
            </Card>
          )}
          {preview && !result && (
            <Card>
              <CardHeader title="Попередній перегляд" right={<span className="text-[13px] text-muted">Нових: <b className="text-main">{preview.new}</b> · дублів: {preview.duplicates}</span>} />
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="border-b border-divider bg-inset/50">
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">Ім'я</th>
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">FB ID</th>
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">Логін</th>
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">GEO</th>
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">2FA</th>
                    <th className="px-4 py-2.5 text-left text-[11px] uppercase tracking-wider text-faint">Статус</th>
                  </tr></thead>
                  <tbody>
                    {preview.rows.map((r, i) => (
                      <tr key={i} className="border-b border-divider last:border-0">
                        <td className="px-4 py-2.5">{r.name}</td>
                        <td className="px-4 py-2.5 font-mono text-[12px]">{r.fb_user_id}</td>
                        <td className="px-4 py-2.5 text-muted">{r.fb_login}</td>
                        <td className="px-4 py-2.5 font-mono">{r.country}</td>
                        <td className="px-4 py-2.5">{r.twofa_ok ? <span className="text-success">✓</span> : <span className="text-faint">—</span>}</td>
                        <td className="px-4 py-2.5">
                          {r.duplicate ? <span className="text-faint">дубль</span>
                            : r.warnings.length ? <span className="flex items-center gap-1 text-warning" title={r.warnings.join("; ")}><AlertTriangle size={13} />{r.warnings.length} застереж.</span>
                            : <span className="text-success">новий</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
          {!preview && !result && (
            <Card className="p-10 text-center text-[13px] text-muted">
              Оберіть файл замовлення, щоб побачити, які акаунти буде додано. Формат — як `order_*.txt` зі стоку (поля через табуляцію).
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
