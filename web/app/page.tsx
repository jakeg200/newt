"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { MessageCard, Typing, type Act } from "@/components/chat/MessageCard";
import { InternAvatar, STAGE_GROWTH, type InternStage } from "@/components/InternAvatar";
import { TaskTypeTabs } from "@/components/TaskTypeTabs";
import { stageLabel } from "@/components/ui";
import { api, ApiError, type ChatMessage } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const RANK_TITLE: Record<string, string> = { new_starter: "New starter", intern: "Intern", junior: "Junior", graduate: "Graduate", senior: "Senior" };

const dayLabel = (iso: string) => {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86_400_000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
};

export default function Conversation() {
  const { user, taskTypes, taskTypeId, setTaskTypeId, taskType, error: ttError } = useTaskTypes();
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [intern, setIntern] = useState("Newt");
  const [rank, setRank] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState("");
  const [text, setText] = useState("");
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const mentor = user?.role === "mentor" || user?.role === "admin";
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  const load = useCallback(async (id: string) => {
    const t = await api.thread(id);
    setIntern(t.intern_name);
    setMessages(t.messages);
    setRank(t.rank);
    setStatusLine(t.status_line);
  }, []);

  useEffect(() => {
    if (!taskTypeId) return;
    setMessages(null);
    load(taskTypeId).catch(fail);
    const every = setInterval(() => load(taskTypeId).catch(() => {}), 30_000);
    return () => clearInterval(every);
  }, [taskTypeId, load]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages?.length, typing]);

  if (!user || !taskType) return <p className="text-sm text-stone-500">{ttError ?? "Loading…"}</p>;
  const growth = STAGE_GROWTH[(taskType.status as InternStage)] ?? "egg";
  const waiting = (messages ?? []).filter((m) => m.direction === "newt" && m.status === "open" && m.kind !== "delivery").length;

  const merge = (incoming: ChatMessage[]) =>
    setMessages((cur) => {
      const byId = new Map((cur ?? []).filter((m) => !m.id.startsWith("local-")).map((m) => [m.id, m]));
      incoming.forEach((m) => byId.set(m.id, m));
      return [...byId.values()].sort((a, b) => a.at.localeCompare(b.at));
    });

  async function send(say?: string) {
    const body = (say ?? text).trim();
    if (!body || !taskType) return;
    setText("");
    setError(null);
    const local: ChatMessage = { id: `local-${Date.now()}`, direction: "person", kind: "chat", body, payload: {}, status: "done",
                                 urgency: "normal", at: new Date().toISOString(), answered_at: null };
    setMessages((cur) => [...(cur ?? []), local]);
    setTyping(true);
    try {
      merge(await api.say(taskType.id, body));
    } catch (e) {
      fail(e);
    } finally {
      setTyping(false);
    }
  }

  const act: Act = async (id, action, value, note) => {
    setError(null);
    try {
      merge(await api.replyTo(id, action, value, note));
    } catch (e) {
      fail(e);
    }
  };

  const suggestions = mentor
    ? [["Give a task", `${intern}, pull together this month's `], ["Teach a rule", "Always "], ["How's it going?", "How's it going?"]]
    : [["How's it going?", "How's it going?"], ["Ask for a summary", "Summarise this month's "]];

  let lastDay = "";
  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <section className="flex flex-wrap items-center justify-between gap-4 pb-5 animate-rise">
        <div className="flex items-center gap-3.5">
          <div className="relative">
            <InternAvatar mood="hello" growth={growth} size={72} />
            <span className="absolute bottom-2 right-1 h-3.5 w-3.5 rounded-full border-2 border-cream bg-emerald-500" aria-label="online" />
          </div>
          <div>
            <h1 className="flex items-baseline gap-2 text-3xl leading-tight">
              {intern}
              {rank && <span className="rounded-full bg-brand-100 px-2.5 py-0.5 font-sans text-xs font-semibold tracking-normal text-brand-800">{RANK_TITLE[rank] ?? stageLabel(taskType.status)}</span>}
            </h1>
            <p className="text-sm text-stone-500">{taskType.name}</p>
            {statusLine && (
              <p className="mt-0.5 flex items-center gap-1.5 text-sm font-medium text-ink" aria-live="polite">
                <span className={`h-2 w-2 rounded-full ${waiting ? "bg-brand-500" : "bg-emerald-500"} animate-pulse`} />
                {statusLine}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <TaskTypeTabs taskTypes={taskTypes} value={taskTypeId} onChange={setTaskTypeId} />
          <Link href="/report" className="rounded-full bg-white px-3.5 py-1.5 text-sm font-medium ring-1 ring-stone-200 hover:bg-stone-100">Report card</Link>
        </div>
      </section>

      <div className="min-h-[50vh] space-y-4 rounded-[2rem] bg-stone-100/70 p-3 sm:p-5" role="log" aria-label={`Conversation with ${intern}`}>
        {messages === null && <p className="py-10 text-center text-sm text-stone-400">Loading your conversation…</p>}
        {messages?.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <InternAvatar mood="resting" growth={growth} size={110} />
            <p className="max-w-sm text-stone-600">Nothing yet. {intern} speaks up in working hours, and only when it&apos;s worth your time.</p>
          </div>
        )}
        {messages?.map((m) => {
          const day = dayLabel(m.at);
          const sep = day !== lastDay;
          lastDay = day;
          return (
            <div key={m.id} className="space-y-4">
              {sep && <p className="text-center text-xs font-medium text-stone-400">{day}</p>}
              <MessageCard m={m} act={act} intern={intern} growth={growth} />
            </div>
          );
        })}
        {typing && <Typing growth={growth} />}
        <div ref={end} />
      </div>

      {error && <p className="mt-3 rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-800 ring-1 ring-red-200" role="alert">{error}</p>}

      <div className="sticky bottom-3 mt-4 space-y-2">
        {!text && (
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map(([l, fill]) => (
              <button key={l} type="button" className="rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-stone-600 ring-1 ring-stone-200 backdrop-blur hover:bg-white"
                      onClick={() => (fill.endsWith("?") ? send(fill) : (setText(fill), input.current?.focus()))}>
                {l}
              </button>
            ))}
          </div>
        )}
        <form className="flex items-center gap-2 rounded-full border border-stone-200 bg-white p-1.5 pl-5 shadow-[0_12px_32px_-14px_rgb(27_23_20/0.4)]"
              onSubmit={(e) => { e.preventDefault(); send(); }}>
          <label htmlFor="say" className="sr-only">Message {intern}</label>
          <input id="say" ref={input} value={text} onChange={(e) => setText(e.target.value)} autoComplete="off"
                 placeholder={`Message ${intern}…`} className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-stone-400" />
          <button type="submit" disabled={!text.trim() || typing} aria-label="Send"
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-600 text-white transition-transform hover:bg-brand-700 active:scale-90 disabled:opacity-30">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
