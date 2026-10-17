"use client";

import { useEffect, useState } from "react";
import { api, type BacktestCase, type BacktestRun, type BacktestStats } from "@/lib/api";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(1)}%`);
const label = (s: string) => s.replace(/_/g, " ");

function Metric({ name, value, note }: { name: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-xs text-stone-500">{name}</dt>
      <dd className="text-xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-stone-500">{note}</dd>}
    </div>
  );
}

function Confusion({ stats }: { stats: BacktestStats }) {
  const decisions = stats.decisions;
  const max = Math.max(1, ...decisions.flatMap((m) => decisions.map((a) => stats.confusion[m]?.[a] ?? 0)));
  return (
    <table className="text-sm">
      <caption className="mb-1 text-left text-xs text-stone-500">Rows: what the mentor did. Columns: what the agent predicted.</caption>
      <thead>
        <tr>
          <th />
          {decisions.map((d) => (
            <th key={d} className="px-2 pb-1 text-left text-xs font-medium text-stone-600">{label(d)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {decisions.map((m) => (
          <tr key={m}>
            <th className="pr-3 text-left text-xs font-medium text-stone-600">{label(m)}</th>
            {decisions.map((a) => {
              const n = stats.confusion[m]?.[a] ?? 0;
              const diag = m === a;
              const alpha = n ? 0.12 + 0.6 * (n / max) : 0;
              return (
                <td
                  key={a}
                  className="h-10 w-20 border border-white text-center tabular-nums"
                  style={{ background: n ? (diag ? `rgba(15,118,110,${alpha})` : `rgba(185,28,28,${alpha})`) : "#f5f5f4" }}
                >
                  {n || ""}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RunResults({ run, canSeeCases }: { run: BacktestRun; canSeeCases: boolean }) {
  const [only, setOnly] = useState<"disagreements" | "handed_back">("disagreements");
  const [cases, setCases] = useState<BacktestCase[] | null>(null);
  const stats = run.stats as BacktestStats;
  const done = run.status === "done";

  useEffect(() => {
    if (!done || !canSeeCases) return;
    setCases(null);
    api.backtestCases(run.id, only).then((r) => setCases(r.items)).catch(() => setCases([]));
  }, [run.id, only, done, canSeeCases]);

  if (run.status === "failed") {
    return <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{run.error}</p>;
  }
  if (!done) {
    const { done: n = 0, total = 0 } = run.progress;
    return (
      <div className="space-y-2 text-sm">
        <p>{run.status === "queued" ? "Waiting to start…" : `Predicting case ${n} of ${total}…`}</p>
        <div className="h-2 overflow-hidden rounded-full bg-stone-200">
          <div className="h-full bg-brand-600 transition-all" style={{ width: total ? `${(100 * n) / total}%` : "4%" }} />
        </div>
        {run.cost_usd > 0 && <p className="text-xs text-stone-500">${run.cost_usd.toFixed(2)} so far</p>}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric name="Agreement with the mentor" value={pct(stats.agreement_rate)} note={`${stats.agreement} of ${stats.predicted} predicted`} />
        <Metric name="Decision matched" value={pct(stats.decision_accuracy)} />
        <Metric name="Handed back" value={String(stats.handed_back)} note="no prediction" />
        <Metric name="Cost" value={`$${stats.cost_usd.toFixed(2)}`} note={`${Math.round(stats.duration_s)} s · ${stats.cases} cases`} />
      </dl>
      <p className="text-xs text-stone-500">
        {run.agent_name} · {run.model}
        {run.params.samples > 1 && ` · ${run.params.samples} samples per case`} · handbook{" "}
        {run.handbook_version ? `v${run.handbook_version}` : "none approved"}
        {stats.text_outputs_pending > 0 && ` · text replies on ${stats.text_outputs_pending} cases are judged in the next milestone`}
      </p>
      {stats.no_handbook && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          No approved handbook yet, so the agent learned from past cases only. Approve one in Orientation and run again.
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Where it agrees and doesn&apos;t</h3>
          <Confusion stats={stats} />
        </section>
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Agreement by confidence</h3>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-stone-500">
              <tr>
                <th className="pb-1 font-medium">Confidence</th>
                <th className="pb-1 font-medium">Cases</th>
                <th className="pb-1 font-medium">Agreement</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {stats.confidence_buckets.map((b) => (
                <tr key={b.from} className="border-t border-stone-100">
                  <td className="py-1">{b.from.toFixed(1)}–{b.to.toFixed(1)}</td>
                  <td className="py-1">{b.cases}</td>
                  <td className="py-1">{pct(b.agreement)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-stone-500">
            If agreement rises with confidence, a threshold can hand back the uncertain cases. Graduation sets it (M5).
          </p>
          {Object.keys(stats.fields).length > 0 && (
            <p className="text-xs text-stone-600">
              Fields:{" "}
              {Object.entries(stats.fields).map(([k, f], i) => (
                <span key={k}>
                  {i > 0 && " · "}
                  {label(k)} {pct(f.accuracy)} <span className="text-stone-400">({f.cases})</span>
                </span>
              ))}
            </p>
          )}
        </section>
      </div>

      {canSeeCases && (
        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium">Cases to look at</h3>
            {(["disagreements", "handed_back"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setOnly(k)}
                className={`rounded-full px-2.5 py-0.5 text-xs ${only === k ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-700"}`}
              >
                {k === "disagreements" ? "Disagreements" : "Handed back"}
              </button>
            ))}
          </div>
          {cases === null ? (
            <p className="text-sm text-stone-500">Loading…</p>
          ) : cases.length === 0 ? (
            <p className="text-sm text-stone-500">None.</p>
          ) : (
            <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white">
              {cases.map((c) => (
                <li key={c.case_id} className="space-y-1 px-3 py-2 text-sm">
                  <p className="font-medium">{c.subject || c.case_id}</p>
                  {c.error ? (
                    <p className="text-red-700">{c.error}</p>
                  ) : (
                    <>
                      <p>
                        Mentor: <span className="font-medium">{label(c.mentor.decision ?? "–")}</span> · Agent:{" "}
                        <span className="font-medium">{label(c.agent?.decision ?? "–")}</span>
                        {c.confidence !== null && <span className="text-stone-500"> at {pct(c.confidence)}</span>}
                      </p>
                      {Object.entries(c.field_scores).filter(([, s]) => !s.match).map(([k, s]) => (
                        <p key={k} className="text-xs text-stone-600">
                          {label(k)}: mentor {String(s.mentor)}, agent {String(s.agent ?? "–")}
                        </p>
                      ))}
                      {c.agent?.rationale && <p className="text-xs text-stone-500">{c.agent.rationale}</p>}
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
