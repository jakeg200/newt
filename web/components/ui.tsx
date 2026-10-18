import type { ReactNode } from "react";
import { GROWTH, InternAvatar, type Growth, type Mood } from "@/components/InternAvatar";

/** Big display title, a short intro, and optionally the intern in the mood of this page. */
export function PageHeader({ title, intro, mood, aside }: { title: ReactNode; intro?: ReactNode; mood?: Mood; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 animate-rise">
      <div className="flex items-center gap-4">
        {mood && <InternAvatar mood={mood} size={72} className="hidden shrink-0 sm:block" />}
        <div className="space-y-1.5">
          <h1 className="text-3xl sm:text-4xl">{title}</h1>
          {intro && <p className="max-w-2xl text-stone-600">{intro}</p>}
        </div>
      </div>
      {aside}
    </div>
  );
}

const PATH: { stage: string; label: string }[] = [
  { stage: "orientation", label: "Orientation" },
  { stage: "shadow", label: "Shadowing" },
  { stage: "supervised", label: "Supervised" },
  { stage: "autonomous", label: "Graduated" },
];

/** The intern's growth path: egg, larva, eft, adult, with the current stage lit. */
export function Journey({ status }: { status: string }) {
  const at = PATH.findIndex((p) => p.stage === (status === "demoted" ? "shadow" : status));
  return (
    <ol className="flex gap-1 text-xs" aria-label="Onboarding stages">
      {PATH.map((p, i) => (
        <li key={p.stage} className="flex flex-1 flex-col gap-1.5" aria-current={i === at ? "step" : undefined}>
          <InternAvatar growth={GROWTH[i]} size={44} decorative animated={i === at} className={i > at ? "opacity-25 grayscale" : ""} />
          <span className={`h-2 rounded-full ${i <= at ? "bg-brand-500" : "bg-stone-200"}`} />
          <span className={i === at ? "font-semibold" : "text-stone-500"}>{p.label}</span>
        </li>
      ))}
    </ol>
  );
}

export const stageLabel = (status: string) =>
  status === "demoted" ? "Back to practice" : (PATH.find((p) => p.stage === status)?.label ?? status);

/** Filter pills, Revnu-style: one active, each with a count. */
export function Pills<T extends string>({ value, options, onChange }: {
  value: T; options: { key: T; label: string; count?: number }[]; onChange: (k: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist">
      {options.map((o) => (
        <button key={o.key} type="button" role="tab" aria-selected={o.key === value} onClick={() => onChange(o.key)}
                className={`rounded-full px-3 py-1 text-sm transition-colors ${o.key === value ? "bg-ink text-white" : "bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-100"}`}>
          {o.label}{o.count !== undefined && <span className={`ml-1.5 tabular-nums ${o.key === value ? "text-white/70" : "text-stone-400"}`}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** A message from the intern, styled like a chat notification. */
export function Bubble({ name, mood = "neutral", growth, time, children }: {
  name: string; mood?: Mood; growth?: Growth; time?: string; children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-white p-3.5 shadow-[0_6px_24px_-14px_rgb(27_23_20/0.3)]">
      <InternAvatar mood={mood} growth={growth} size={48} decorative className="shrink-0" animated={false} />
      <div className="min-w-0 text-sm">
        <p className="flex items-baseline gap-2">
          <span className="font-semibold">{name}</span>
          {time && <span className="text-xs text-stone-400">{time}</span>}
        </p>
        <div className="text-stone-700">{children}</div>
      </div>
    </div>
  );
}
