"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RepredictBanner } from "@/components/RepredictBanner";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { TeachingCard } from "@/components/teaching/TeachingCard";
import { Bubble, PageHeader, Pills } from "@/components/ui";
import { Audit, Draft, Inputs } from "@/components/work/WorkCards";
import { api, ApiError, type AuditCard, type DraftCard, type HandbackCard, type TeachingQueue } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

type Kind = "all" | "draft" | "audit" | "teach" | "handback";

export default function NeedsYouPage() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error: ttError } = useTaskTypes();
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [audits, setAudits] = useState<AuditCard[]>([]);
  const [handbacks, setHandbacks] = useState<HandbackCard[]>([]);
  const [queue, setQueue] = useState<TeachingQueue | null>(null);
  const [kind, setKind] = useState<Kind>("all");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [repredict, setRepredict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isMentor = user?.role === "mentor" || user?.role === "admin";
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  const load = useCallback(async (id: string) => {
    const [d, a, h, q] = await Promise.all([api.supervised(id), api.audits(id), api.handbacks(id), api.teachingQueue(id, 20)]);
    setDrafts(d);
    setAudits(a);
    setHandbacks(h);
    setQueue(q);
  }, []);

  useEffect(() => {
    if (!taskTypeId || !isMentor) return;
    setError(null);
    load(taskTypeId).catch(fail);
  }, [taskTypeId, isMentor, load]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{ttError ?? "Loading…"}</p>;
  const intern = taskType.intern_name;

  if (!isMentor) {
    return (
      <div className="space-y-6">
        <PageHeader title="Needs you" mood="neutral" />
        <div className="max-w-xl">
          <Bubble name={intern}>
            Day-to-day checks go to the mentor. Anything that needs your signature shows on my{" "}
            <Link href="/report" className="font-medium underline">report card</Link>.
          </Bubble>
        </div>
      </div>
    );
  }

  const done = (msg: string) => {
    setToast(msg);
    load(taskType.id).catch(fail);
  };
  const cards = queue?.cards ?? [];
  const counts = { draft: drafts.length, audit: audits.length, teach: cards.length, handback: handbacks.length };
  const total = counts.draft + counts.audit + counts.teach + counts.handback;
  const show = (k: Exclude<Kind, "all">) => kind === "all" || kind === k;

  // One focus item: the most time-sensitive first (drafts are waiting to go out), then audits, lessons, hand-backs.
  const focus =
    show("draft") && drafts[0] ? <Draft key={drafts[0].prediction_id} card={drafts[0]} decisions={taskType.decision} onDone={done} />
    : show("audit") && audits[0] ? <Audit key={audits[0].audit_id} card={audits[0]} decisions={taskType.decision} onDone={done} />
    : show("teach") && cards[0] ? (
      <li className="list-none"><TeachingCard card={cards[0]} busy={busy} onTeach={async (t) => {
        setBusy(true);
        setError(null);
        try {
          const r = await api.lesson({ prediction_id: cards[0].prediction_id, attribution: t.attribution, note: t.note || undefined,
                                       reply_ok: t.reply_ok, rule_text: t.rule_text || undefined });
          setToast(`${r.effect} ${r.remaining} left to teach.`);
          if (r.repredict_run_id) setRepredict(r.repredict_run_id);
          await load(taskType.id);
        } catch (e) {
          fail(e);
        } finally {
          setBusy(false);
        }
      }} /></li>
    )
    : show("handback") && handbacks[0] ? (
      <li className="list-none space-y-2 rounded-3xl border border-stone-200 bg-white p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-brand-700">Handed back to you</p>
        <p className="font-medium">{handbacks[0].case.subject || handbacks[0].case.id}</p>
        <Inputs inputs={handbacks[0].case.inputs} />
        <ul className="list-disc pl-5 text-sm text-stone-600">{handbacks[0].reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <p className="text-sm text-stone-500">Handle it in your usual system. {intern} sees what you did and learns from it.</p>
      </li>
    )
    : null;

  const upNext = [
    ...(show("draft") ? drafts.map((d) => ({ key: d.prediction_id, tag: "Draft", subject: d.case.subject })) : []),
    ...(show("audit") ? audits.map((a) => ({ key: a.audit_id, tag: "Audit", subject: a.case.subject })) : []),
    ...(show("teach") ? cards.map((c) => ({ key: c.prediction_id, tag: "Teach", subject: c.case.subject })) : []),
    ...(show("handback") ? handbacks.map((h) => ({ key: h.prediction_id, tag: "Handed back", subject: h.case.subject })) : []),
  ].slice(1, 8);

  return (
    <div className="space-y-6">
      <PageHeader
        title={total ? <><span className="hl">{total}</span> {total === 1 ? "thing needs" : "things need"} you</> : "Nothing needs you"}
        intro={`Everything ${intern} wants a person for, one at a time. Most take one tap.`}
        mood={total ? "thinking" : "resting"}
        aside={<TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />}
      />
      <Pills value={kind} onChange={setKind} options={[
        { key: "all", label: "All", count: total },
        { key: "draft", label: "Drafts to approve", count: counts.draft },
        { key: "audit", label: "Audits", count: counts.audit },
        { key: "teach", label: "To teach", count: counts.teach },
        { key: "handback", label: "Handed back", count: counts.handback },
      ]} />
      {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">{error}</p>}
      {toast && <p className="animate-rise rounded-full bg-ink px-4 py-2 text-sm text-white" role="status">{toast}</p>}
      {repredict && <RepredictBanner runId={repredict} onDone={() => load(taskType.id).catch(() => {})} />}

      {focus ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
          <ul className="animate-rise">{focus}</ul>
          {upNext.length > 0 && (
            <aside className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Up next</p>
              <ul className="divide-y divide-stone-100 rounded-3xl border border-stone-200 bg-white text-sm">
                {upNext.map((u) => (
                  <li key={u.key} className="flex items-center gap-2 px-4 py-2.5">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                    <span className="min-w-0 flex-1 truncate">{u.subject || "Untitled"}</span>
                    <span className="shrink-0 text-xs text-stone-400">{u.tag}</span>
                  </li>
                ))}
              </ul>
            </aside>
          )}
        </div>
      ) : (
        <div className="max-w-xl animate-rise">
          <Bubble name={intern} mood="resting" growth="adult">
            All caught up! Nothing {kind === "all" ? "" : "of this kind "}needs you right now. I&apos;ll ping you here when something does.
          </Bubble>
        </div>
      )}
    </div>
  );
}
