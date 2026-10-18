"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type ManagerSettings, type ManagerTeam, type Stage } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

const pct = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);
const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const STAGE_STYLE: Record<Stage, string> = {
  shadow: "bg-stone-200 text-stone-800",
  supervised: "bg-sky-100 text-sky-900",
  autonomous: "bg-emerald-100 text-emerald-900",
  demoted: "bg-red-100 text-red-800",
};

function money(x: number | null, currency: string) {
  if (x === null) return "–";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(x);
  } catch {
    return `${currency} ${x.toFixed(0)}`;
  }
}

function SettingsForm({ team, settings, onSaved }: { team: string; settings: ManagerSettings; onSaved: () => void }) {
  const [form, setForm] = useState({
    currency: settings.currency, usd_rate: String(settings.usd_rate),
    hourly_cost: settings.hourly_cost?.toString() ?? "", minutes_per_case: settings.minutes_per_case?.toString() ?? "",
    intern_name: settings.intern_name,
  });
  const [error, setError] = useState<string | null>(null);
  const input = "w-full rounded-md border border-stone-300 bg-white px-2 py-1 text-sm";
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <form
      className="grid grid-cols-2 gap-2 sm:grid-cols-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await api.managerSettings(team, {
            currency: form.currency.toUpperCase(), usd_rate: Number(form.usd_rate),
            ...(form.hourly_cost ? { hourly_cost: Number(form.hourly_cost) } : {}),
            ...(form.minutes_per_case ? { minutes_per_case: Number(form.minutes_per_case) } : {}),
            ...(form.intern_name.trim() ? { intern_name: form.intern_name.trim() } : {}),
          });
          onSaved();
        } catch (err) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      }}
    >
      <label className="space-y-0.5 text-xs text-stone-500">Your intern&apos;s name
        <input value={form.intern_name} onChange={set("intern_name")} maxLength={30} className={input} />
      </label>
      <label className="space-y-0.5 text-xs text-stone-500">Minutes a person spends per case
        <input value={form.minutes_per_case} onChange={set("minutes_per_case")} inputMode="decimal" placeholder="e.g. 6" className={input} />
      </label>
      <label className="space-y-0.5 text-xs text-stone-500">Loaded hourly cost
        <input value={form.hourly_cost} onChange={set("hourly_cost")} inputMode="decimal" placeholder="e.g. 45" className={input} />
      </label>
      <label className="space-y-0.5 text-xs text-stone-500">Currency
        <input value={form.currency} onChange={set("currency")} maxLength={3} className={input} />
      </label>
      <label className="space-y-0.5 text-xs text-stone-500">{form.currency || "Units"} per US dollar
        <input value={form.usd_rate} onChange={set("usd_rate")} inputMode="decimal" className={input} />
      </label>
      <div className="flex items-end">
        <button type="submit" className="w-full rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-white">Save</button>
      </div>
      {error && <p className="col-span-full text-sm text-red-700">{error}</p>}
    </form>
  );
}

export default function ManagerPage() {
  const { user } = useUser();
  const [data, setData] = useState<{ period_days: number; teams: ManagerTeam[] } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api.managerDashboard().then(setData).catch((e) => setError(e instanceof ApiError ? e.message : String(e))), []);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user || !data) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const isManager = user.role === "manager" || user.role === "admin";

  return (
    <div className="stagger space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-4"><InternAvatar mood="neutral" growth="adult" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">Manager</h1></div>
        <p className="max-w-2xl text-sm text-stone-600">
          What the agents did for each team in the last {data.period_days} days, and what it&apos;s worth. People&apos;s own
          performance isn&apos;t measured here.
        </p>
      </div>

      {data.teams.map((t) => {
        const cur = t.settings.currency;
        return (
          <section key={t.team} className="space-y-4 rounded-3xl border border-stone-200 bg-white p-5">
            <header className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-medium">{label(t.team)}</h2>
              <p className="text-sm text-stone-500">
                {t.handbook ? `Handbook v${t.handbook.version}, approved ${new Date(t.handbook.approved_at).toLocaleDateString()}` : "No approved handbook"}
              </p>
            </header>

            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <dt className="text-xs text-stone-500">Cases the agent handled</dt>
                <dd className="text-2xl font-semibold tabular-nums">{t.cases_handled}</dd>
              </div>
              <div>
                <dt className="text-xs text-stone-500">Hours returned</dt>
                <dd className="text-2xl font-semibold tabular-nums">{t.hours_returned ?? "–"}</dd>
                {t.hours_returned === null && <dd className="text-xs text-stone-500">Set minutes per case</dd>}
              </div>
              <div>
                <dt className="text-xs text-stone-500">Value of those hours</dt>
                <dd className="text-2xl font-semibold tabular-nums">{money(t.value_of_hours, cur)}</dd>
              </div>
              <div>
                <dt className="text-xs text-stone-500">Agent running cost</dt>
                <dd className="text-2xl font-semibold tabular-nums">{money(t.running_cost, cur)}</dd>
                <dd className="text-xs text-stone-500">
                  live ${t.running_cost_usd.live.toFixed(2)} · testing ${t.running_cost_usd.evaluation.toFixed(2)}
                </dd>
              </div>
            </dl>
            {t.net !== null && (
              <p className={`text-sm font-medium ${t.net >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                Net {t.net >= 0 ? "saving" : "cost"}: {money(Math.abs(t.net), cur)} over {data.period_days} days
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-sm">
                <thead className="text-xs text-stone-500">
                  <tr>
                    <th className="py-1 font-medium">Task type</th>
                    <th className="py-1 font-medium">Stage</th>
                    <th className="py-1 font-medium">Handled (alone / approved)</th>
                    <th className="py-1 font-medium">Coverage</th>
                    <th className="py-1 font-medium">Hand-back rate</th>
                    <th className="py-1 font-medium">Audits</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {t.task_types.map((tt) => (
                    <tr key={tt.id}>
                      <td className="py-2">{tt.name}</td>
                      <td className="py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_STYLE[tt.status]}`}>{tt.status}</span></td>
                      <td className="py-2 tabular-nums">{tt.handled.autonomous} / {tt.handled.supervised}</td>
                      <td className="py-2 tabular-nums">{pct(tt.coverage)}</td>
                      <td className="py-2 tabular-nums">{pct(tt.hand_back_rate)}</td>
                      <td className="py-2 text-xs text-stone-600">
                        {tt.audits.passed + tt.audits.failed ? `${tt.audits.passed} passed, ${tt.audits.failed} failed` : "–"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {isManager && (
              editing === t.team ? (
                <SettingsForm team={t.team} settings={t.settings} onSaved={() => { setEditing(null); load(); }} />
              ) : (
                <button type="button" onClick={() => setEditing(t.team)} className="text-sm text-brand-700 hover:underline">
                  {t.settings.minutes_per_case ? "Change cost assumptions" : "Set minutes per case and hourly cost"}
                </button>
              )
            )}
            {t.task_types[0]?.time_to_decision_minutes !== null && t.task_types[0]?.time_to_decision_minutes !== undefined && (
              <p className="text-xs text-stone-500">
                For reference: items in the history waited a median of {Math.round(t.task_types[0].time_to_decision_minutes)} minutes for a
                decision. That&apos;s elapsed time, not effort, so it isn&apos;t used for hours returned.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
