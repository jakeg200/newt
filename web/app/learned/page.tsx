"use client";

import { useCallback, useEffect, useState } from "react";
import { RepredictBanner } from "@/components/RepredictBanner";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { api, ApiError, type RuleExample, type RuleInfo, type TaskTypeInfo } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

const label = (s: string | null) => (s ? s.replace(/_/g, " ") : "no decision named");

function RuleRow({ rule, onSave, onStatus }: {
  rule: RuleInfo;
  onSave: (text: string) => Promise<void>;
  onStatus: (status: RuleInfo["status"]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(rule.text);
  const [examples, setExamples] = useState<RuleExample[] | null>(null);
  const [open, setOpen] = useState(false);
  const button = "rounded-md border border-stone-300 bg-white px-2 py-0.5 text-xs hover:bg-stone-50";

  const source = rule.source === "mentor"
    ? "Yours"
    : `Learned from ${rule.stats.support ?? rule.examples} cases${rule.stats.precision ? `, right ${Math.round(rule.stats.precision * 100)}% of the time` : ""}`;

  return (
    <li className="space-y-2 px-4 py-3">
      {editing ? (
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await onSave(text);
            setEditing(false);
          }}
        >
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="w-full rounded-md border border-stone-300 px-2.5 py-1.5 text-sm" />
          <div className="flex gap-2">
            <button type="submit" className="rounded-full bg-ink px-4 py-1 text-xs font-medium text-white">Save and re-predict</button>
            <button type="button" onClick={() => { setText(rule.text); setEditing(false); }} className="text-xs text-stone-500">Cancel</button>
          </div>
        </form>
      ) : (
        <p className="text-sm">{rule.text}</p>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs text-stone-500">
        <span className="rounded bg-stone-100 px-1.5 py-0.5 text-stone-700">{label(rule.decision)}</span>
        <span>{source}</span>
        {rule.version > 1 && <span>· edited (v{rule.version})</span>}
        {rule.examples > 0 && (
          <button
            type="button"
            className="underline"
            onClick={async () => {
              setOpen(!open);
              if (!examples) setExamples(await api.ruleExamples(rule.id));
            }}
          >
            {open ? "Hide examples" : `${rule.examples} examples`}
          </button>
        )}
        <span className="ml-auto flex gap-1.5">
          {!editing && <button type="button" className={button} onClick={() => setEditing(true)}>Edit</button>}
          {rule.status === "proposed" && <button type="button" className={button} onClick={() => onStatus("active")}>Accept</button>}
          {rule.status === "proposed" && <button type="button" className={button} onClick={() => onStatus("retired")}>Dismiss</button>}
          {rule.status === "active" && <button type="button" className={button} onClick={() => onStatus("retired")}>Retire</button>}
          {rule.status === "retired" && <button type="button" className={button} onClick={() => onStatus("active")}>Reactivate</button>}
        </span>
      </div>
      {open && (
        <ul className="space-y-1 rounded-md bg-stone-50 p-2 text-xs">
          {(examples ?? []).map((e) => (
            <li key={e.case_id}>
              <span className="font-medium">{e.subject || e.case_id}</span>: {Object.values(e.inputs).filter(Boolean).join(" · ").slice(0, 160)} →{" "}
              <span className="font-medium">{label(e.decision)}</span>
            </li>
          ))}
          {examples === null && <li>Loading…</li>}
        </ul>
      )}
    </li>
  );
}

export default function LearnedPage() {
  const { user } = useUser();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [rules, setRules] = useState<RuleInfo[]>([]);
  const [repredict, setRepredict] = useState<string | null>(null);
  const [inferring, setInferring] = useState(false);
  const [newRule, setNewRule] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isMentor = user?.role === "mentor" || user?.role === "admin";
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    if (!user) return;
    api.taskTypes().then((tts) => {
      setTaskTypes(tts);
      setTaskTypeId((id) => (id && tts.some((t) => t.id === id) ? id : (tts[0]?.id ?? null)));
    }).catch(fail);
  }, [user]);

  const load = useCallback(async (ttId: string) => setRules(await api.rules(ttId)), []);

  useEffect(() => {
    if (!taskTypeId || !isMentor) return;
    setError(null);
    setRepredict(null);
    load(taskTypeId).catch(fail);
  }, [taskTypeId, isMentor, load]);

  const taskType = taskTypes.find((t) => t.id === taskTypeId);
  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  if (!isMentor) return <p className="text-sm text-stone-500">These are the mentor&apos;s rules; only the mentor sees and edits them.</p>;

  async function change(fn: () => Promise<RuleInfo>) {
    setError(null);
    try {
      const r = await fn();
      if (r.repredict_run_id) setRepredict(r.repredict_run_id);
      await load(taskType!.id);
    } catch (e) {
      fail(e);
    }
  }

  const groups: { status: RuleInfo["status"]; title: string; blurb: string }[] = [
    { status: "active", title: "What the intern follows", blurb: "Used on every new case. Edit one and it re-predicts your backlog." },
    { status: "proposed", title: "What it thinks you do", blurb: "Spotted in your decisions. Accept the ones that are right, fix the ones that are nearly right." },
    { status: "retired", title: "Retired", blurb: "" },
  ];

  return (
    <div className="stagger space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-4"><InternAvatar mood="learning" growth="eft" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">What I&apos;ve learned</h1></div>
          <p className="max-w-2xl text-sm text-stone-600">
            The intern&apos;s picture of how you decide, in plain English. Fixing one rule fixes every case it touches.
          </p>
        </div>
        <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />
      </div>

      {error && (
        <div className="flex justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {repredict && <RepredictBanner key={repredict} runId={repredict} />}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={inferring}
          onClick={async () => {
            setInferring(true);
            try {
              await api.inferRules(taskType.id);
              await load(taskType.id);
            } catch (e) {
              fail(e);
            } finally {
              setInferring(false);
            }
          }}
          className="rounded-full bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-40"
        >
          {inferring ? "Reading your decisions…" : "Find rules in my decisions"}
        </button>
        <form
          className="flex min-w-[18rem] flex-1 gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!newRule.trim()) return;
            await change(() => api.createRule(taskType.id, newRule));
            setNewRule("");
          }}
        >
          <input value={newRule} onChange={(e) => setNewRule(e.target.value)} placeholder='Add a rule, e.g. When an item mentions "key account", choose escalate.'
                 className="flex-1 rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm" />
          <button type="submit" className="rounded-full border border-stone-300 bg-white px-4 py-1.5 text-sm font-medium">Add</button>
        </form>
      </div>

      {groups.map((g) => {
        const list = rules.filter((r) => r.status === g.status)
          .sort((a, b) => g.status === "proposed" ? (b.stats.support ?? 0) - (a.stats.support ?? 0) : 0);
        if (list.length === 0 && g.status === "retired") return null;
        return (
          <section key={g.status} className="space-y-2">
            <div>
              <h2 className="font-medium">{g.title} <span className="text-sm font-normal text-stone-500">· {list.length}</span></h2>
              {g.blurb && <p className="text-sm text-stone-500">{g.blurb}</p>}
            </div>
            {list.length === 0 ? (
              <p className="text-sm text-stone-400">None yet.</p>
            ) : (
              <ul className="divide-y divide-stone-100 rounded-3xl border border-stone-200 bg-white">
                {list.map((r) => (
                  <RuleRow key={`${r.id}-${r.version}-${r.status}`} rule={r}
                           onSave={(text) => change(() => api.updateRule(r.id, { text }))}
                           onStatus={(status) => change(() => api.updateRule(r.id, { status }))} />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
