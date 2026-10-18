"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type DestinationInfo, type TaskTypeInfo } from "@/lib/api";

const ACTION: Record<string, string> = { set_status: "status updates", set_field: "fields", draft_reply: "draft replies", send_reply: "replies", route: "routing" };

/** Where Newt does the work: the firm's own system, or Zapier / Make / n8n, receiving signed actions. */
export function Destinations({ taskType, allowed, intern }: { taskType: TaskTypeInfo; allowed: string[]; intern: string }) {
  const [list, setList] = useState<DestinationInfo[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [actions, setActions] = useState<string[]>(allowed);
  const [secret, setSecret] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.destinations(taskType.id).then(setList).catch(() => {});
  }, [taskType.id]);

  const add = async () => {
    setError(null);
    try {
      const d = await api.addDestination({ task_type_id: taskType.id, name: name || "My system", url, actions });
      setSecret(d.secret);
      setList([...(list ?? []), d]);
      setAdding(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };
  const test = async (id: string) => {
    setTesting(id);
    try {
      const r = await api.testDestination(id);
      setList((cur) => (cur ?? []).map((d) => (d.id === id ? { ...d, last_test: r } : d)));
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-stone-600">
        {intern} sends each action to your system, referring to the original item (&ldquo;reply to the sender of INV-91007&rdquo;). It never holds
        people&apos;s real details; your system does. Works with your own tools, or Zapier, Make and n8n.
      </p>
      {(list ?? []).map((d) => (
        <div key={d.id} className="flex flex-wrap items-center gap-3 rounded-2xl bg-white p-4 ring-1 ring-stone-200">
          <span className={`h-2.5 w-2.5 rounded-full ${d.last_test.ok === false ? "bg-red-500" : d.last_test.ok ? "bg-emerald-500" : "bg-stone-300"}`} />
          <div className="min-w-0 flex-1">
            <p className="font-medium">{d.name}</p>
            <p className="truncate text-xs text-stone-500">{d.url} · {d.actions.map((a) => ACTION[a] ?? a).join(", ")}</p>
            {d.last_test.at && <p className="text-xs text-stone-500">Last test: {d.last_test.ok ? "worked" : `failed (${d.last_test.detail})`}</p>}
          </div>
          <button type="button" onClick={() => test(d.id)} disabled={testing === d.id}
                  className="rounded-full bg-white px-3 py-1.5 text-xs font-medium ring-1 ring-stone-300 hover:bg-stone-100 disabled:opacity-50">
            {testing === d.id ? "Testing…" : "Send a test"}
          </button>
        </div>
      ))}
      {list?.length === 0 && !adding && (
        <p className="rounded-2xl bg-amber-50 px-4 py-2.5 text-sm text-amber-900 ring-1 ring-amber-200">
          Nothing connected yet, so {intern}&apos;s work is simulated and labelled that way everywhere.
        </p>
      )}
      {secret && (
        <div className="rounded-2xl bg-ink p-4 text-sm text-white">
          <p className="font-medium">Your signing secret (shown once)</p>
          <code className="mt-1 block break-all text-brand-200">{secret}</code>
          <p className="mt-1 text-xs text-white/60">Your system checks each request&apos;s X-Newt-Signature with it.</p>
        </div>
      )}
      {adding ? (
        <form className="space-y-2.5 rounded-2xl bg-white p-4 ring-1 ring-stone-200" onSubmit={(e) => { e.preventDefault(); add(); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Xero via Zapier"
                 className="w-full rounded-full border border-stone-300 px-3.5 py-1.5 text-sm" />
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.zapier.com/…" required type="url"
                 className="w-full rounded-full border border-stone-300 px-3.5 py-1.5 text-sm" />
          <div className="flex flex-wrap gap-1.5">
            {allowed.map((a) => {
              const on = actions.includes(a);
              return (
                <button key={a} type="button" aria-pressed={on} onClick={() => setActions(on ? actions.filter((x) => x !== a) : [...actions, a])}
                        className={`rounded-full px-3 py-1 text-xs ${on ? "bg-ink text-white" : "bg-stone-100 text-stone-500"}`}>
                  {ACTION[a] ?? a}
                </button>
              );
            })}
          </div>
          {error && <p className="text-sm text-red-700">{error}</p>}
          <div className="flex gap-2">
            <button type="submit" className="rounded-full bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white">Connect</button>
            <button type="button" onClick={() => setAdding(false)} className="rounded-full px-3 py-1.5 text-sm text-stone-500">Cancel</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setAdding(true)} className="rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-300 hover:bg-stone-100">
          + Connect a system
        </button>
      )}
    </div>
  );
}
