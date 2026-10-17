"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type BoardRow, type Evaluation, type Role, type TrackRecord } from "@/lib/api";

const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);
const label = (s: string | null | undefined) => (s ? s.replace(/_/g, " ") : "–");

function Examples({ title, items }: { title: string; items?: Evaluation["agreements"] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">{title}</h4>
      <ul className="space-y-0.5 text-sm">
        {items.map((e) => (
          <li key={e.case_id} className="flex flex-wrap gap-x-2">
            <span className="min-w-0 flex-1 truncate">{e.subject || e.case_id}</span>
            <span className="text-stone-600">intern {label(e.agent)} · you {label(e.mentor)}</span>
            <span className="tabular-nums text-stone-500">{e.confidence.toFixed(2)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Proposal({ row, role, agentId, onChanged }: { row: BoardRow; role: Role | undefined; agentId: string | null; onChanged: () => void }) {
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [record, setRecord] = useState<TrackRecord | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [swap, setSwap] = useState({ model: "", version: "" });

  useEffect(() => {
    setEv(null);
    setRecord(null);
    setMessage(null);
    setError(null);
    api.evaluation(row.id).then(setEv).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.trackRecord(row.id).then(setRecord).catch(() => {});
  }, [row.id, row.status]);

  async function run(what: string, fn: () => Promise<string>) {
    setBusy(what);
    setError(null);
    setMessage(null);
    try {
      setMessage(await fn());
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const canSignSupervised = (role === "mentor" || role === "admin") && (row.status === "shadow" || row.status === "demoted");
  const canSignAutonomy = role === "manager" && row.status === "supervised";
  const button = "rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-40";

  return (
    <div className="space-y-5">
      {error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {message && <p className="rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900">{message}</p>}

      {!ev ? (
        <p className="text-sm text-stone-500">Working out the evidence…</p>
      ) : (
        <>
          <section className="space-y-3">
            <p className="text-sm text-stone-700">
              {ev.tau === null ? (
                <>
                  The claim to prove: on some confident share of cases, the intern disagrees with you less than{" "}
                  <span className="font-medium">{pct(ev.alpha, 0)}</span> of the time, with 95% confidence. No confidence threshold
                  gets there yet; the closest is below.
                </>
              ) : (
                <>
                  The claim: on cases like these, among those it handles (confidence at least{" "}
                  <span className="font-medium tabular-nums">{ev.tau.toFixed(2)}</span>), the intern disagrees with you less than{" "}
                  <span className="font-medium">{pct(ev.alpha, 0)}</span> of the time, with 95% confidence.
                </>
              )}
            </p>
            <ul className="space-y-1.5">
              {ev.checks.map((c) => (
                <li key={c.name} className="flex items-start gap-2 text-sm">
                  <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] text-white ${c.ok ? "bg-emerald-600" : "bg-stone-400"}`}>
                    {c.ok ? "✓" : "–"}
                  </span>
                  <span>{c.detail}</span>
                </li>
              ))}
            </ul>
            {!ev.eligible && ev.more_clean_cases_needed > 0 && (
              <p className="text-sm text-stone-600">
                With {ev.errors_above} disagreement{ev.errors_above === 1 ? "" : "s"} among confident cases, it needs{" "}
                {ev.cases_needed} cases above the threshold: about {ev.more_clean_cases_needed} more with no disagreements.
              </p>
            )}
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div><dt className="text-xs text-stone-500">Error upper bound</dt><dd className="font-semibold tabular-nums">{pct(ev.ucb, 2)}</dd></div>
              <div><dt className="text-xs text-stone-500">Coverage</dt><dd className="font-semibold tabular-nums">{pct(ev.coverage, 0)}</dd></div>
              <div><dt className="text-xs text-stone-500">Cases (backtest / live)</dt><dd className="font-semibold tabular-nums">{ev.backtest_cases} / {ev.live_cases}</dd></div>
              <div><dt className="text-xs text-stone-500">Agreement overall</dt><dd className="font-semibold tabular-nums">{pct(ev.agreement_rate)}</dd></div>
            </dl>
          </section>

          {(ev.agreements || ev.disagreements || ev.hand_backs) && (
            <section className="grid gap-4 md:grid-cols-3">
              <Examples title="Agreed, confident" items={ev.agreements} />
              <Examples title="Disagreed, confident" items={ev.disagreements} />
              <Examples title="Would hand back" items={ev.hand_backs} />
            </section>
          )}

          {Object.keys(ev.criteria).length > 0 && (
            <section className="space-y-1">
              <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">What drives your decisions, as the model sees it</h4>
              <ul className="text-sm text-stone-700">
                {Object.entries(ev.criteria).map(([d, terms]) => (
                  <li key={d}><span className="font-medium">{label(d)}</span>: {terms.join(", ")}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="flex flex-wrap gap-2 border-t border-stone-100 pt-4">
            {canSignSupervised && (
              <button type="button" disabled={!ev.eligible || !!busy} className={`${button} bg-teal-700 text-white`}
                      onClick={() => run("sign", async () => { await api.graduate(row.id, "supervised"); return "Signed. The intern now drafts and you approve."; })}>
                Sign: start supervised practice
              </button>
            )}
            {canSignAutonomy && (
              <button type="button" disabled={!ev.eligible || row.supervised_cases < row.supervised_needed || !!busy} className={`${button} bg-emerald-700 text-white`}
                      onClick={() => run("sign", async () => { await api.graduate(row.id, "autonomous"); return "Signed. The intern now acts alone above the threshold."; })}>
                Sign: allow autonomy
              </button>
            )}
            {row.status === "supervised" && (
              <span className="self-center text-sm text-stone-600">
                {row.supervised_cases} of {row.supervised_needed} supervised cases
                {role !== "manager" && " · the manager signs autonomy"}
              </span>
            )}
            {(row.status === "shadow" || row.status === "demoted") && role === "manager" && (
              <span className="self-center text-sm text-stone-600">The mentor signs the move to supervised practice.</span>
            )}
            <button type="button" disabled={!!busy} className={`${button} border border-stone-300 bg-white`}
                    onClick={() => run("drift", async () => {
                      const r = await api.driftCheck(row.id);
                      return r.drifted ? `Drift found: ${Math.round(r.result.recent_unfamiliar * 100)}% of recent items are unfamiliar. Back to shadow.`
                        : `No drift: ${Math.round((r.result.recent_unfamiliar ?? 0) * 100)}% of ${r.result.recent_cases} recent items unfamiliar.`;
                    })}>
              Check for drift
            </button>
            {record && (
              <button type="button" className={`${button} border border-stone-300 bg-white`}
                      onClick={async () => {
                        const blob = await api.trackRecordPdf(row.id);
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `track-record-${row.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pdf`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}>
                Track record (PDF)
              </button>
            )}
          </section>

          {(role === "manager" || role === "admin") && agentId && (
            <form className="flex flex-wrap items-end gap-2 text-sm"
                  onSubmit={(e) => {
                    e.preventDefault();
                    run("swap", async () => {
                      const r = await api.swapModel(agentId, swap.model, swap.version);
                      return r.reprobation_runs.length
                        ? `Swapped to ${r.model} ${r.version}. Re-probation on the frozen record is running; the result appears in the history.`
                        : `Swapped to ${r.model} ${r.version}. Nothing graduated, so nothing to re-certify.`;
                    });
                  }}>
              <label className="space-y-0.5">
                <span className="block text-xs text-stone-500">Swap the model</span>
                <input required value={swap.model} onChange={(e) => setSwap({ ...swap, model: e.target.value })} placeholder="model"
                       className="rounded-md border border-stone-300 px-2 py-1" />
              </label>
              <input required value={swap.version} onChange={(e) => setSwap({ ...swap, version: e.target.value })} placeholder="version"
                     className="w-24 rounded-md border border-stone-300 px-2 py-1" />
              <button type="submit" disabled={!!busy} className={`${button} border border-stone-300 bg-white`}>Swap and re-certify</button>
            </form>
          )}

          {record && record.history.length > 0 && (
            <section className="space-y-1">
              <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">History</h4>
              <ul className="space-y-0.5 text-sm">
                {[...record.history].reverse().map((h, i) => (
                  <li key={i}>
                    <span className="tabular-nums text-stone-500">{h.date}</span> {label(h.from)} → <span className="font-medium">{label(h.to)}</span>{" "}
                    <span className="text-stone-500">({h.by})</span>{h.note && <span className="text-stone-600"> · {h.note}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
