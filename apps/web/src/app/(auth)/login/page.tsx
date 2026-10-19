"use client";
import { QRCodeSVG } from "qrcode.react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

type Step = "password" | "totp_setup" | "totp_required";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [pre, setPre] = useState("");
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const submitPassword = () => run(async () => {
    const r = await api<{ step: Step; pre_token: string }>("/auth/login", { body: { username, password } });
    setPre(r.pre_token);
    if (r.step === "totp_setup") {
      setSetup(await api(`/auth/2fa/setup?pre_token=${encodeURIComponent(r.pre_token)}`, { method: "POST" }));
    }
    setStep(r.step);
  });

  const submitCode = () => run(async () => {
    await api("/auth/2fa/verify", { body: { pre_token: pre, code } });
    router.replace("/dashboard");
  });

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <div className="panel w-full max-w-sm space-y-6 p-8">
        <div className="flex items-center gap-3">
          <div className="relative size-12 overflow-hidden rounded-xl border border-purple-500/40 shadow-[0_0_18px_rgba(168,85,247,0.4)] shrink-0 bg-black">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt="Skull Partners Logo"
              className="size-full object-cover"
            />
          </div>
          <div>
            <div className="font-semibold text-[17px] text-main">Skull Partners</div>
            <div className="text-[12px] text-muted">Ops Control Panel</div>
          </div>
        </div>

        {step === "password" ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submitPassword(); }}>
            <Field label="Логін"><Input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></Field>
            <Field label="Пароль"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <ErrorNote>{error}</ErrorNote>
            <Button variant="primary" className="w-full" disabled={busy || !username || !password}>Увійти</Button>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submitCode(); }}>
            {step === "totp_setup" && setup && (
              <div className="space-y-3">
                <p className="text-[13px] text-muted">Для входу потрібна двофакторна автентифікація. Скануйте QR у застосунку-автентифікаторі (Google Authenticator, 1Password, Authy).</p>
                <div className="mx-auto w-fit rounded-md bg-white p-3"><QRCodeSVG value={setup.uri} size={148} /></div>
                <p className="break-all text-center font-mono text-[11px] text-faint">{setup.secret}</p>
              </div>
            )}
            <Field label="Код з застосунку">
              <Input autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={6} className="text-center font-mono text-lg tracking-[0.4em]"
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </Field>
            <ErrorNote>{error}</ErrorNote>
            <Button variant="primary" className="w-full" disabled={busy || code.length !== 6}>
              {step === "totp_setup" ? "Підтвердити і увійти" : "Увійти"}
            </Button>
            <button type="button" className="w-full text-[12px] text-muted hover:text-main cursor-pointer" onClick={() => { setStep("password"); setCode(""); setError(""); }}>← Назад</button>
          </form>
        )}
      </div>
    </main>
  );
}
