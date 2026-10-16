"use client";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { OFF_LABEL, STAGE_LABEL, stageTone, TONE_STYLE } from "@/lib/stages";
import type { OffReason, Stage } from "@/lib/types";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-[13px] font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap",
  {
    variants: {
      variant: {
        primary: "bg-accent text-on-accent hover:bg-accent-light shadow-[0_0_16px_var(--accent-glow)]",
        ghost: "border border-line-strong bg-surface-hover text-main hover:bg-surface-active",
        danger: "border border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--stage-off-fg)] hover:brightness-125",
        link: "text-accent hover:text-accent-light px-0",
      },
      size: { md: "h-9 px-4", sm: "h-8 px-3 text-[12px]" },
    },
    defaultVariants: { variant: "ghost", size: "md" },
  },
);
export function Button({ className, variant, size, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>) {
  return <button className={cn(button({ variant, size }), className)} {...p} />;
}

const field = "w-full rounded-md border border-line-strong bg-inset px-3 h-9 text-[13px] text-main placeholder:text-faint focus:border-accent outline-none";
export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => <input className={cn(field, className)} {...p} />;
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => <select className={cn(field, "pr-8", className)} {...p} />;
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cn(field, "h-auto min-h-20 py-2", className)} {...p} />
);

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-faint">{hint}</span>}
    </label>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("panel", className)}>{children}</section>;
}

export function CardHeader({ title, icon, right }: { title: ReactNode; icon?: ReactNode; right?: ReactNode }) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-divider px-5 py-4">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold">{icon}{title}</h2>
      {right}
    </header>
  );
}

export function StageBadge({ stage, offReason }: { stage: Stage; offReason?: OffReason | null }) {
  const t = TONE_STYLE[stageTone(stage)];
  const label = stage === "off" && offReason ? `${OFF_LABEL[offReason]} (Off)` : STAGE_LABEL[stage];
  return (
    <span className="inline-flex items-center rounded-md border px-2 py-0.5 text-[12px] font-medium" style={{ background: t.bg, color: t.fg, borderColor: t.fg + "33" }}>
      {label}
    </span>
  );
}

export function Chip({ active, onClick, children, tone }: { active?: boolean; onClick?: () => void; children: ReactNode; tone?: "danger" }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-[12px] font-medium transition cursor-pointer",
        active ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface-hover text-muted hover:text-main",
        !active && tone === "danger" && "text-[var(--stage-off-fg)] border-[var(--danger-border)] bg-[var(--danger-bg)]",
      )}
    >
      {children}
    </button>
  );
}

export function Modal({ title, onClose, children, width = "max-w-md" }: { title: string; onClose: () => void; children: ReactNode; width?: string }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-label={title} className={cn("panel w-full space-y-4 p-6", width)}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">{title}</h3>
          <button onClick={onClose} aria-label="Закрити" className="text-muted hover:text-main cursor-pointer"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const Mono = ({ children, className }: { children: ReactNode; className?: string }) => (
  <span className={cn("font-mono", className)}>{children}</span>
);

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-5 py-10 text-center text-[13px] text-muted">{children}</div>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return children ? <p className="rounded-md border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-2 text-[13px] text-[var(--stage-off-fg)]">{children}</p> : null;
}

export function PageHeader({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[28px] font-bold tracking-tight">{title}</h1>
        {sub && <div className="mt-1 text-[13px] text-muted">{sub}</div>}
      </div>
      {right}
    </div>
  );
}

export function ComingSoon({ title, mvp, text }: { title: string; mvp: string; text: string }) {
  return (
    <>
      <PageHeader title={title} />
      <Card className="p-10 text-center">
        <p className="mono text-[12px] font-mono text-accent">{mvp}</p>
        <p className="mx-auto mt-2 max-w-md text-[14px] text-muted">{text}</p>
      </Card>
    </>
  );
}
