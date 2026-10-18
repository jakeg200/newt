"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { BlastView, ChangeTest } from "@/components/improve/ChangeTest";
import { PageHeader } from "@/components/ui";
import { api, ApiError, type Blast, type Improvement, type Judgement } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
const STATUS: Record<Improvement["status"], [string, string]> = {
  testing: ["Testing", "bg-sky-100 text-sky-800"], ready: ["Waiting for the mentor", "bg-amber-100 text-amber-900"],
  promoted: ["Live", "bg-emerald-100 text-emerald-800"], rejected: ["Dropped", "bg-stone-100 text-stone-600"], failed: ["Test failed", "bg-red-100 text-red-800"],
};

/** Every change to how Newt works, newest first, with what it did to past cases before it went live. */
function Changes({ changes, mentor, onChanged }: { changes: Improvement[]; mentor: boolean; onChanged: () => void }) {
  if (changes.length === 0) return null;
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-2xl font-extrabold">Every change, tested first</h2>
        <p className="text-sm text-stone-600">Before a rule or routine changes how Newt works, it&apos;s replayed on past cases. A change that breaks nothing goes live; one that would change the team&apos;s past decisions waits for the mentor.</p>
      </div>
      <ul className="space-y-2">
        {changes.map((c) => (
          <li key={c.id} className="space-y-2 rounded-2xl border border-stone-200 bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="min-w-0 font-medium">{c.summary}</p>
              <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS[c.status][1]}`}>{STATUS[c.status][0]}</span>
            </div>
            {c.status === "ready" && mentor ? <ChangeTest id={c.id} onDone={onChanged} embedded />
              : (c.blast as Blast).cases !== undefined && <BlastView b={c.blast as Blast} compact />}
            <p className="text-xs text-stone-400">{new Date(c.created_at).toLocaleDateString([], { day: "numeric", month: "short" })} · {c.source === "newt" ? "Newt's idea" : c.signal === "exception" ? "a confirmed exception" : "taught by the mentor"}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function JudgementPage() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error: ttError } = useTaskTypes();
  const [j, setJ] = useState<Judgement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const mentor = user?.role === "mentor" || user?.role === "admin";

  const load = useCallback(async (id: string) => setJ(await api.judgement(id)), []);
  useEffect(() => {
    if (taskTypeId) load(taskTypeId).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [taskTypeId, load]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{ttError ?? "Loading…"}</p>;
  const intern = taskType.intern_name;

  const confirm = async (text: string) => {
    setBusy(text);
    try {
      const r = await api.createRule(taskType.id, text);
      if (r.improvement) setTesting(r.improvement.id);
      await load(taskType.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const download = async (kind: "md" | "pdf") => {
    const blob = await api.judgementFile(taskType.id, kind);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `judgement-${taskType.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.${kind}`;
    a.click();
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title={<>What only <span className="hl">your team</span> knew</>}
        intro={`How the team really decides, written down by ${intern} from behaviour, with the evidence behind every line. It stays when people move on.`}
        mood="learning"
        aside={<TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />}
      />
      {error && <p className="rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-800 ring-1 ring-red-200">{error}</p>}
      {!j ? <p className="text-sm text-stone-500">Reading the team&apos;s decisions…</p> : (
        <>
          <div className="stagger grid gap-3 sm:grid-cols-4">
            {[[String(j.decisions), "decisions learned from"], [String(j.unwritten.length), "unwritten rules captured"],
              [pct(j.explicit_share), "of decisions now explained by a rule"], [String(j.written.length), "items in the written handbook"]].map(([v, l]) => (
              <div key={l} className="rounded-3xl border border-stone-200 bg-white p-5">
                <p className="font-[family-name:var(--font-display)] text-4xl font-extrabold">{v}</p>
                <p className="text-sm text-stone-500">{l}</p>
              </div>
            ))}
          </div>

          {j.exceptions.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-2xl font-extrabold">Rules nobody wrote down</h2>
              <p className="text-sm text-stone-500">Patterns in where {intern} got it wrong. Confirm the ones that are really how you work.</p>
              <div className="grid gap-3 md:grid-cols-2">
                {j.exceptions.map((e) => (
                  <div key={e.key} className="space-y-2 rounded-3xl bg-brand-50/70 p-5 ring-1 ring-brand-200">
                    <p className="font-semibold">&ldquo;{e.text}&rdquo;</p>
                    <p className="text-sm text-stone-600">
                      {intern} got {e.misses} of these wrong · applies to {e.coverage} past cases · the team does this {pct(e.agreement)} of the time
                    </p>
                    {e.examples.length > 0 && <p className="text-xs text-stone-500">e.g. {e.examples.slice(0, 2).join(" · ")}</p>}
                    {mentor && (
                      <button type="button" disabled={busy === e.text} onClick={() => confirm(e.text)}
                              className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50">
                        {busy === e.text ? "Adding…" : "Yes, that's our rule"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {testing && <ChangeTest key={testing} id={testing} onDone={() => load(taskType.id).catch(() => {})} />}
          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <section className="space-y-3">
              <h2 className="text-2xl font-extrabold">Learned from behaviour</h2>
              {j.unwritten.length === 0 && <p className="text-sm text-stone-500">Nothing yet. Every correction and confirmed pattern lands here.</p>}
              <ul className="space-y-2">
                {j.unwritten.map((u) => (
                  <li key={u.id} className="rounded-2xl border border-stone-200 bg-white p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="font-medium">{u.text}</p>
                      {u.status === "testing" ? (
                        <span className="shrink-0 rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-semibold text-sky-800">Not live yet</span>
                      ) : u.status === "proposed" ? (
                        <span className="shrink-0 rounded-full bg-stone-100 px-2.5 py-0.5 text-xs font-semibold text-stone-600">Suggested</span>
                      ) : (
                        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${u.passes ? "bg-emerald-100 text-emerald-800" : "bg-stone-100 text-stone-600"}`}>
                          {u.passes ? "Proven" : "Not yet proven"}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-stone-500">
                      {u.learned}{u.taught_by ? ` by ${u.taught_by}` : ""} · governs {u.coverage} past decisions · team agrees {pct(u.agreement)} · v{u.version}
                    </p>
                  </li>
                ))}
              </ul>
              {j.notes.length > 0 && (
                <>
                  <h3 className="pt-2 font-[family-name:var(--font-display)] text-lg font-extrabold">In the mentor&apos;s words</h3>
                  <ul className="space-y-2">
                    {j.notes.slice().reverse().map((n, i) => (
                      <li key={i} className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
                        <p className="hand text-xl leading-snug">&ldquo;{n.note}&rdquo;</p>
                        <p className="mt-1 text-xs text-stone-500">on {n.case}</p>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
            <section className="space-y-3">
              <h2 className="text-2xl font-extrabold">Written down</h2>
              {j.written.length === 0 ? (
                <p className="text-sm text-stone-500">No approved handbook yet. <Link href="/orientation" className="underline">Add the team&apos;s documents</Link>.</p>
              ) : (
                <ul className="space-y-2">
                  {j.written.map((w, i) => (
                    <li key={i} className="rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-200">
                      <p className="text-xs font-medium uppercase tracking-wide text-stone-400">{w.kind}</p>
                      <p>{w.text}</p>
                      {w.sources.length > 0 && <p className="mt-1 text-xs text-stone-500">Source: {w.sources.join(", ")}</p>}
                    </li>
                  ))}
                </ul>
              )}
              {j.conflicts.length > 0 && (
                <div className="space-y-2 rounded-2xl bg-amber-50 p-4 ring-1 ring-amber-200">
                  <p className="font-semibold text-amber-900">Rules that disagree</p>
                  {j.conflicts.map((c, i) => <p key={i} className="text-sm text-amber-900">{c.rules.join(" vs ")} ({c.cases} cases)</p>)}
                  <Link href="/learned" className="text-sm font-medium underline">Resolve in the rules list</Link>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-2">
                <button type="button" onClick={() => download("pdf")} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">Download the playbook (PDF)</button>
                <button type="button" onClick={() => download("md")} className="rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-300">Markdown</button>
              </div>
            </section>
          </div>
          <Changes changes={j.changes ?? []} mentor={mentor} onChanged={() => load(taskType.id).catch(() => {})} />
        </>
      )}
    </div>
  );
}
