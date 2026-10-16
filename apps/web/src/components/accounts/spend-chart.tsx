"use client";
import { useState } from "react";
import useSWR from "swr";
import { Chip, Empty } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { SpendPoint } from "@/lib/types";
import { money } from "@/lib/utils";

export function SpendChart({ accountId, hasAdId }: { accountId: string; hasAdId: boolean }) {
  const [days, setDays] = useState(7);
  const { data } = useSWR<SpendPoint[]>(hasAdId ? `/api/accounts/${accountId}/spend?days=${days}` : null, fetcher, { refreshInterval: 60000 });
  const [hover, setHover] = useState<number | null>(null);

  const head = (
    <div className="flex gap-2 px-5 pt-4">
      <Chip active={days === 7} onClick={() => setDays(7)}>7 днів</Chip>
      <Chip active={days === 30} onClick={() => setDays(30)}>30 днів</Chip>
    </div>
  );
  if (!hasAdId) return <Empty>Вкажіть Ad account ID, щоб зіставити кабінет з даними Clover.</Empty>;
  if (!data || data.every((p) => p.spend === null)) return <>{head}<Empty>Даних Clover за цей період ще немає.</Empty></>;

  const vals = data.map((p) => (p.spend === null ? 0 : Number(p.spend)));
  const max = Math.max(...vals, 1);
  const total = vals.reduce((a, b) => a + b, 0);
  const W = 640, H = 160, gap = days === 7 ? 14 : 4, bw = (W - gap * (data.length - 1)) / data.length;

  return (
    <div>
      {head}
      <div className="px-5 pt-3 text-[12px] text-muted">
        Разом за період: <b className="font-mono text-main">{money(total)}</b>
        {hover !== null && <span className="ml-3 font-mono">{data[hover].date}: {data[hover].spend === null ? "немає даних" : money(data[hover].spend)}</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full px-3 pb-3" role="img" aria-label="Спенд по днях">
        {data.map((p, i) => {
          const h = p.spend === null ? 2 : Math.max(2, (Number(p.spend) / max) * H);
          const x = i * (bw + gap);
          const showLabel = days === 7 || i % 5 === 0 || i === data.length - 1;
          return (
            <g key={p.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={x} y={0} width={bw} height={H} fill="transparent" />
              <rect x={x} y={H - h} width={bw} height={h} rx={3}
                fill={p.spend === null ? "var(--border-strong)" : "var(--accent)"} opacity={hover === null || hover === i ? 1 : 0.45} />
              {showLabel && <text x={x + bw / 2} y={H + 16} textAnchor="middle" fontSize="10" fill="var(--text-faint)" fontFamily="var(--font-jetbrains)">{p.date.slice(8)}.{p.date.slice(5, 7)}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
