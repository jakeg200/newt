"use client";

import { useCallback, useEffect, useState } from "react";
import { Proposal } from "@/components/board/Proposal";
import { api, ApiError, type AgentInfo, type BoardRow, type Stage } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

const STAGE_STYLE: Record<Stage, string> = {
  shadow: "bg-stone-200 text-stone-800",
  supervised: "bg-sky-100 text-sky-900",
  autonomous: "bg-emerald-100 text-emerald-900",
  demoted: "bg-red-100 text-red-800",
};

const pct = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);

function Bar({ value, max, ok }: { value: number; max: number; ok: boolean }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-stone-200">
      <div className={`h-full ${ok ? "bg-emerald-600" : "bg-brand-600"}`} style={{ width: `${Math.min(100, (100 * value) / Math.max(1, max))}%` }} />
    </div>
  );
}

export default function BoardPage() {
  const { user } = useUser();
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [b, a] = await Promise.all([api.board(), api.agents()]);
    setRows(b);
    setAgents(a);
    setSelected((s) => s ?? b[0]?.id ?? null);
  }, []);

  useEffect(() => {
    if (!user) return;
    load().catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [user, load]);

  if (!user || !rows) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const row = rows.find((r) => r.id === selected);
  const builtIn = agents.find((a) => a.kind === "built_in");

  return (
    <div className="stagger space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-4"><InternAvatar mood="graduated" growth="adult" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">Task board</h1></div>
        <p className="max-w-2xl text-sm text-stone-600">
          Each task type earns its own autonomy. It moves on when the evidence clears the bar and the right person signs,
          and back when audits, drift or a model change say so.
        </p>
      </div>

      <div className="overflow-x-auto rounded-3xl border border-stone-200 bg-white">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="border-b border-stone-200 text-xs text-stone-500">
            <tr>
              <th className="px-4 py-2 font-medium">Task type</th>
              <th className="px-4 py-2 font-medium">Stage</th>
              <th className="px-4 py-2 font-medium">To the next stage</th>
              <th className="px-4 py-2 font-medium">Error bound</th>
              <th className="px-4 py-2 font-medium">Coverage</th>
              <th className="px-4 py-2 font-medium">Audits</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map((r) => {
              const e = r.evaluation;
              const supervised = r.status === "supervised";
              return (
                <tr key={r.id} onClick={() => setSelected(r.id)}
                    className={`cursor-pointer ${r.id === selected ? "bg-stone-50" : "hover:bg-stone-50"}`}>
                  <td className="px-4 py-3 font-medium">{r.name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_STYLE[r.status]}`}>{r.status}</span>
                  </td>
                  <td className="w-64 px-4 py-3">
                    {r.status === "autonomous" ? (
                      <span className="text-xs text-stone-600">Acting alone above τ {r.tau?.toFixed(2)}</span>
                    ) : supervised ? (
                      <div className="space-y-1">
                        <Bar value={r.supervised_cases} max={r.supervised_needed} ok={r.supervised_cases >= r.supervised_needed} />
                        <span className="text-xs text-stone-600">
                          {r.supervised_cases} of {r.supervised_needed} supervised cases · {pct(r.untouched.rate)} approved untouched
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <Bar value={e.n_above - e.errors_above} max={Math.max(e.cases_needed, e.min_cases)} ok={e.eligible} />
                        <span className="text-xs text-stone-600">
                          {e.eligible ? "Ready to sign" : `${e.n_above} confident cases, ${e.live_above} live · needs ${Math.max(e.cases_needed, e.min_cases)} and 50 live`}
                        </span>
                      </div>
                    )}
                  </td>
                  <td className={`px-4 py-3 tabular-nums ${e.ucb <= e.alpha ? "text-emerald-700" : ""}`}>
                    {pct(e.ucb, 1)} <span className="text-xs text-stone-500">/ {pct(e.alpha)}</span>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{pct(e.coverage)}</td>
                  <td className="px-4 py-3 text-xs text-stone-600">
                    {r.audits.passed + r.audits.failed > 0 ? `${r.audits.passed} passed, ${r.audits.failed} failed` : "–"}
                    {r.audits.pending > 0 && ` · ${r.audits.pending} waiting`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {row && (
        <section className="space-y-3 rounded-3xl border border-stone-200 bg-white p-5">
          <h2 className="font-medium">Graduation proposal · {row.name}</h2>
          <Proposal row={row} role={user.role} agentId={builtIn?.id ?? null} onChanged={() => load().catch(() => {})} />
        </section>
      )}
    </div>
  );
}
