"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { InternAvatar, type Growth } from "@/components/InternAvatar";
import { PageHeader } from "@/components/ui";
import { api, ApiError, type Insights, type TeamNewt, type TeamView } from "@/lib/api";
import { useUser } from "@/lib/user";

const pct = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);
const GROWTH: Record<string, Growth> = { new_starter: "egg", intern: "larva", junior: "eft", graduate: "adult", senior: "adult", owner: "adult" };

function NewtCard({ n }: { n: TeamNewt }) {
  const [alpha, setAlpha] = useState(n.capacity.alpha);
  const [ins, setIns] = useState<Insights | null>(null);
  useEffect(() => {
    api.insights(n.id).then(setIns).catch(() => {});
  }, [n.id]);
  const plan = n.capacity.what_if.find((w) => w.alpha === alpha) ?? n.capacity.current;
  const waiting = n.needs_people.drafts + n.needs_people.handbacks + n.needs_people.audits;
  return (
    <article className="space-y-4 rounded-3xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3">
        <InternAvatar growth={GROWTH[n.rank]} mood={waiting ? "thinking" : "working"} size={60} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="font-[family-name:var(--font-display)] text-xl font-extrabold">{n.intern_name}</span>
            <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-800">{n.title}</span>
          </p>
          <p className="truncate text-sm text-stone-500">{n.name}</p>
        </div>
        {waiting > 0 && <Link href="/inbox" className="rounded-full bg-ink px-3 py-1.5 text-xs font-semibold text-white">{waiting} need you</Link>}
      </div>
      {n.evidence.n_above === 0 ? (
        <p className="rounded-2xl bg-stone-50 px-3.5 py-2 text-sm text-stone-600">
          No evidence yet. {n.intern_name} is learning from your team&apos;s past decisions and earns trust case by case.
        </p>
      ) : <p className="rounded-2xl bg-stone-50 px-3.5 py-2 text-sm">
        Certified on <b>{n.evidence.n_above}</b> cases · wrong at most <b>{pct(n.evidence.ucb, 1)}</b> (limit {pct(n.evidence.alpha)}) · {n.evidence.ucb <= n.evidence.alpha ? "carries" : "would carry"} <b>{pct(n.evidence.coverage)}</b> of the work
        {n.evidence.ucb > n.evidence.alpha && <span className="text-stone-500">, once it&apos;s under the limit</span>}
      </p>}

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-medium">Capacity at a {pct(alpha)} risk limit</p>
          <div className="flex gap-1" role="radiogroup" aria-label="Risk limit">
            {n.capacity.what_if.map((w) => (
              <button key={w.alpha} type="button" role="radio" aria-checked={w.alpha === alpha} onClick={() => setAlpha(w.alpha)}
                      className={`rounded-full px-2 py-0.5 text-xs ${w.alpha === alpha ? "bg-ink text-white" : "bg-stone-100 text-stone-600"}`}>
                {pct(w.alpha)}
              </button>
            ))}
          </div>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-stone-200" role="img" aria-label={`${pct(plan.share)} of the work`}>
          <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${Math.round(plan.share * 100)}%` }} />
        </div>
        <p className="text-xs text-stone-500">
          {plan.cases_per_week} of {n.capacity.volume_per_week} cases a week{plan.hours_per_week !== null && ` · ${plan.hours_per_week} h freed`}
          {!plan.certified && " · not certifiable at this limit yet"}
          {alpha !== n.capacity.alpha && " · what-if only; the real limit doesn't change here"}
        </p>
      </div>

      {n.human_work.length > 0 && (
        <div>
          <p className="text-sm font-medium">Still comes to people</p>
          <ul className="mt-1 space-y-0.5 text-sm text-stone-600">{n.human_work.slice(0, 3).map((h) => <li key={h.reason}>• {h.reason} <span className="text-stone-400">({h.cases})</span></li>)}</ul>
        </div>
      )}

      {ins && ins.drivers.length > 0 && (
        <div>
          <p className="text-sm font-medium">What drives the exceptions</p>
          <ul className="mt-1 space-y-1 text-sm">
            {ins.drivers.slice(0, 3).map((d) => (
              <li key={d.key} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                <span className="min-w-0 flex-1 truncate"><b>{d.value}</b>: {pct(d.rate)} end in {d.top_exception.replace(/_/g, " ")}</span>
                <span className="shrink-0 text-xs text-stone-400">{d.lift}× usual</span>
              </li>
            ))}
          </ul>
          {ins.rank !== "owner" && <p className="mt-1 text-xs text-stone-500">Once {n.intern_name} owns an outcome, it proposes fixes for these.</p>}
        </div>
      )}
      {ins && ins.initiatives.filter((i) => i.status === "running").map((i) => (
        <div key={i.id} className="rounded-2xl bg-emerald-50 px-3.5 py-2.5 text-sm ring-1 ring-emerald-200">
          <p className="font-semibold text-emerald-900">{i.title}</p>
          <p className="text-emerald-900/80">
            Exception rate {pct(i.baseline_rate)} before{i.since?.rate !== null && i.since ? ` → ${pct(i.since.rate)} since (${i.since.cases} cases)` : ", measuring since it started"}
          </p>
        </div>
      ))}
    </article>
  );
}

export default function TeamPage() {
  const { user } = useUser();
  const [team, setTeam] = useState<TeamView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (user) api.team().then(setTeam).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [user]);
  if (!user) return null;
  const role = team?.role;
  const reasons = (team?.newts ?? []).flatMap((n) => n.human_work).sort((a, b) => b.cases - a.cases).slice(0, 4);

  return (
    <div className="space-y-8">
      <PageHeader title={<>Your team of <span className="hl">Newts</span></>} mood="working"
                  intro="Every Newt, what it carries on evidence, and what still needs people. One expert, supervising several Newts." />
      {error && <p className="text-sm text-red-700">{error}</p>}
      {!team ? <p className="text-sm text-stone-500">Loading the team…</p> : (
        <>
          <section className="grid gap-4 rounded-[2rem] bg-ink p-6 text-white md:grid-cols-[1.2fr_1fr]">
            <div className="space-y-2">
              <p className="hand text-2xl leading-none text-brand-300">Your role, with Newt</p>
              <p className="font-[family-name:var(--font-display)] text-3xl font-extrabold leading-tight">
                You supervise {role!.newts} {role!.newts === 1 ? "Newt" : "Newts"}, carrying {pct(role!.share)} of the work.
              </p>
              <p className="text-white/70">
                {role!.carried_per_week} of {role!.volume_per_week} cases a week{role!.hours_per_week ? `, about ${role!.hours_per_week} hours freed` : ""}. You keep the judgement calls.
              </p>
            </div>
            <div className="space-y-2 rounded-2xl bg-white/10 p-4">
              <p className="text-sm font-medium text-white/80">What you focus on now</p>
              {reasons.length ? (
                <ul className="space-y-1 text-sm">{reasons.map((r) => <li key={r.reason}>• {r.reason} <span className="text-white/50">({r.cases})</span></li>)}</ul>
              ) : <p className="text-sm text-white/60">Exceptions and hand-backs will show here.</p>}
            </div>
          </section>
          <div className="stagger grid gap-4 lg:grid-cols-2">{team.newts.map((n) => <NewtCard key={n.id} n={n} />)}</div>
          <p className="text-sm text-stone-500">Need another role covered? <Link href="/first-day" className="underline">Hire a Newt from the role library</Link>.</p>
        </>
      )}
    </div>
  );
}
