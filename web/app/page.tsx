"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { InternAvatar, STAGE_GROWTH, STAGE_MOOD } from "@/components/InternAvatar";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { Bubble, Journey, stageLabel } from "@/components/ui";
import { api, ApiError, type BoardRow, type Digest, type TeachingSummary } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 1000) / 10}%`);
const ago = (iso: string) => {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 1 ? "now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

/** What the intern says about where it is, and the one next step for this person. */
function status(row: BoardRow, manager: boolean): { say: string; cta: string; href: string } {
  const ev = row.evaluation;
  if ((row.status === "shadow" || row.status === "demoted") && ev.eligible)
    return { say: `${ev.errors_above} mistakes in ${ev.n_above} cases I was sure about. At worst I'd be wrong ${pct(ev.ucb)} of the time, under your ${pct(ev.alpha)} limit. I think I'm ready to start drafting for you.`,
             cta: manager ? "See my report card" : "Sign me up for supervised practice", href: "/report" };
  if (row.status === "shadow" || row.status === "demoted")
    return { say: `I'm still shadowing you: ${ev.n_above} cases I was sure about so far, ${ev.more_clean_cases_needed ?? "a few"} more clean ones to go.`,
             cta: manager ? "See my report card" : "Teach me", href: manager ? "/report" : "/inbox" };
  if (row.status === "supervised") {
    const ready = row.supervised_cases >= row.supervised_needed;
    return { say: `I draft, you approve. ${row.supervised_cases} of ${row.supervised_needed} practice cases done${ready ? ", so I'm ready to work on my own if the manager signs." : "."}`,
             cta: ready && manager ? "Sign my autonomy" : "Review my drafts", href: ready && manager ? "/report" : "/inbox" };
  }
  return { say: `I'm working on my own now. ${row.audits.passed} spot checks passed${row.audits.failed ? `, ${row.audits.failed} failed` : ""}. Anything unusual comes straight back to you.`,
           cta: manager ? "See hours saved" : "See what I did", href: "/report" };
}

type Said = { from: "you" | "newt"; text: string; link?: boolean };

