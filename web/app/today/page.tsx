"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bubble, PageHeader } from "@/components/ui";
import { ChangeTest } from "@/components/improve/ChangeTest";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { TeachingCard } from "@/components/teaching/TeachingCard";
import { api, ApiError, type TaskTypeInfo, type TeachingQueue, type TeachingSummary } from "@/lib/api";
import { useUser } from "@/lib/user";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

function Stat({ name, value, note }: { name: string; value: string; note?: React.ReactNode }) {
  return (
    <div className="rounded-3xl border border-stone-200 bg-white p-5">
      <p className="text-xs text-stone-500">{name}</p>
      <p className="font-[family-name:var(--font-display)] text-3xl font-extrabold tabular-nums">{value}</p>
      {note && <p className="mt-0.5 text-xs text-stone-500">{note}</p>}
    </div>
  );
}

export default function TodayPage() {
  const { user } = useUser();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [summary, setSummary] = useState<TeachingSummary | null>(null);
  const [queue, setQueue] = useState<TeachingQueue | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [change, setChange] = useState<string | null>(null);
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

  const load = useCallback(async (ttId: string) => {
    const [s, q] = await Promise.all([api.teachingSummary(ttId), isMentor ? api.teachingQueue(ttId, 5) : Promise.resolve(null)]);
    setSummary(s);
    setQueue(q);
  }, [isMentor]);

  useEffect(() => {
    if (!taskTypeId || !user) return;
    setError(null);
    setChange(null);
    load(taskTypeId).catch(fail);
  }, [taskTypeId, user, load]);

  const taskType = taskTypes.find((t) => t.id === taskTypeId);
  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const card = queue?.cards[0];
  const judge = summary?.judge;

  return (
    <div className="space-y-6">
      <PageHeader
        title={<>Teach <span className="hl">{taskType.intern_name}</span> today</>}
        intro={<>Only the cases worth your time: where {taskType.intern_name} differed from you or wasn&apos;t sure, plus the odd spot check.
          Agreements are counted, not reviewed. One tap per card.</>}
        mood="learning"
        aside={<TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />}
      />

      {error && (
        <div className="flex justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {summary && (
        <div className="stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat name="To teach" value={String(summary.queue)} note={queue && Object.entries(queue.by_kind).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(" · ")} />
          <Stat name="Agrees with you" value={pct(summary.agreement)} note={`${summary.predicted} cases in the latest backtest, after your lessons`} />
          <Stat name="Lessons given" value={String(summary.lessons)} note={summary.rules.active ? `${summary.rules.active} active rules` : "no rules yet"} />
          <Stat
            name="Reply judge agrees with you"
            value={judge?.rate === null || judge?.rate === undefined ? "–" : pct(judge.rate)}
            note={judge && (judge.trusted
              ? `${judge.agree} of ${judge.compared} replies · trusted`
              : `${judge.agree} of ${judge.compared} replies · not trusted until ${judge.trust_bar.min_lessons} rated at ${pct(judge.trust_bar.rate)}`)}
          />
        </div>
      )}

      {change && <ChangeTest key={change} id={change} onDone={() => taskTypeId && load(taskTypeId).catch(() => {})} />}
      {toast && (
        <p className="rounded-md bg-stone-900 px-3 py-2 text-sm text-white" role="status">
          {toast}
        </p>
      )}

      {!isMentor ? (
        <p className="text-sm text-stone-500">The teaching queue is the mentor&apos;s. You see the totals above.</p>
      ) : !summary?.run_id ? (
        <p className="text-sm text-stone-500">
          Nothing to teach yet. <Link href="/backtest" className="text-brand-700 underline">Run a backtest</Link> first.
        </p>
      ) : card ? (
        <TeachingCard
          card={card}
          busy={busy}
          onTeach={async (t) => {
            setBusy(true);
            setError(null);
            try {
              const r = await api.lesson({ prediction_id: card.prediction_id, attribution: t.attribution, note: t.note || undefined,
                                           reply_ok: t.reply_ok, rule_text: t.rule_text || undefined });
              setToast(`${r.effect} Saved in ${(r.elapsed_ms / 1000).toFixed(2)} s. ${r.remaining} left.`);
              if (r.improvement_id) setChange(r.improvement_id);
              await load(taskType.id);
            } catch (e) {
              fail(e);
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : (
        <div className="max-w-xl animate-rise">
          <Bubble name={taskType.intern_name} mood="resting">
            All caught up! Nothing in this backtest needs you. Here&apos;s <Link href="/learned" className="font-medium underline">what I&apos;ve learned</Link> so far.
          </Bubble>
        </div>
      )}
    </div>
  );
}
