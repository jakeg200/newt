"use client";

import { useEffect, useState } from "react";
import { RepredictBanner } from "@/components/RepredictBanner";
import { api, ApiError, type Blast, type Improvement } from "@/lib/api";

const label = (s: string | null) => (s ? s.replace(/_/g, " ") : "nothing");

/** What a change did to past cases: fixed, broke, and a few of each to look at. */
export function BlastView({ b, compact }: { b: Blast; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const unit = b.unit === "processes" ? "past case, start to finish," : "past case";
  const shown = (["broke", "fixed", "moved"] as const).filter((k) => b.examples?.[k]?.length);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold">
        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-800">fixes {b.fixed}</span>
        <span className={`rounded-full px-2.5 py-0.5 ${b.broke ? "bg-amber-100 text-amber-900" : "bg-stone-100 text-stone-600"}`}>breaks {b.broke}</span>
        {b.moved > 0 && <span className="rounded-full bg-stone-100 px-2.5 py-0.5 text-stone-600">changes {b.moved} other{b.moved === 1 ? "" : "s"}</span>}
        <span className="font-normal text-stone-500">on {b.cases} {unit.replace("case", b.cases === 1 ? "case" : "cases")}</span>
      </div>
      {!compact && b.agreement_before !== null && b.agreement_after !== null && b.unit !== "processes" && (
        <p className="text-xs text-stone-500">
          In line with your team on these cases: {Math.round(b.agreement_before * 100)}% → <b className="text-ink">{Math.round(b.agreement_after * 100)}%</b>.
          The certified error bound is re-checked on the frozen record once it goes live.
        </p>
      )}
      {shown.length > 0 && (
        <button type="button" onClick={() => setOpen(!open)} className="text-xs font-medium text-stone-600 underline">
          {open ? "Hide the cases" : "See the cases"}
        </button>
      )}
      {open && (
        <ul className="space-y-1 text-xs">
          {shown.flatMap((k) => b.examples[k].map((e) => (
            <li key={`${k}-${e.case_id}`} className="flex gap-2">
              <span className={`shrink-0 font-semibold ${k === "broke" ? "text-amber-800" : k === "fixed" ? "text-emerald-800" : "text-stone-500"}`}>{k}</span>
              <span className="min-w-0 truncate">{e.subject || "a case"}: {label(e.before)} → <b>{label(e.after)}</b>
                {b.unit !== "processes" && e.team && <span className="text-stone-400"> (team: {label(e.team)})</span>}</span>
            </li>
          )))}
        </ul>
      )}
    </div>
  );
}

/** Follows a change while it's tested on past cases, then shows its blast radius and, if it waits, the mentor's call. */
export function ChangeTest({ id, onDone, embedded }: { id: string; onDone?: () => void; embedded?: boolean }) {
  const [imp, setImp] = useState<Improvement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await api.improvement(id);
        if (stop) return;
        setImp(r);
        if (r.status === "testing") timer = setTimeout(poll, 1000);
        else onDone?.();
      } catch {
        if (!stop) timer = setTimeout(poll, 2000);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function decide(keep: boolean) {
    setBusy(true);
    setError(null);
    try {
      setImp(keep ? await api.promoteImprovement(id, true) : await api.rejectImprovement(id));
      onDone?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!imp || imp.status === "testing") {
    return (
      <p className="flex items-center gap-2 rounded-2xl bg-sky-50 px-4 py-2.5 text-sm text-sky-900 ring-1 ring-sky-200" aria-live="polite">
        <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" /> Testing the change on past cases before Newt uses it…
      </p>
    );
  }
  if (imp.status === "failed") return <p className="rounded-2xl bg-red-50 px-4 py-2.5 text-sm text-red-800 ring-1 ring-red-200">The test didn&apos;t run: {imp.error}</p>;
  const b = imp.blast as Blast;
  return (
    <div className={`space-y-2.5 rounded-2xl px-4 py-3 text-sm ring-1 ${imp.status === "ready" ? "bg-amber-50 ring-amber-200" : "bg-white ring-stone-200"}`}>
      <p className="font-medium">
        {imp.status === "promoted" ? "Tested, and live." : imp.status === "rejected" ? "Dropped." : "Tested. It changes some of your team's past decisions:"}
        {!embedded && <span className="ml-1 font-normal text-stone-600">{imp.summary}</span>}
      </p>
      {b.cases !== undefined && <BlastView b={b} />}
      {imp.status === "ready" && (
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy} onClick={() => decide(true)} className="rounded-full bg-ink px-3.5 py-1.5 text-sm font-medium text-white disabled:opacity-40">Use it anyway</button>
          <button type="button" disabled={busy} onClick={() => decide(false)} className="rounded-full bg-white px-3.5 py-1.5 text-sm font-medium ring-1 ring-stone-300 disabled:opacity-40">Drop it</button>
        </div>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
      {imp.repredict_run_id && <RepredictBanner runId={imp.repredict_run_id} onDone={onDone} />}
    </div>
  );
}
