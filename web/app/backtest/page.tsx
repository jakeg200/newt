"use client";

import { useCallback, useEffect, useState } from "react";
import { RunResults } from "@/components/backtest/RunResults";
import { api, ApiError, type AgentInfo, type BacktestRun, type Estimate, type TaskTypeInfo } from "@/lib/api";
import { useUser } from "@/lib/user";

const STATUS_STYLE: Record<BacktestRun["status"], string> = {
  queued: "bg-stone-200 text-stone-700",
  running: "bg-sky-100 text-sky-900",
  done: "bg-emerald-100 text-emerald-900",
  failed: "bg-red-100 text-red-800",
};

function NewAgentForm({ onCreated }: { onCreated: (a: AgentInfo) => void }) {
  const [form, setForm] = useState({ name: "", endpoint: "", version: "", model: "" });
  const [error, setError] = useState<string | null>(null);
  const input = "w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm";
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <form
      className="space-y-2 rounded-lg border border-stone-200 bg-white p-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          onCreated(await api.createAgent(form));
        } catch (err) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      }}
    >
      <p className="text-sm text-stone-600">
        A vendor&apos;s or your own agent. We POST each case to its endpoint, signed, and it answers in the task&apos;s output
        shape.
      </p>
      <label className="block space-y-1 text-sm">
        <span>Name</span>
        <input required value={form.name} onChange={set("name")} placeholder="Acme AP agent" className={input} />
      </label>
      <label className="block space-y-1 text-sm">
        <span>Endpoint</span>
        <input required value={form.endpoint} onChange={set("endpoint")} placeholder="https://agent.vendor.com/predict" className={input} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block space-y-1 text-sm">
          <span>Version</span>
          <input required value={form.version} onChange={set("version")} placeholder="2.3.1" className={input} />
        </label>
        <label className="block space-y-1 text-sm">
          <span>Model (optional)</span>
          <input value={form.model} onChange={set("model")} placeholder="vendor-model" className={input} />
        </label>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <button type="submit" className="rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white">
        Register agent
      </button>
    </form>
  );
}

