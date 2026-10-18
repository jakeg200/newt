"use client";

import { useCallback, useEffect, useState } from "react";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { api, ApiError, type AuditCard, type Digest, type DraftCard, type HandbackCard, type TaskTypeInfo } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { Audit, Draft, label } from "@/components/work/WorkCards";
import { useUser } from "@/lib/user";

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
    <div className="stagger space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-4"><InternAvatar mood="working" growth="adult" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">Autonomy</h1></div>
          <p className="max-w-2xl text-sm text-stone-600">
            In supervised practice the intern drafts and you approve. Once autonomous it acts alone, but only through allowed
            actions, hands back anything unusual, and some of its work comes to you blind as an audit.
          </p>
        </div>
        <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />
      </div>
      {error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {toast && <p className="rounded-full bg-ink px-4 py-2 text-sm text-white" role="status">{toast}</p>}

      {digest && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            ["Stage", digest.status],
            ["Handled alone", String(digest.cases_handled)],
            ["Actions taken", String(digest.actions_executed)],
            ["Actions blocked", String(digest.actions_blocked)],
            ["Audits waiting", String(digest.audits_pending)],
          ].map(([k, v]) => (
            <div key={k} className="rounded-3xl border border-stone-200 bg-white p-3">
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
                <ul className="divide-y divide-stone-100 rounded-3xl border border-stone-200 bg-white">
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
                <ul className="divide-y divide-stone-100 rounded-3xl border border-stone-200 bg-white text-sm">
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
