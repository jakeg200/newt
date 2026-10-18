"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { STAGE_MOOD } from "@/components/InternAvatar";
import { Proposal } from "@/components/board/Proposal";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { CareerLadder, OutcomeCard } from "@/components/outcomes/OutcomeCard";
import { ProcessReplay } from "@/components/outcomes/ProcessReplay";
import { ShowsItsWork } from "@/components/outcomes/ShowsItsWork";
import { PageHeader } from "@/components/ui";
import { api, type AgentInfo, type BoardRow, type Career, type ManagerTeam, type Outcomes } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const pct = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);

function Tile({ big, label, note, good }: { big: string; label: string; note?: string; good?: boolean }) {
  return (
    <div className="rounded-3xl border border-stone-200 bg-white p-5">
      <p className={`font-[family-name:var(--font-display)] text-4xl font-extrabold tabular-nums ${good ? "text-emerald-700" : ""}`}>{big}</p>
      <p className="mt-1 font-medium">{label}</p>
      {note && <p className="text-sm text-stone-500">{note}</p>}
    </div>
  );
}

export default function ReportCardPage() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error } = useTaskTypes();
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [teams, setTeams] = useState<ManagerTeam[]>([]);
  const [outcomes, setOutcomes] = useState<Outcomes | null>(null);
  const [career, setCareer] = useState<Career | null>(null);

  const load = useCallback(async () => {
    const [b, a, m] = await Promise.all([api.board(), api.agents(), api.managerDashboard().catch(() => ({ teams: [] as ManagerTeam[] }))]);
    setRows(b);
    setAgents(a);
    setTeams(m.teams);
  }, []);

  useEffect(() => {
    if (user) load().catch(() => {});
  }, [user, load]);

  useEffect(() => {
    if (!taskTypeId) return;
    api.outcomes(taskTypeId).then(setOutcomes).catch(() => {});
    api.career(taskTypeId).then(setCareer).catch(() => {});
  }, [taskTypeId]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const intern = taskType.intern_name;
  const row = rows.find((r) => r.id === taskType.id);
  const team = teams.find((t) => t.team === taskType.team);
  if (!row) return <p className="text-sm text-stone-500">Loading…</p>;
  const ev = row.evaluation;
  const ready = (row.status === "shadow" || row.status === "demoted") ? ev.eligible
    : row.status === "supervised" ? row.supervised_cases >= row.supervised_needed : false;

  return (
    <div className="space-y-8">
      <PageHeader
        title={<>{intern}&apos;s <span className="hl">report card</span></>}
        intro={`How ${intern} is doing at ${taskType.name.toLowerCase()}, in plain numbers, and what it has earned.`}
        mood={STAGE_MOOD[row.status]}
        aside={<TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />}
      />

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr] animate-rise">
        {outcomes && <OutcomeCard o={outcomes} intern={intern} />}
        {career && outcomes && <CareerLadder career={career} promotions={outcomes.promotions} />}
      </div>
      {ready && (
        <p className="rounded-2xl bg-emerald-50 px-4 py-2.5 text-sm font-medium text-emerald-900 ring-1 ring-emerald-200">
          {intern} has earned a review for the next step. See the evidence below.
        </p>
      )}

      <ShowsItsWork taskTypeId={taskType.id} intern={intern} />
      <ProcessReplay taskTypeId={taskType.id} canRun={["mentor", "manager", "admin"].includes(user.role)} />

      <h2 className="pt-2 text-2xl font-extrabold">Why you can trust these numbers</h2>
      <div className="stagger grid gap-3 sm:grid-cols-3">
        <Tile big={pct(ev.agreement_rate)} label="In line with your team" note={`on ${ev.cases} past cases, after your lessons`} />
        <Tile big={pct(ev.ucb, 1)} good={ev.ucb <= ev.alpha} label="Wrong at most, when sure"
              note={`Your limit is ${pct(ev.alpha)}. ${ev.errors_above} mistakes in ${ev.n_above} cases it was sure about.`} />
        <Tile big={pct(ev.coverage)} label="Of the work it can take" note="The rest comes back to you, with a reason." />
        {row.status === "supervised" && (
          <Tile big={`${row.supervised_cases}/${row.supervised_needed}`} label="Practice cases approved" note={`${pct(row.untouched.rate)} approved without edits`} />
        )}
        {row.audits.passed + row.audits.failed > 0 && (
          <Tile big={`${row.audits.passed}/${row.audits.passed + row.audits.failed}`} good={row.audits.failed === 0} label="Spot checks passed"
                note="Cases it handled alone, re-decided blind by your team." />
        )}
        {team && team.hours_returned !== null && (
          <Tile big={`${team.hours_returned}h`} label="Given back to your team"
                note={team.net !== null ? `Worth ${team.settings.currency} ${Math.round(team.net)} after running costs` : undefined} />
        )}
      </div>

      <details className="group rounded-3xl border border-stone-200 bg-white p-5" open={ready}>
        <summary className="cursor-pointer list-none font-medium">
          <span className="mr-2 inline-block transition-transform group-open:rotate-90">›</span>
          {ready ? "Review the evidence and sign" : "Show the maths, signatures and track record"}
        </summary>
        <div className="mt-4">
          <Proposal row={row} role={user.role} agentId={agents.find((a) => a.kind === "built_in")?.id ?? null} onChanged={() => load().catch(() => {})} />
        </div>
      </details>

      <p className="text-sm text-stone-500">
        See <Link href="/learned" className="underline">everything {intern} has learned</Link> or the{" "}
        <Link href="/board" className="underline">detailed task board</Link>.
      </p>
    </div>
  );
}