export default function BacktestPage() {
  const { user } = useUser();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [limit, setLimit] = useState(300);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newSecret, setNewSecret] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canRun = user?.role === "mentor" || user?.role === "manager" || user?.role === "admin";
  const canSeeCases = user?.role === "mentor" || user?.role === "admin";
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    if (!user) return;
    Promise.all([api.taskTypes(), api.agents()])
      .then(([tts, ags]) => {
        setTaskTypes(tts);
        setTaskTypeId((id) => (id && tts.some((t) => t.id === id) ? id : (tts[0]?.id ?? null)));
        setAgents(ags);
      })
      .catch(fail);
  }, [user]);

  const loadRuns = useCallback(async (ttId: string) => {
    const list = await api.backtests(ttId);
    setRuns(list);
    setSelected((s) => (s && list.some((r) => r.id === s) ? s : (list[0]?.id ?? null)));
  }, []);

  useEffect(() => {
    if (!taskTypeId || !user) return;
    loadRuns(taskTypeId).catch(fail);
  }, [taskTypeId, user, loadRuns]);

  useEffect(() => {
    if (!taskTypeId || !canRun) return;
    const t = setTimeout(() => {
      api.estimate(taskTypeId, agentId, limit).then(setEstimate).catch(() => setEstimate(null));
    }, 300);
    return () => clearTimeout(t);
  }, [taskTypeId, agentId, limit, canRun]);

  const active = runs.some((r) => r.status === "queued" || r.status === "running");
  useEffect(() => {
    if (!active || !taskTypeId) return;
    const t = setInterval(() => loadRuns(taskTypeId).catch(() => {}), 2000);
    return () => clearInterval(t);
  }, [active, taskTypeId, loadRuns]);

  const taskType = taskTypes.find((t) => t.id === taskTypeId);
  const run = runs.find((r) => r.id === selected);
  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;

  async function start() {
    setError(null);
    try {
      const r = await api.startBacktest({ task_type_id: taskType!.id, agent_id: agentId, limit });
      setSelected(r.id);
      await loadRuns(taskType!.id);
    } catch (e) {
      fail(e);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Backtest</h1>
          <p className="max-w-2xl text-sm text-stone-600">
            Before shadowing live work, the agent replays the mentor&apos;s decided history. Each case is predicted using only
            what was known when it arrived, then compared with what the mentor actually did.
          </p>
        </div>
        {taskTypes.length > 1 && (
          <div className="flex gap-1 rounded-lg bg-stone-200/60 p-1 text-sm" role="tablist" aria-label="Task type">
            {taskTypes.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={t.id === taskTypeId}
                onClick={() => setTaskTypeId(t.id)}
                className={`rounded-md px-3 py-1 ${t.id === taskTypeId ? "bg-white font-medium shadow-sm" : "text-stone-600"}`}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="flex justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <aside className="space-y-6">
          {canRun && (
            <section className="space-y-3 rounded-lg border border-stone-200 bg-white p-4">
              <h2 className="font-medium">New backtest</h2>
              <label className="block space-y-1 text-sm">
                <span>Agent</span>
                <select
                  value={agentId ?? ""}
                  onChange={(e) => setAgentId(e.target.value || null)}
                  className="w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5"
                >
                  <option value="">This team&apos;s apprentice</option>
                  {agents.filter((a) => a.kind === "external").map((a) => (
                    <option key={a.id} value={a.id}>{a.name} v{a.version}</option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1 text-sm">
                <span>Most recent cases</span>
                <input
                  type="number"
                  min={1}
                  max={5000}
                  value={limit}
                  onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
                  className="w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 tabular-nums"
                />
              </label>
              {estimate && (
                <p className="text-xs text-stone-600">
                  {estimate.cases} of {estimate.cases_available} decided cases · {estimate.model}
                  {estimate.samples > 1 && ` × ${estimate.samples} samples`}
                  <br />
                  {estimate.billed_here
                    ? `About $${estimate.est_cost_usd.toFixed(2)} and ${estimate.est_minutes} min.`
                    : estimate.model.startsWith("offline")
                      ? "Offline baseline: no model calls, no cost. Add an API key to use Claude."
                      : "The vendor's own costs; nothing billed here."}
                </p>
              )}
              <button
                type="button"
                disabled={!estimate || estimate.cases === 0 || active}
                onClick={start}
                className="w-full rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-40"
              >
                {active ? "A backtest is running…" : "Start backtest"}
              </button>
              {estimate?.cases === 0 && <p className="text-xs text-stone-500">Capture some decided history first.</p>}
            </section>
          )}

          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">Agents</h2>
              {canRun && !adding && (
                <button type="button" onClick={() => setAdding(true)} className="text-sm text-brand-700 hover:underline">
                  Register external agent
                </button>
              )}
            </div>
            {adding && (
              <NewAgentForm
                onCreated={(a) => {
                  setAdding(false);
                  setNewSecret(a);
                  api.agents().then(setAgents).catch(fail);
                }}
              />
            )}
            {newSecret?.signing_secret && (
              <div className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs">
                <p className="font-medium">Signing secret for {newSecret.name}. Copy it now; it won&apos;t be shown again.</p>
                <code className="block break-all">{newSecret.signing_secret}</code>
                <p>Requests carry X-Agent-Onboarding-Signature: sha256=HMAC of the body with this secret.</p>
              </div>
            )}
            <ul className="space-y-1 text-sm">
              {agents.map((a) => (
                <li key={a.id} className="rounded-md bg-white px-3 py-2 ring-1 ring-stone-200">
                  <p className="font-medium">{a.name}</p>
                  <p className="text-xs text-stone-500">
                    {a.kind === "external" ? `${a.endpoint} · v${a.version}` : `runs on ${a.runs_with.model}`}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <section className="space-y-4">
          {runs.length === 0 ? (
            <p className="text-sm text-stone-500">No backtests yet.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {runs.map((r) => {
                  const s = r.stats as { agreement_rate?: number | null };
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setSelected(r.id)}
                      className={`rounded-lg border px-3 py-1.5 text-left text-xs ${r.id === selected ? "border-stone-900 bg-white" : "border-stone-200 bg-stone-50"}`}
                    >
                      <span className="block font-medium">
                        {new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className={`mt-0.5 inline-block rounded px-1.5 ${STATUS_STYLE[r.status]}`}>{r.status}</span>{" "}
                      {s.agreement_rate !== undefined && s.agreement_rate !== null && (
                        <span className="tabular-nums">{(s.agreement_rate * 100).toFixed(0)}%</span>
                      )}
                      <span className="block text-stone-500">{r.agent_name}</span>
                    </button>
                  );
                })}
              </div>
              {run && (
                <div className="rounded-lg border border-stone-200 bg-white p-5">
                  <RunResults run={run} canSeeCases={canSeeCases} />
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
