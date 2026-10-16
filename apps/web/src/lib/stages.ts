import type { OffReason, Stage } from "./types";

/** Порядок воронки (розділ 5 ТЗ) без returned/off */
export const FLOW: Stage[] = [
  "purchased", "in_adspower", "bm_created", "phone_linked", "warmup", "card_linked", "checking", "ready", "issued",
];

export const STAGE_LABEL: Record<Stage, string> = {
  purchased: "Куплено", in_adspower: "AdsPower", bm_created: "БМ", phone_linked: "Номер",
  warmup: "Прогрів", card_linked: "Карта", checking: "Перевірка 24г", ready: "Готовий",
  issued: "Видано", sold: "Продано", returned: "Повернено", off: "Off",
};

/** Короткі підписи для воронки на дашборді */
export const STAGE_SHORT: Record<Stage, string> = {
  purchased: "Куплено", in_adspower: "AdsPower", bm_created: "БМ", phone_linked: "Номер",
  warmup: "Прогрів", card_linked: "Карта", checking: "Перевірка", ready: "Готові",
  issued: "Видано", sold: "Продано", returned: "Повернено", off: "Off",
};

export const OFF_LABEL: Record<OffReason, string> = {
  ban: "Бан", reserve: "Резерв", paused: "Пауза", returned: "Повернено", written_off: "Списано",
};

export type StageTone = "issued" | "ready" | "check" | "work" | "off" | "sold";
export function stageTone(s: Stage): StageTone {
  if (s === "issued") return "issued";
  if (s === "ready") return "ready";
  if (s === "checking") return "check";
  if (s === "off") return "off";
  if (s === "sold") return "sold";
  return "work";
}

export const TONE_STYLE: Record<StageTone, { bg: string; fg: string }> = {
  issued: { bg: "var(--stage-issued-bg)", fg: "var(--stage-issued-fg)" },
  ready: { bg: "var(--stage-ready-bg)", fg: "var(--stage-ready-fg)" },
  check: { bg: "var(--stage-check-bg)", fg: "var(--stage-check-fg)" },
  work: { bg: "var(--stage-work-bg)", fg: "var(--stage-work-fg)" },
  off: { bg: "var(--stage-off-bg)", fg: "var(--stage-off-fg)" },
  sold: { bg: "rgba(167,139,250,.14)", fg: "#c4b5fd" },
};

/** Етапи, на які можна перейти кнопкою «вперед» (наступний по ланцюгу) */
export function forwardStage(s: Stage): Stage | null {
  const i = FLOW.indexOf(s);
  return i >= 0 && i < FLOW.length - 1 ? FLOW[i + 1] : null;
}