export default function Home() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error } = useTaskTypes();
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [summary, setSummary] = useState<TeachingSummary | null>(null);
  const [needs, setNeeds] = useState<{ drafts: number; audits: number; handbacks: number } | null>(null);
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState<Said[]>([]);
  const [sending, setSending] = useState(false);
  const mentor = user?.role === "mentor" || user?.role === "admin";
  const manager = user?.role === "manager";

  useEffect(() => {
    if (user) api.board().then(setRows).catch(() => {});
  }, [user]);

  const load = useCallback(async (id: string) => {
    const [d, s] = await Promise.all([api.digest(id), api.teachingSummary(id)]);
    setDigest(d);
    setSummary(s);
    if (mentor) {
      const [dr, au, hb] = await Promise.all([api.supervised(id), api.audits(id), api.handbacks(id)]);
      setNeeds({ drafts: dr.length, audits: au.length, handbacks: hb.length });
    }
  }, [mentor]);

  useEffect(() => {
    if (taskTypeId) load(taskTypeId).catch(() => {});
  }, [taskTypeId, load]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  const intern = taskType.intern_name;
  const row = rows.find((r) => r.id === taskType.id);
  const s = row ? status(row, manager) : null;
  const toTeach = summary?.queue ?? 0;
  const waiting = needs ? needs.drafts + needs.audits + needs.handbacks + toTeach : 0;
  const alone = (digest?.recent ?? []).filter((r) => r.status === "executed" && r.action === "set_status");
  const hour = new Date().getHours();

  async function send() {
    const text = message.trim();
    if (!text || !taskType) return;
    setSending(true);
    setChat((c) => [...c, { from: "you", text }]);
    setMessage("");
    try {
      const rule = await api.createRule(taskType.id, text);
      setChat((c) => [...c, { from: "newt", link: true, text: rule.decision
        ? `Got it. From now on, when that comes up I'll choose "${rule.decision.replace(/_/g, " ")}". I'll re-check my recent answers with it too.`
        : "Got it, I've added that to my rules. I'll re-check my recent answers with it." }]);
      load(taskType.id).catch(() => {});
    } catch (e) {
      setChat((c) => [...c, { from: "newt", text: `I couldn't turn that into a rule: ${e instanceof ApiError ? e.message : String(e)}. Try naming the decision and the words that trigger it.` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <section className="flex flex-wrap items-center justify-between gap-4 pt-2">
        <div className="flex items-center gap-4 animate-rise">
          <InternAvatar mood="hello" growth={row ? STAGE_GROWTH[row.status] : "egg"} size={104} />
          <div>
            <h1 className="text-4xl">{hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening"}, {user.name.split(" ")[0]}.</h1>
            <p className="text-stone-600">Here&apos;s what <span className="font-medium text-ink">{intern}</span> has been up to.</p>
          </div>
        </div>
        <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />
      </section>

      {row && (
        <div className="rounded-3xl border border-stone-200 bg-white p-5 animate-rise">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-extrabold">{taskType.name}</h2>
            <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-800">{stageLabel(row.status)}</span>
          </div>
          <Journey status={row.status} />
        </div>
      )}

      <section className="stagger space-y-3" aria-label={`Messages from ${intern}`}>
        {s && (
          <Bubble name={intern} mood={STAGE_MOOD[row!.status]} growth={STAGE_GROWTH[row!.status]} time="now">
            <p>{s.say}</p>
            <Link href={s.href} className="mt-2 inline-flex rounded-full bg-brand-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand-700">{s.cta} →</Link>
          </Bubble>
        )}
        {mentor && waiting > 0 && needs && (
          <Bubble name={intern} mood="thinking" growth={row ? STAGE_GROWTH[row.status] : undefined}>
            <p>
              {waiting} {waiting === 1 ? "thing needs" : "things need"} you:{" "}
              {[[needs.drafts, "draft to approve", "drafts to approve"], [needs.audits, "spot check", "spot checks"],
                [toTeach, "case to teach me", "cases to teach me"], [needs.handbacks, "case I handed back", "cases I handed back"]]
                .filter(([n]) => (n as number) > 0).map(([n, one, many]) => `${n} ${n === 1 ? one : many}`).join(", ")}.
            </p>
            <Link href="/inbox" className="mt-2 inline-flex rounded-full bg-ink px-3.5 py-1.5 text-xs font-semibold text-white">Open Needs you →</Link>
          </Bubble>
        )}
        {alone.length > 0 && (
          <Bubble name={intern} mood="working" growth="adult" time={ago(alone[0].at)}>
            <p>I handled {digest?.cases_handled ?? alone.length} cases on my own. The latest:</p>
            <ul className="mt-1.5 space-y-1">
              {alone.slice(0, 4).map((a) => (
                <li key={a.case_id + a.at} className="flex items-center gap-2 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span className="min-w-0 flex-1 truncate">{a.subject}</span>
                  <span className="text-stone-400">{String(a.payload.value ?? "").replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
          </Bubble>
        )}
        {summary?.latest_repredict?.changed !== null && summary?.latest_repredict?.changed !== undefined && (
          <Bubble name={intern} mood="learning" growth={row ? STAGE_GROWTH[row.status] : undefined} time={ago(summary.latest_repredict.created_at)}>
            Your latest rule changed {summary.latest_repredict.changed} of my answers on {summary.latest_repredict.compared} recent cases.
          </Bubble>
        )}
        {summary && summary.rules.active > 0 && (
          <Bubble name={intern} mood="neutral" growth={row ? STAGE_GROWTH[row.status] : undefined}>
            I&apos;m following {summary.rules.active} of your rules. <Link href="/learned" className="font-medium underline">See what I&apos;ve learned</Link>.
          </Bubble>
        )}
        {chat.map((m, i) => m.from === "you" ? (
          <p key={i} className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm text-white">{m.text}</p>
        ) : (
          <Bubble key={i} name={intern} mood="learning" growth={row ? STAGE_GROWTH[row.status] : undefined} time="now">
            {m.text} {m.link && <Link href="/learned" className="font-medium underline">See my rules</Link>}
          </Bubble>
        ))}
      </section>

      {mentor && (
        <form className="sticky bottom-4 flex items-center gap-2 rounded-full border border-stone-200 bg-white p-1.5 pl-5 shadow-[0_10px_30px_-12px_rgb(27_23_20/0.35)]"
              onSubmit={(e) => { e.preventDefault(); send(); }}>
          <label htmlFor="message-newt" className="sr-only">Message {intern}</label>
          <input id="message-newt" value={message} onChange={(e) => setMessage(e.target.value)} disabled={sending}
                 placeholder={`Message ${intern}: e.g. "Always escalate bank detail changes"`}
                 className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-stone-400" />
          <button type="submit" disabled={sending || !message.trim()}
                  className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
            {sending ? "…" : "Send"}
          </button>
        </form>
      )}
    </div>
  );
}
