"use client";

import { useCallback, useEffect, useState } from "react";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { api, ApiError, type AuditCard, type Digest, type DraftCard, type HandbackCard, type TaskTypeInfo } from "@/lib/api";
import { useUser } from "@/lib/user";

const label = (s: string | null | undefined) => (s ? s.replace(/_/g, " ") : "–");

function Inputs({ inputs }: { inputs: Record<string, string> }) {
  return (
    <>
      {Object.entries(inputs).filter(([, v]) => v).map(([k, v]) => (
        <p key={k} className="text-sm text-stone-700"><span className="text-xs text-stone-500">{label(k)}: </span>{v}</p>
      ))}
    </>
  );
}

function Draft({ card, decisions, onDone }: { card: DraftCard; decisions: string[]; onDone: (msg: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [decision, setDecision] = useState(card.agent.decision);
  const replyKey = Object.keys(card.agent.text_outputs ?? {})[0];
  const [reply, setReply] = useState(replyKey ? card.agent.text_outputs[replyKey] : "");
  const [busy, setBusy] = useState(false);
  const blocked = card.actions.filter((a) => a.status === "blocked");

  async function act(fn: () => Promise<string>) {
    setBusy(true);
    try {
      onDone(await fn());
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-lg border border-stone-200 bg-white p-4">
      <p className="font-medium">{card.case.subject || card.case.id}</p>
      <Inputs inputs={card.case.inputs} />
      <div className="rounded-md bg-stone-50 p-3 text-sm">
        <p>
          The intern would <span className="font-medium">{label(card.agent.decision)}</span>
          {card.confidence !== null && <span className="text-stone-500"> ({Math.round(card.confidence * 100)}% sure)</span>}
        </p>
        {replyKey && card.agent.text_outputs[replyKey] && !editing && (
          <p className="mt-1 whitespace-pre-wrap">{card.agent.text_outputs[replyKey]}</p>
        )}
        {blocked.length > 0 && (
          <p className="mt-1 text-xs text-stone-500">Not allowed, so left out: {blocked.map((b) => `${b.action} (${b.policy.reasons.join("; ")})`).join(", ")}</p>
        )}
      </div>
      {editing && (
        <div className="space-y-2">
          <select value={decision} onChange={(e) => setDecision(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1 text-sm">
            {decisions.map((d) => <option key={d} value={d}>{label(d)}</option>)}
          </select>
          {replyKey && <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={3} className="w-full rounded-md border border-stone-300 px-2 py-1 text-sm" />}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {!editing ? (
          <>
            <button type="button" disabled={busy} className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white"
                    onClick={() => act(async () => { await api.approveDraft(card.prediction_id); return "Approved as drafted."; })}>
              Approve
            </button>
            <button type="button" disabled={busy} className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm"
                    onClick={() => setEditing(true)}>
              Edit
            </button>
          </>
        ) : (
          <>
            <button type="button" disabled={busy} className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white"
                    onClick={() => act(async () => {
                      const r = decision === card.agent.decision
                        ? await api.approveDraft(card.prediction_id, replyKey ? { text_outputs: { [replyKey]: reply } } : {})
                        : await api.rejectDraft(card.prediction_id, decision);
                      return r.status === "rejected" ? "Recorded your decision instead." : "Approved with your edits.";
                    })}>
              Save
            </button>
            <button type="button" className="rounded-md px-3 py-1.5 text-sm text-stone-600" onClick={() => setEditing(false)}>Cancel</button>
          </>
        )}
      </div>
    </li>
  );
}

function Audit({ card, decisions, onDone }: { card: AuditCard; decisions: string[]; onDone: (msg: string) => void }) {
  const [decision, setDecision] = useState(decisions[0]);
  return (
    <li className="space-y-2 rounded-lg border border-stone-200 bg-white p-4">
      <p className="font-medium">{card.case.subject || card.case.id}</p>
      <Inputs inputs={card.case.inputs} />
      <p className="text-xs text-stone-500">The intern already handled this. Decide it yourself; you&apos;ll see its answer after.</p>
      <form className="flex gap-2" onSubmit={async (e) => {
        e.preventDefault();
        const r = await api.submitAudit(card.audit_id, decision);
        const demoted = r.review?.demoted_to ? ` The task type moved back to ${r.review.demoted_to}.` : "";
        onDone(r.result === "pass" ? `Audit passed: the intern also chose ${label(r.agent_decision)}.${demoted}`
          : `Audit failed: the intern chose ${label(r.agent_decision)}.${demoted}`);
      }}>
        <select value={decision} onChange={(e) => setDecision(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1 text-sm">
          {decisions.map((d) => <option key={d} value={d}>{label(d)}</option>)}
        </select>
        <button type="submit" className="rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white">Submit</button>
      </form>
    </li>
  );
}

export default function AutonomyPage() {
  const { user } = useUser();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [handbacks, setHandbacks] = useState<HandbackCard[]>([]);
  const [audits, setAudits] = useState<AuditCard[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isMentor = user?.role === "mentor" || user?.role === "admin";

  useEffect(() => {
    if (!user) return;
    api.taskTypes().then((tts) => {
      setTaskTypes(tts);
      setTaskTypeId((id) => (id && tts.some((t) => t.id === id) ? id : (tts[0]?.id ?? null)));
    }).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [user]);

  const load = useCallback(async (id: string) => {
    setDigest(await api.digest(id));
    if (isMentor) {
      const [d, h, a] = await Promise.all([api.supervised(id), api.handbacks(id), api.audits(id)]);
      setDrafts(d);
      setHandbacks(h);
      setAudits(a);
    }
  }, [isMentor]);

  useEffect(() => {
    if (!taskTypeId || !user) return;
    load(taskTypeId).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [taskTypeId, user, load]);

  const taskType = taskTypes.find((t) => t.id === taskTypeId);
  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const done = (msg: string) => {
    setToast(msg);
    load(taskType.id).catch(() => {});
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Autonomy</h1>
          <p className="max-w-2xl text-sm text-stone-600">
            In supervised practice the intern drafts and you approve. Once autonomous it acts alone, but only through allowed
            actions, hands back anything unusual, and some of its work comes to you blind as an audit.
          </p>
        </div>
        <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />
      </div>
      {error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {toast && <p className="rounded-md bg-stone-900 px-3 py-2 text-sm text-white" role="status">{toast}</p>}

      {digest && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            ["Stage", digest.status],
            ["Handled alone", String(digest.cases_handled)],
            ["Actions taken", String(digest.actions_executed)],
            ["Actions blocked", String(digest.actions_blocked)],
            ["Audits waiting", String(digest.audits_pending)],
          ].map(([k, v]) => (
            <div key={k} className="rounded-lg border border-stone-200 bg-white p-3">
              <dt className="text-xs text-stone-500">{k}</dt>
              <dd className="text-lg font-semibold tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {!isMentor ? (
        <p className="text-sm text-stone-500">Drafts, hand-backs and audits are the mentor&apos;s. You see the totals above.</p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-2">
          <section className="space-y-3">
            <h2 className="font-medium">Waiting for your approval <span className="text-sm font-normal text-stone-500">· {drafts.length}</span></h2>
            {drafts.length === 0 ? <p className="text-sm text-stone-500">Nothing to approve.</p> : (
              <ul className="space-y-3">{drafts.map((d) => <Draft key={d.prediction_id} card={d} decisions={taskType.decision} onDone={done} />)}</ul>
            )}
          </section>
          <div className="space-y-8">
            <section className="space-y-3">
              <h2 className="font-medium">Blind audits <span className="text-sm font-normal text-stone-500">· {audits.length}</span></h2>
              {audits.length === 0 ? <p className="text-sm text-stone-500">No audits waiting.</p> : (
                <ul className="space-y-3">{audits.map((a) => <Audit key={a.audit_id} card={a} decisions={taskType.decision} onDone={done} />)}</ul>
              )}
            </section>
            <section className="space-y-3">
              <h2 className="font-medium">Handed back to you <span className="text-sm font-normal text-stone-500">· {handbacks.length}</span></h2>
              {handbacks.length === 0 ? <p className="text-sm text-stone-500">Nothing handed back.</p> : (
                <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white">
                  {handbacks.map((h) => (
                    <li key={h.prediction_id} className="space-y-1 px-4 py-3 text-sm">
                      <p className="font-medium">{h.case.subject || h.case.id}</p>
                      <ul className="list-disc pl-5 text-stone-600">{h.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            {digest?.recent && digest.recent.length > 0 && (
              <section className="space-y-2">
                <h2 className="font-medium">What it did on its own</h2>
                <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white text-sm">
                  {digest.recent.slice(0, 15).map((r, i) => (
                    <li key={i} className="flex flex-wrap gap-x-2 px-4 py-2">
                      <span className={`rounded px-1.5 text-xs ${r.status === "executed" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>{r.status}</span>
                      <span className="font-medium">{label(r.action)}</span>
                      <span className="min-w-0 flex-1 truncate text-stone-600">{r.subject}</span>
                      {r.reasons.length > 0 && <span className="w-full text-xs text-stone-500">{r.reasons.join("; ")}</span>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
