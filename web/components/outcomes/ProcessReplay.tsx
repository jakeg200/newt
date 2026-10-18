"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type ProcessReplay as Replay, type ProcessResult } from "@/lib/api";

const VERDICT: Record<ProcessResult["verdict"], [string, string]> = {
  like_team: ["Ran it like your team", "bg-emerald-100 text-emerald-800"],
  handed_back: ["Handed it back", "bg-stone-200 text-stone-700"],
  diverged: ["Went differently", "bg-amber-100 text-amber-900"],
};
const WHO: Record<string, string> = { newt: "bg-brand-500", team: "bg-stone-400", world: "bg-sky-500" };
const dayLabel = (d: number) => (d < 0.04 ? "on arrival" : d < 1 ? `after ${Math.max(1, Math.round(d * 24))}h` : `day ${Math.round(d * 10) / 10}`);

function Timeline({ r }: { r: ProcessResult }) {
  return (
    <ol className="relative space-y-2.5 border-l-2 border-stone-200 pl-5">
      {r.timeline.map((e, i) => (
        <li key={i} className="relative">
          <span className={`absolute -left-[1.6rem] top-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-white ${WHO[e.who]}`} aria-hidden />
          <p className="text-sm">
            <span className="mr-1.5 text-xs tabular-nums text-stone-400">{dayLabel(e.day)}</span>
            {e.who === "world" ? e.what.charAt(0).toUpperCase() + e.what.slice(1)
              : <><b className="font-medium">{e.who === "newt" ? "Newt" : "Your team"}</b> {e.what}</>}
            {e.off_script && <span className="ml-1.5 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">not what the team did</span>}
          </p>
          {e.steps && e.steps.length > 0 && <p className="text-xs text-stone-500">checked first: {[...new Set(e.steps.filter((s) => s !== "propose"))].map((s) => s.replace(/_/g, " ")).join(", ")}</p>}
        </li>
      ))}
    </ol>
  );
}

/** Whole past cases replayed end to end with Newt in the team's place: replies, waiting, chasing, closing. */
export function ProcessReplay({ taskTypeId, canRun }: { taskTypeId: string; canRun: boolean }) {
  const [run, setRun] = useState<Replay | null | undefined>(undefined);
  const [i, setI] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api.processReplay(taskTypeId).then(setRun).catch(() => setRun(null)), [taskTypeId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!run || (run.status !== "queued" && run.status !== "running")) return;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [run, load]);

  async function start() {
    setError(null);
    try {
      setRun(await api.startProcessReplay(taskTypeId));
      setI(0);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (run === undefined) return null;
  const busy = run && (run.status === "queued" || run.status === "running");
  const s = run?.summary;
  const results = (run?.results ?? []).slice().sort((a, b) => b.timeline.length - a.timeline.length);
  const r = results[i];
  const carried = s ? s.cases - s.handed_back : 0;
  return (
    <section className="space-y-4 rounded-3xl border border-stone-200 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-stone-500">Whole cases, start to finish</p>
          <h3 className="text-xl font-extrabold">Replayed with Newt in your team&apos;s place</h3>
        </div>
        {canRun && <button type="button" onClick={start} disabled={!!busy}
                           className="rounded-full bg-ink px-3.5 py-1.5 text-sm font-medium text-white disabled:opacity-40">
          {busy ? `Replaying… ${run?.progress.done ?? 0}/${run?.progress.total ?? "?"}` : run ? "Replay again" : "Replay past cases"}
        </button>}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {!run && <p className="text-sm text-stone-600">Newt reruns real past cases from arrival to close, replies, waiting and chasing included, days of work in seconds, and compares what it did with what your team did. Nothing it does here reaches anyone.</p>}
      {run?.status === "failed" && <p className="text-sm text-red-700">The replay stopped: {run.error}</p>}
      {s && (
        <>
          <p className="text-[15px]">
            {s.cases} past cases, {run?.simulated_days} days of work replayed in {run?.duration_s}s. Of the {carried} it would have carried,
            it ran <b>{s.like_team}</b> just as your team did{s.handed_back ? <>, and handed <b>{s.handed_back}</b> back</> : null}
            {s.median_hours_sooner !== null && s.median_hours_sooner > 0 && <>, acting a median <b>{s.median_hours_sooner}h</b> sooner</>}.
          </p>
          {Object.keys(s.divergences).length > 0 && (
            <ul className="flex flex-wrap gap-1.5 text-xs">
              {Object.entries(s.divergences).map(([k, n]) => <li key={k} className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-900 ring-1 ring-amber-200">{k} · {n}</li>)}
            </ul>
          )}
          {run?.threshold?.source === "none yet" && (
            <p className="text-xs text-stone-500">Newt isn&apos;t certified yet, so this replay let every answer through rather than handing unsure ones back.</p>
          )}
          {r && (
            <div className="space-y-3 rounded-2xl bg-stone-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="min-w-0 truncate font-semibold">{r.subject || "A past case"}</p>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${VERDICT[r.verdict][1]}`}>{VERDICT[r.verdict][0]}</span>
              </div>
              <Timeline r={r} />
              {r.reasons.length > 0 && r.verdict !== "like_team" && <p className="text-xs text-stone-600">{r.reasons.join("; ")}</p>}
              {results.length > 1 && (
                <div className="flex items-center gap-2 text-sm">
                  <button type="button" onClick={() => setI((i - 1 + results.length) % results.length)} className="rounded-full bg-white px-3 py-1 ring-1 ring-stone-200" aria-label="Previous case">‹</button>
                  <span className="text-xs text-stone-500">{i + 1} of {results.length}</span>
                  <button type="button" onClick={() => setI((i + 1) % results.length)} className="rounded-full bg-white px-3 py-1 ring-1 ring-stone-200" aria-label="Next case">›</button>
                </div>
              )}
            </div>
          )}
          {!run?.results && <p className="text-xs text-stone-500">The cases themselves are visible to the mentor.</p>}
        </>
      )}
    </section>
  );
}
