"use client";

import { useEffect, useState } from "react";
import { api, type SampleWork } from "@/lib/api";

const TOOL: Record<string, [string, string]> = {
  search_past_cases: ["🔎", "Searched past cases"], get_case: ["📄", "Read an earlier case"], lookup_record: ["🗂️", "Looked up the record"],
  check_rule: ["📏", "Checked the rules"], calculate: ["🧮", "Did the maths"], propose: ["✅", "Decided"],
};

function summary(step: SampleWork["steps"][number]): string {
  const o = step.output as Record<string, unknown>;
  const i = step.input as Record<string, unknown>;
  switch (step.tool) {
    case "search_past_cases": {
      const cases = (o.cases as { decision: string }[] | undefined) ?? [];
      const counts = cases.reduce<Record<string, number>>((acc, c) => ({ ...acc, [c.decision]: (acc[c.decision] ?? 0) + 1 }), {});
      return cases.length ? `${cases.length} similar: ${Object.entries(counts).map(([d, n]) => `${n} ${d.replace(/_/g, " ")}`).join(", ")}` : "nothing similar";
    }
    case "lookup_record":
      return o.found ? `${i.kind} ${i.ref}: ${Object.entries((o.record as Record<string, unknown>) ?? {}).filter(([k]) => !["kind", "ref"].includes(k)).slice(0, 3).map(([k, v]) => `${k} ${v}`).join(", ")}`
        : `${i.kind} ${i.ref}: ${o.source === "unavailable" ? "not available (past case)" : "not found"}`;
    case "check_rule": {
      const rules = (o.rules as unknown[] | undefined) ?? [];
      const hard = (o.always_hand_back as unknown[] | undefined) ?? [];
      return hard.length ? `always hand back: ${hard.join(", ")}` : rules.length ? `${rules.length} rule${rules.length > 1 ? "s" : ""} apply` : "no rule applies";
    }
    case "propose":
      return String(i.decision ?? "").replace(/_/g, " ");
    default:
      return o.error ? String(o.error) : JSON.stringify(o).slice(0, 80);
  }
}

/** One real case Newt worked, step by step: the difference between an answer and doing the job. */
export function ShowsItsWork({ taskTypeId, intern }: { taskTypeId: string; intern: string }) {
  const [w, setW] = useState<SampleWork | null | undefined>(undefined);
  useEffect(() => {
    api.sampleWork(taskTypeId).then(setW).catch(() => setW(null));
  }, [taskTypeId]);
  if (!w) return null;
  const verdict = w.agreement ? ["Right, with the evidence the role requires", "bg-emerald-100 text-emerald-800"]
    : w.decision_match ? [`Right answer, but skipped ${(w.checks.missing ?? []).join(", ").replace(/_/g, " ") || "a required step"}: doesn't count`, "bg-amber-100 text-amber-900"]
      : ["Different from the team's decision: a lesson", "bg-stone-200 text-stone-700"];
  return (
    <section className="space-y-3 rounded-3xl border border-stone-200 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-stone-500">{intern} shows its work · {w.live ? "live case" : "replayed past case"}</p>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${verdict[1]}`}>{verdict[0]}</span>
      </div>
      <p className="font-semibold">{w.subject}</p>
      <ol className="relative space-y-3 border-l-2 border-brand-200 pl-5">
        {w.steps.map((s) => (
          <li key={s.n} className="relative">
            <span className="absolute -left-[1.85rem] flex h-6 w-6 items-center justify-center rounded-full bg-white text-sm ring-2 ring-brand-200" aria-hidden>
              {(TOOL[s.tool] ?? ["•"])[0]}
            </span>
            <p className="text-sm font-medium">{(TOOL[s.tool] ?? [s.tool, s.tool])[1]}</p>
            <p className="text-sm text-stone-600">{summary(s)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
