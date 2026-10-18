"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GROWTH, InternAvatar, STAGE_GROWTH, STAGE_MOOD } from "@/components/InternAvatar";
import { Bubble } from "@/components/ui";
import { api, ApiError, type BoardRow, type Stage, type TaskTypeInfo } from "@/lib/api";
import { useUser } from "@/lib/user";

const PATH: { stage: Stage | "orientation"; label: string }[] = [
  { stage: "orientation", label: "Orientation" },
  { stage: "shadow", label: "Shadowing" },
  { stage: "supervised", label: "Supervised" },
  { stage: "autonomous", label: "Graduated" },
];

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 1000) / 10}%`);

/** What the intern says about itself, and the one next step, by stage and role. */
function status(row: BoardRow, role: string | undefined): { say: string; cta: string; href: string } {
  const manager = role === "manager";
  const ev = row.evaluation;
  if ((row.status === "shadow" || row.status === "demoted") && ev.eligible)
    return {
      say: `${ev.errors_above} errors in ${ev.n_above} confident cases. My error bound is ${pct(ev.ucb)}, under your ${pct(ev.alpha)} bar. I think I'm ready for supervised practice.`,
      cta: manager ? "See the evidence" : "Sign my graduation", href: "/board",
    };
  if (row.status === "shadow" || row.status === "demoted")
    return {
      say: `I'm shadowing: ${ev.n_above} confident cases so far, ${ev.more_clean_cases_needed ?? "a few"} more clean ones to go.`,
      cta: manager ? "See the evidence" : "Teach me today's cases", href: manager ? "/board" : "/today",
    };
  if (row.status === "supervised")
    return {
      say: `I'm drafting, you approve. ${row.supervised_cases} of ${row.supervised_needed} supervised cases done.`,
      cta: row.supervised_cases >= row.supervised_needed && manager ? "Sign my autonomy" : "Review my drafts",
      href: row.supervised_cases >= row.supervised_needed && manager ? "/board" : "/autonomy",
    };
  return {
    say: `I'm working on my own. ${row.audits.passed} blind audits passed${row.audits.failed ? `, ${row.audits.failed} failed` : ""}. Anything unusual comes back to you.`,
    cta: manager ? "See hours returned" : "Check my hand-backs", href: manager ? "/manager" : "/autonomy",
  };
}

export default function Home() {
  const { user } = useUser();
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [types, setTypes] = useState<TaskTypeInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api.board().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.taskTypes().then(setTypes).catch(() => {});
  }, [user]);

  const intern = types[0]?.intern_name ?? "Newt";
  const nameOf = (id: string) => types.find((t) => t.id === id)?.intern_name ?? intern;

  return (
    <div className="space-y-12">
      <section className="grid items-center gap-8 pt-6 md:grid-cols-[1.4fr_1fr]">
        <div className="stagger space-y-5">
          <p className="hand text-2xl text-brand-700">Hi{user ? ` ${user.name.split(" ")[0]}` : ""}, meet your new hire</p>
          <h1 className="text-5xl leading-[1.02] sm:text-6xl">
            This is <span className="hl">{intern}</span>.<br />It learns the job <span className="text-brand-600">like a new hire.</span>
          </h1>
          <p className="max-w-xl text-lg text-stone-600">
            {intern} reads your handbook, shadows your team, practises under supervision, and only works alone once the
            evidence says it can be trusted.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href={rows?.[0] ? status(rows[0], user?.role).href : "/orientation"}
                  className="lift rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-white">
              {rows?.[0] ? status(rows[0], user?.role).cta : "Start orientation"} →
            </Link>
            <Link href="/board" className="lift rounded-full border border-stone-300 bg-white px-5 py-2.5 text-sm font-semibold">
              Task board
            </Link>
          </div>
        </div>
        <div className="flex justify-center md:justify-end">
          <InternAvatar mood="hello" size={260} />
        </div>
      </section>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {!rows && !error && <p className="text-sm text-stone-500">Loading…</p>}
      {rows?.length === 0 && (
        <Bubble name={intern} mood="hello">
          Nothing to do yet. Give me your team&apos;s documents in <Link href="/orientation" className="font-medium underline">orientation</Link> and I&apos;ll get reading.
        </Bubble>
      )}

      {rows && rows.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-2xl font-extrabold">Where {intern} is up to</h2>
          <ul className="stagger grid gap-4 md:grid-cols-2">
            {rows.map((row) => {
              const at = PATH.findIndex((p) => p.stage === (row.status === "demoted" ? "shadow" : row.status));
              const s = status(row, user?.role);
              return (
                <li key={row.id} className="lift space-y-4 rounded-3xl border border-stone-200 bg-white p-5">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-[family-name:var(--font-display)] text-lg font-extrabold">{row.name}</h3>
                    <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-800">
                      {row.status === "demoted" ? "Back to practice" : PATH[at]?.label}
                    </span>
                  </div>
                  <ol className="flex gap-1 text-xs" aria-label="Onboarding stages">
                    {PATH.map((p, i) => (
                      <li key={p.stage} className="flex flex-1 flex-col gap-1.5">
                        <InternAvatar growth={GROWTH[i]} size={44} decorative animated={i === at}
                                      className={i > at ? "opacity-25 grayscale" : ""} />
                        <span className={`h-2 rounded-full ${i <= at ? "bg-brand-500" : "bg-stone-200"}`} />
                        <span className={i === at ? "font-semibold" : "text-stone-500"}>{p.label}</span>
                      </li>
                    ))}
                  </ol>
                  <Bubble name={nameOf(row.id)} mood={STAGE_MOOD[row.status]} growth={STAGE_GROWTH[row.status]}>{s.say}</Bubble>
                  <Link href={s.href} className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">
                    {s.cta} →
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
