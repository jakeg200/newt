"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type ContactPrefs as Prefs } from "@/lib/api";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function Toggle({ on, onChange, label, hint }: { on: boolean; onChange: (v: boolean) => void; label: string; hint: string }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span>
        <span className="block font-medium">{label}</span>
        <span className="block text-sm text-stone-500">{hint}</span>
      </span>
      <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)}
              className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${on ? "bg-brand-600" : "bg-stone-300"}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
      </button>
    </label>
  );
}

/** How Newt may reach this person: like telling a new colleague when you're around. */
export function ContactPrefs({ intern }: { intern: string }) {
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    api.preferences().then(setPrefs).catch(() => {});
  }, []);

  if (!prefs) return null;
  const save = async (patch: Partial<Prefs>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    try {
      setPrefs(await api.setPreferences(patch));
      setSaved("Saved");
    } catch (e) {
      setSaved(e instanceof ApiError ? e.message : "Couldn't save");
    }
    setTimeout(() => setSaved(null), 1500);
  };

  return (
    <section className="space-y-5 rounded-3xl border border-stone-200 bg-white p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-xl font-extrabold">How {intern} reaches you</h2>
        {saved && <span className="text-xs text-stone-500" role="status">{saved}</span>}
      </div>
      <p className="-mt-3 text-sm text-stone-500">
        Like telling a new colleague when you&apos;re around. Work that needs you arrives in your hours; questions are rationed.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <p className="font-medium">Working hours</p>
          <div className="flex items-center gap-2 text-sm">
            <input type="time" value={prefs.start} onChange={(e) => save({ start: e.target.value })} className="rounded-full border border-stone-300 px-3 py-1.5" aria-label="Start" />
            <span className="text-stone-400">to</span>
            <input type="time" value={prefs.end} onChange={(e) => save({ end: e.target.value })} className="rounded-full border border-stone-300 px-3 py-1.5" aria-label="End" />
          </div>
          <div className="flex flex-wrap gap-1">
            {DAYS.map((d, i) => {
              const on = prefs.workdays.includes(i);
              return (
                <button key={d} type="button" aria-pressed={on}
                        onClick={() => save({ workdays: on ? prefs.workdays.filter((x) => x !== i) : [...prefs.workdays, i].sort() })}
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${on ? "bg-ink text-white" : "bg-stone-100 text-stone-500"}`}>
                  {d}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-stone-400">Times in {prefs.timezone.replace("_", " ")}</p>
        </div>

        <div className="space-y-2">
          <p className="font-medium">Questions a day, at most</p>
          <div className="flex items-center gap-3">
            <input type="range" min={0} max={10} value={prefs.questions_per_day} onChange={(e) => save({ questions_per_day: Number(e.target.value) })}
                   className="flex-1 accent-[var(--color-brand-600)]" aria-label="Questions a day" />
            <span className="w-6 text-center font-[family-name:var(--font-display)] text-xl font-extrabold">{prefs.questions_per_day}</span>
          </div>
          <p className="text-xs text-stone-400">{intern} only asks what&apos;s worth your time, and never the same thing twice.</p>
        </div>
      </div>

      <div className="space-y-4 border-t border-stone-100 pt-4">
        <Toggle on={prefs.calls} onChange={(v) => save({ calls: v })} label="Can ask for a quick call"
                hint="For things faster said than typed. Always a request, never a surprise." />
        <Toggle on={prefs.urgent_out_of_hours} onChange={(v) => save({ urgent_out_of_hours: v })} label="Urgent things out of hours"
                hint="Only genuinely urgent cases, like a hand-back on something time-critical." />
      </div>

      <div className="space-y-2 border-t border-stone-100 pt-4">
        <p className="font-medium">Where {intern} talks to you</p>
        <div className="flex flex-wrap gap-1.5">
          {([["app", "Here", true], ["slack", "Slack", false], ["teams", "Teams", false], ["email", "Email", false]] as const).map(([k, l, ready]) => (
            <button key={k} type="button" disabled={!ready} onClick={() => save({ channel: k })}
                    className={`rounded-full px-3 py-1.5 text-sm ${prefs.channel === k ? "bg-ink text-white" : "bg-stone-100 text-stone-500"} disabled:opacity-60`}>
              {l}{!ready && <span className="ml-1 text-[10px] uppercase tracking-wide">soon</span>}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
