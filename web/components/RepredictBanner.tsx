"use client";

import { useEffect, useState } from "react";
import { api, type RepredictRun } from "@/lib/api";

const label = (s: string | null) => (s ? s.replace(/_/g, " ") : "no prediction");

/** Follows a backlog re-prediction until it finishes, then says what moved. */
export function RepredictBanner({ runId, onDone }: { runId: string; onDone?: () => void }) {
  const [run, setRun] = useState<RepredictRun | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await api.run(runId);
        if (stop) return;
        setRun(r);
        if (r.status === "queued" || r.status === "running") timer = setTimeout(poll, 1000);
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
  }, [runId]);

  if (!run || run.status === "queued" || run.status === "running") {
    return <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">Re-predicting your backlog with the new rules…</p>;
  }
  if (run.status === "failed") {
    return <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">Re-prediction failed: {run.error}</p>;
  }
  const changed = run.stats.changed ?? 0;
  const compared = run.stats.compared_with_previous ?? 0;
  return (
    <div className="rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-900">
      <p>
        <span className="font-medium">
          This changed {changed} prediction{changed === 1 ? "" : "s"} in your backlog
        </span>{" "}
        <span className="text-brand-800">({compared} cases re-predicted)</span>
        {changed > 0 && (
          <button type="button" onClick={() => setOpen(!open)} className="ml-2 underline">
            {open ? "Hide" : "Show"}
          </button>
        )}
      </p>
      {open && (
        <ul className="mt-2 space-y-0.5 text-xs">
          {(run.stats.changes ?? []).map((c) => (
            <li key={c.case_id}>
              {c.subject || c.case_id}: {label(c.before)} → <span className="font-medium">{label(c.after)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
