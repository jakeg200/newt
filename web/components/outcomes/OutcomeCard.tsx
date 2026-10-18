"use client";

import { useState } from "react";
import { InternAvatar, type Growth } from "@/components/InternAvatar";
import type { Career, Kpi, Outcomes } from "@/lib/api";

const fmt = (metric: string, v: number | null | undefined) =>
  v === null || v === undefined ? "–" : metric === "share_by_newt" ? `${Math.round(v * 100)}%`
    : metric === "median_hours_to_complete" ? `${v}h` : metric === "value" ? Math.round(v).toLocaleString() : String(v);

const RANK_GROWTH: Record<string, Growth> = { new_starter: "egg", intern: "larva", junior: "eft", graduate: "adult", senior: "adult", owner: "adult" };
const TO_RANK: Record<string, string> = { supervised: "Junior", autonomous: "Graduate", senior: "Senior", owner: "Owner", shadow: "Intern",
                                          demoted: "Back to practice", initiative: "Initiative" };

/** The headline KPI over the weeks, with the goal line and each promotion marked, like a performance chart. */
function Chart({ kpi, weeks, promotions }: { kpi: Kpi; weeks: Outcomes["weeks"]; promotions: Outcomes["promotions"] }) {
  const values = (kpi.series ?? []).map((v) => v ?? 0);
  const W = 560, H = 150, P = 8;
  const max = Math.max(1, ...values, kpi.target ?? 0) * 1.15;
  const x = (i: number) => P + (i * (W - 2 * P)) / Math.max(1, values.length - 1);
  const y = (v: number) => H - P - (v / max) * (H - 2 * P);
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(values.length - 1)},${H - P} L${x(0)},${H - P} Z`;
  const t0 = new Date(weeks[0]?.start ?? 0).getTime(), t1 = new Date(weeks[weeks.length - 1]?.end ?? 0).getTime();
  const marks = promotions.map((p) => ({ ...p, t: new Date(p.at).getTime() })).filter((p) => p.t >= t0 && p.t <= t1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img" aria-label={`${kpi.label} over the last ${values.length} weeks`}>
      <defs>
        <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="var(--color-brand-500)" stopOpacity="0.3" />
          <stop offset="1" stopColor="var(--color-brand-500)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {kpi.target !== null && (
        <g>
          <line x1={P} x2={W - P} y1={y(kpi.target)} y2={y(kpi.target)} stroke="var(--color-stone-400)" strokeDasharray="4 5" />
          <text x={P + 2} y={y(kpi.target) - 5} fontSize="11" fill="var(--color-stone-500)">Goal {fmt(kpi.metric, kpi.target)}</text>
        </g>
      )}
      {marks.map((m) => {
        const mx = P + ((m.t - t0) / Math.max(1, t1 - t0)) * (W - 2 * P);
        return (
          <g key={m.at}>
            <line x1={mx} x2={mx} y1={P} y2={H - P} stroke="var(--color-ink)" strokeOpacity="0.25" />
            <text x={mx > W * 0.8 ? mx - 4 : mx + 4} y={P + 10} fontSize="11" fill="var(--color-ink)" textAnchor={mx > W * 0.8 ? "end" : "start"}>
              {TO_RANK[m.to] ?? m.to}
            </text>
          </g>
        );
      })}
      <path d={area} fill="url(#fill)" />
      <path d={line} fill="none" stroke="var(--color-brand-600)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {values.length > 0 && <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="4.5" fill="var(--color-brand-600)" stroke="white" strokeWidth="2" />}
    </svg>
  );
}

export function OutcomeCard({ o, intern }: { o: Outcomes; intern: string }) {
  const charted = o.kpis.filter((k) => k.series);
  const [pick, setPick] = useState(charted[0]?.metric);
  const kpi = charted.find((k) => k.metric === pick) ?? charted[0];
  if (!kpi) return null;
  const up = kpi.trend !== null && kpi.trend !== 0 ? (kpi.trend > 0) === (kpi.direction === "up") : null;
  return (
    <section className="space-y-4 rounded-3xl border border-stone-200 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-stone-500">Outcome · this week</p>
          <p className="font-[family-name:var(--font-display)] text-5xl font-extrabold tabular-nums">{fmt(kpi.metric, kpi.this_week)}</p>
          <p className="mt-0.5 text-sm">
            <span className="font-medium">{kpi.label}</span>
            {kpi.trend !== null && (
              <span className={`ml-2 font-medium ${up ? "text-emerald-700" : up === false ? "text-amber-700" : "text-stone-500"}`}>
                {kpi.trend > 0 ? "▲" : kpi.trend < 0 ? "▼" : "•"} {fmt(kpi.metric, Math.abs(kpi.trend))} vs last week
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {charted.map((k) => (
            <button key={k.metric} type="button" onClick={() => setPick(k.metric)}
                    className={`rounded-full px-2.5 py-1 text-xs ${k.metric === kpi.metric ? "bg-ink text-white" : "bg-stone-100 text-stone-600"}`}>
              {k.label}
            </button>
          ))}
        </div>
      </div>
      <Chart kpi={kpi} weeks={o.weeks} promotions={o.promotions} />
      <div className="grid grid-cols-3 gap-2 text-center">
        {[[String(o.since_start.completed_by_newt), `finished by ${intern} so far`], [String(o.backlog_open), "waiting right now"],
          [o.kpis.filter((k) => k.on_track).length + "/" + o.kpis.filter((k) => k.target !== null).length, "goals on track"]].map(([v, l]) => (
          <div key={l} className="rounded-2xl bg-stone-50 py-2.5">
            <p className="font-[family-name:var(--font-display)] text-xl font-extrabold">{v}</p>
            <p className="text-[11px] text-stone-500">{l}</p>
          </div>
        ))}
      </div>
      {o.simulated && (
        <p className="rounded-2xl bg-amber-50 px-3.5 py-2 text-xs text-amber-900 ring-1 ring-amber-200">
          No system is connected yet, so {intern}&apos;s work is simulated. Connect one in Setup to see real results.
        </p>
      )}
    </section>
  );
}

/** Newt's career so far: each rung, earned with evidence and a signature. */
export function CareerLadder({ career, promotions }: { career: Career; promotions: Outcomes["promotions"] }) {
  const at = career.ladder.findIndex((r) => r.rank === career.rank);
  const when = (rank: string) => {
    const to = { junior: "supervised", graduate: "autonomous", senior: "senior", owner: "owner" }[rank];
    const p = [...promotions].reverse().find((e) => e.to === to);
    return p ? new Date(p.at).toLocaleDateString([], { day: "numeric", month: "short" }) : null;
  };
  return (
    <section className="rounded-3xl border border-stone-200 bg-white p-5 sm:p-6">
      <p className="mb-4 text-sm font-medium text-stone-500">Career</p>
      <ol className="grid grid-cols-6 gap-1">
        {career.ladder.map((r, i) => (
          <li key={r.rank} className="flex flex-col items-center gap-1.5 text-center" aria-current={i === at ? "step" : undefined}>
            <InternAvatar growth={RANK_GROWTH[r.rank]} size={i === at ? 52 : 38} decorative animated={i === at}
                          className={i > at ? "opacity-25 grayscale" : ""} />
            <span className={`h-1.5 w-full rounded-full ${i <= at ? "bg-brand-500" : "bg-stone-200"}`} />
            <span className={`text-xs ${i === at ? "font-semibold" : "text-stone-500"}`}>{r.title}</span>
            {i <= at && when(r.rank) && <span className="text-[10px] text-stone-400">{when(r.rank)}</span>}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-stone-500">
        {at < career.ladder.length - 1 ? `Next: ${career.ladder[at + 1].title}, earned on evidence and signed off by a person.` : "Top of the ladder, still spot-checked every week."}
      </p>
    </section>
  );
}
