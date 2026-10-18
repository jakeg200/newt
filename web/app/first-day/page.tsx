"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { InternAvatar, type Mood } from "@/components/InternAvatar";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { Bubble } from "@/components/ui";
import { Destinations } from "@/components/work/Destinations";
import { Routines } from "@/components/work/Routines";
import { api, ApiError, type Kpi, type Question, type RolePackInfo, type TaskTypeInfo } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const STEPS = ["Role", "Meet", "Success", "Sign-off", "Know-how", "Routines", "Systems", "Start"] as const;
const LADDER = [
  ["Intern", "watches your work and writes down what it would do, sealed until you've decided"],
  ["Junior", "drafts the work; nothing happens until you approve each one"],
  ["Graduate", "handles routine cases alone, hands back anything unusual, and is spot-checked"],
  ["Senior", "earns extra responsibilities, like chasing replies itself"],
  ["Outcome owner", "owns a goal: finds what drives it, proposes fixes for you to agree, reports every week"],
];

/** The role library: roles a Newt can be hired for. Industry-specific roles come as packs, never code. */
function RoleLibrary({ taskTypes, manager, onHired }: { taskTypes: TaskTypeInfo[]; manager: boolean; onHired: () => void }) {
  const [packs, setPacks] = useState<RolePackInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.rolePacks().then(setPacks).catch(() => {});
  }, []);
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {packs.map((p) => {
          const hired = taskTypes.some((t) => t.name === p.task_type);
          return (
            <div key={p.id} className={`space-y-2 rounded-2xl p-4 ring-1 ${hired ? "bg-emerald-50/60 ring-emerald-200" : "bg-white ring-stone-200"}`}>
              <p className="font-semibold">{p.title}</p>
              <p className="text-sm text-stone-600">{p.tagline}</p>
              <p className="text-xs text-stone-500">Measured on: {p.kpis.slice(0, 3).join(", ")}</p>
              {hired ? <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">On your team</span>
                : manager ? (
                  <button type="button" disabled={busy === p.id} className="rounded-full bg-ink px-3.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                          onClick={async () => {
                            setBusy(p.id);
                            setError(null);
                            try {
                              await api.hire(p.id);
                              onHired();
                            } catch (e) {
                              setError(e instanceof ApiError ? e.message : String(e));
                              setBusy(null);
                            }
                          }}>
                    {busy === p.id ? "Hiring…" : "Hire a Newt for this"}
                  </button>
                ) : <span className="text-xs text-stone-400">A manager can hire this role</span>}
            </div>
          );
        })}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

