"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Routine, type TaskTypeInfo } from "@/lib/api";

const STEP: Record<string, string> = {
  set_status: "Update the status", set_field: "Fill in the fields", draft_reply: "Draft the reply", send_reply: "Send the reply", route: "Route it to you",
};
const label = (s: string) => s.replace(/_/g, " ");

/** How Newt handles each decision: proposed by Newt from what the team does, agreed by the mentor. */
export function Routines({ taskType, allowed, canEdit, intern }: { taskType: TaskTypeInfo; allowed: string[]; canEdit: boolean; intern: string }) {
  const [routines, setRoutines] = useState<Record<string, Routine> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.routines(taskType.id).then(setRoutines).catch(() => {});
  }, [taskType.id]);

  if (!routines) return null;
  const save = async (decision: string, r: Routine) => {
    setError(null);
    try {
      const saved = await api.setRoutine(taskType.id, decision, r.steps, r.follow_up_days);
      setRoutines({ ...routines, [decision]: saved });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-3">
      {Object.entries(routines).map(([decision, r]) => (
        <div key={decision} className={`rounded-2xl p-4 ring-1 ${r.status === "approved" ? "bg-white ring-stone-200" : "bg-brand-50/60 ring-brand-200"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold">When it&apos;s <span className="hl">{label(decision)}</span></p>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${r.status === "approved" ? "bg-emerald-100 text-emerald-800" : "bg-brand-100 text-brand-800"}`}>
              {r.status === "approved" ? "Agreed" : `${intern} suggests`}
            </span>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {allowed.map((a) => {
              const on = r.steps.includes(a);
              return (
                <button key={a} type="button" disabled={!canEdit} aria-pressed={on}
                        onClick={() => setRoutines({ ...routines, [decision]: { ...r, steps: on ? r.steps.filter((s) => s !== a) : [...r.steps, a] } })}
                        className={`rounded-full px-3 py-1 text-sm transition-colors ${on ? "bg-ink text-white" : "bg-white text-stone-500 ring-1 ring-stone-200"} disabled:cursor-default`}>
                  {on ? "✓ " : ""}{STEP[a] ?? label(a)}
                </button>
              );
            })}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-sm text-stone-600">
            <span>Follow up if nothing happens after</span>
            <select disabled={!canEdit} value={r.follow_up_days ?? ""} aria-label={`Follow-up for ${label(decision)}`}
                    onChange={(e) => setRoutines({ ...routines, [decision]: { ...r, follow_up_days: e.target.value ? Number(e.target.value) : null } })}
                    className="rounded-full border border-stone-300 bg-white px-2.5 py-1">
              <option value="">never</option>
              {[1, 2, 3, 5, 7, 14].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}
            </select>
            {canEdit && (
              <button type="button" onClick={() => save(decision, r)}
                      className="ml-auto rounded-full bg-brand-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand-700">
                {r.status === "approved" ? "Save" : "Agree"}
              </button>
            )}
          </div>
          {r.status !== "approved" && typeof r.reply_share === "number" && r.reply_share > 0 && (
            <p className="mt-2 text-xs text-stone-500">You replied on {Math.round(r.reply_share * 100)}% of these, so I&apos;d draft a reply too.</p>
          )}
        </div>
      ))}
      {error && <p className="text-sm text-red-700">{error}</p>}
      <p className="text-xs text-stone-500">
        As a junior, {intern} only does these after you approve each case. As a graduate, it does them on its own. Chasing on its own is a senior responsibility.
      </p>
    </div>
  );
}