export default function FirstDay() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error } = useTaskTypes();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [kpis, setKpis] = useState<Kpi[]>([]);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const manager = user?.role === "manager" || user?.role === "admin";
  const mentor = user?.role === "mentor" || user?.role === "admin";

  useEffect(() => {
    if (!taskType) return;
    setName(taskType.intern_name);
    api.outcomes(taskType.id).then((o) => {
      setKpis(o.kpis);
      setTargets(Object.fromEntries(o.kpis.map((k) => [k.metric, k.target === null ? "" : String(k.metric === "share_by_newt" ? k.target * 100 : k.target)])));
    }).catch(() => {});
    api.questionnaire(taskType.team).then((qs) => {
      const mine = qs.filter((q) => q.key.includes(".bank.") || ["always_escalate", "never_alone", "common_mistakes"].includes(q.key));
      setQuestions(mine);
      setAnswers(Object.fromEntries(mine.map((q) => [q.key, (q as Question & { answer?: string }).answer ?? ""])));
    }).catch(() => {});
  }, [taskType]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const intern = name || taskType.intern_name;
  const flash = (s: string) => { setSaved(s); setTimeout(() => setSaved(null), 1800); };
  const fail = (e: unknown) => flash(e instanceof ApiError ? e.message : String(e));

  async function next() {
    try {
      if (step === 1 && manager && name.trim() && name.trim() !== taskType!.intern_name) {
        await api.managerSettings(taskType!.team, { intern_name: name.trim() });
      }
      if (step === 2 && manager) {
        await api.setKpiTargets(taskType!.id, Object.fromEntries(kpis.map((k) => {
          const v = targets[k.metric];
          return [k.metric, v === "" || v === undefined ? null : k.metric === "share_by_newt" ? Number(v) / 100 : Number(v)];
        })));
      }
      if (step === 4 && mentor) {
        const filled = Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim()));
        if (Object.keys(filled).length) await api.saveAnswers(taskType!.team, filled);
      }
      setStep((s) => Math.min(STEPS.length - 1, s + 1));
    } catch (e) {
      fail(e);
    }
  }

  const say: { mood: Mood; text: React.ReactNode }[] = [
    { mood: "hello", text: <>Which role am I joining? Pick one from the library, or carry on with <b>{taskType.name.toLowerCase()}</b>.</> },
    { mood: "hello", text: <>Hi! I&apos;m joining the team to help with <b>{taskType.name.toLowerCase()}</b>. I start as an intern and earn every step from there. What should everyone call me?</> },
    { mood: "thinking", text: <>How will we know I&apos;m doing a good job? These are what I&apos;ll report on every week, and what my reviews will show.</> },
    { mood: "learning", text: <>Here&apos;s how I earn trust. Each step needs evidence and a signature from a person. Some things always come back to you, whatever my rank.</> },
    { mood: "learning", text: <>A few things only your team knows. A sentence each is plenty; I&apos;ll write them into my handbook notes.</> },
    { mood: "drafting", text: <>This is how I&apos;d handle each kind of case, based on what you do today. Agree or change it.</> },
    { mood: "working", text: <>Where should I do the work? I only use the access you give me, and every action is logged.</> },
    { mood: "graduated", text: <>That&apos;s my first day done. I&apos;ll start as an <b>intern</b>: watching, learning and asking only what&apos;s worth your time.</> },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 animate-rise">
        <div className="flex items-center gap-3">
          <InternAvatar mood="hello" growth={step === STEPS.length - 1 ? "larva" : "egg"} size={64} />
          <div>
            <p className="hand text-xl leading-none text-brand-700">First day</p>
            <h1 className="text-3xl">Onboarding {intern}</h1>
          </div>
        </div>
        <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={(id) => { setTaskTypeId(id); setStep(0); }} />
      </div>

      <div className="grid gap-6 md:grid-cols-[11rem_1fr]">
        <ol className="flex gap-1 overflow-x-auto md:flex-col" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button type="button" onClick={() => setStep(i)} aria-current={i === step ? "step" : undefined}
                      className={`flex w-full items-center gap-2 whitespace-nowrap rounded-full px-3 py-1.5 text-sm ${i === step ? "bg-ink text-white" : i < step ? "text-ink" : "text-stone-400"}`}>
                <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${i < step ? "bg-emerald-500 text-white" : i === step ? "bg-white text-ink" : "bg-stone-200"}`}>
                  {i < step ? "✓" : i + 1}
                </span>
                {s}
              </button>
            </li>
          ))}
        </ol>

        <div key={step} className="space-y-4 animate-rise">
          <Bubble name={intern} mood={say[step].mood} growth={step === STEPS.length - 1 ? "larva" : "egg"}>{say[step].text}</Bubble>

          <div className="rounded-3xl border border-stone-200 bg-white p-5">
            {step === 1 && (
              <div className="space-y-3">
                <label className="block space-y-1.5">
                  <span className="text-sm font-medium">Name</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} disabled={!manager} maxLength={30}
                         className="w-full max-w-xs rounded-full border border-stone-300 px-4 py-2 text-lg font-semibold disabled:bg-stone-50" />
                </label>
                <p className="text-sm text-stone-500">Role: <b>{taskType.name}</b> · Team: {taskType.team.replace(/_/g, " ")}{!manager && " · the manager picks the name"}</p>
              </div>
            )}
            {step === 2 && (
              <div className="grid gap-3 sm:grid-cols-2">
                {kpis.map((k) => (
                  <label key={k.metric} className="space-y-1.5 rounded-2xl bg-stone-50 p-3.5">
                    <span className="block text-sm font-medium">{k.label}</span>
                    <span className="flex items-center gap-2 text-sm text-stone-500">
                      Goal {k.direction === "down" ? "at most" : "at least"}
                      <input value={targets[k.metric] ?? ""} onChange={(e) => setTargets({ ...targets, [k.metric]: e.target.value })} disabled={!manager}
                             inputMode="decimal" placeholder="none" className="w-20 rounded-full border border-stone-300 bg-white px-3 py-1 disabled:bg-stone-50" />
                      {k.metric === "share_by_newt" ? "%" : k.metric === "median_hours_to_complete" ? "hours" : "a week"}
                    </span>
                  </label>
                ))}
                {!manager && <p className="text-sm text-stone-500 sm:col-span-2">The manager sets the goals.</p>}
              </div>
            )}
            {step === 3 && (
              <div className="space-y-4">
                <ol className="space-y-2">
                  {LADDER.map(([t, d], i) => (
                    <li key={t} className="flex gap-3">
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-800">{i + 1}</span>
                      <p><b>{t}</b>: {d}.</p>
                    </li>
                  ))}
                </ol>
                {taskType.hard_rules.length > 0 && (
                  <div>
                    <p className="text-sm font-medium">Always comes back to you</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {taskType.hard_rules.map((r) => <span key={r} className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-900 ring-1 ring-amber-200">{r}</span>)}
                    </div>
                  </div>
                )}
              </div>
            )}
            {step === 4 && (
              <div className="space-y-3">
                {questions.map((q) => (
                  <label key={q.key} className="block space-y-1.5">
                    <span className="text-sm font-medium">{q.question}</span>
                    <textarea value={answers[q.key] ?? ""} onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })} disabled={!mentor} rows={2}
                              className="w-full rounded-2xl border border-stone-300 px-3.5 py-2 text-sm disabled:bg-stone-50" />
                  </label>
                ))}
                {!mentor && <p className="text-sm text-stone-500">The mentor answers these.</p>}
              </div>
            )}
            {step === 0 && <RoleLibrary taskTypes={taskTypes} manager={manager} onHired={() => window.location.reload()} />}
            {step === 5 && <Routines taskType={taskType} allowed={taskType.allowed_actions} canEdit={mentor} intern={intern} />}
            {step === 6 && <Destinations taskType={taskType} allowed={taskType.allowed_actions} intern={intern} />}
            {step === 7 && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Link href="/orientation" className="rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-300 hover:bg-stone-100">Give it the team&apos;s documents</Link>
                  <Link href="/capture" className="rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-300 hover:bg-stone-100">Connect where the work arrives</Link>
                  <Link href="/" className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">Go to {intern} →</Link>
                </div>
                <p className="text-sm text-stone-500">It replays your past cases first, so you see how it would have done before it sees anything live.</p>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            {step > 0 && <button type="button" onClick={() => setStep(step - 1)} className="rounded-full px-4 py-2 text-sm text-stone-500 hover:text-ink">Back</button>}
            {step < STEPS.length - 1 && (
              <button type="button" onClick={next} className="rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700">Next</button>
            )}
            {saved && <span className="text-sm text-stone-500" role="status">{saved}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
