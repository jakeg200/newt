"use client";

import { useState } from "react";
import { InternAvatar, type Growth, type Mood } from "@/components/InternAvatar";
import type { ChatMessage, ReplyAction } from "@/lib/api";

const label = (s: unknown) => String(s ?? "").replace(/_/g, " ");
const pct = (x: unknown) => (typeof x === "number" ? `${Math.round(x * 1000) / 10}%` : "–");
const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const LESSON: Record<string, string> = {
  intern_wrong: "Yes, you were wrong",
  both_fine: "Both are fine",
  mentor_changed: "I'd change my call",
  couldnt_know: "You couldn't have known",
};

const MOOD: Record<ChatMessage["kind"], Mood> = {
  standup: "hello", question: "thinking", delivery: "working", handback: "handing-back", draft: "drafting",
  promotion: "graduated", ack: "neutral", chat: "neutral",
};

export type Act = (id: string, action: ReplyAction, value?: string, note?: string) => Promise<void>;

function Chip({ children, onClick, primary, disabled }: { children: React.ReactNode; onClick: () => void; primary?: boolean; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all active:scale-95 disabled:opacity-40 ${
              primary ? "bg-ink text-white hover:bg-stone-800" : "bg-white text-ink ring-1 ring-stone-300 hover:bg-stone-100"}`}>
      {children}
    </button>
  );
}

function Answered({ m }: { m: ChatMessage }) {
  const a = m.payload.answer as { action: string; value?: string } | undefined;
  if (m.status === "done" && !a) return <p className="mt-2 text-xs text-stone-400">Dealt with elsewhere ✓</p>;
  if (!a) return null;
  const text = a.action === "approve" ? "Approved" : a.action === "sign" ? "Signed" : a.action === "dismiss" ? "Not now"
    : a.action === "lesson" ? LESSON[a.value ?? ""] ?? label(a.value) : a.action === "answer" ? "Answered" : label(a.value);
  return <p className="mt-2 inline-flex rounded-full bg-stone-100 px-2.5 py-0.5 text-xs text-stone-600">You: {text} ✓</p>;
}

function CaseBox({ c }: { c?: { subject?: string; inputs?: Record<string, string> } }) {
  if (!c) return null;
  return (
    <div className="mt-2 rounded-2xl bg-stone-50 px-3.5 py-2.5 text-sm">
      <p className="font-medium">{c.subject || "Untitled"}</p>
      {Object.entries(c.inputs ?? {}).filter(([, v]) => v).slice(0, 3).map(([k, v]) => (
        <p key={k} className="text-stone-600"><span className="text-xs text-stone-400">{label(k)}: </span>{v}</p>
      ))}
    </div>
  );
}

function Body({ m, act, open }: { m: ChatMessage; act: Act; open: boolean }) {
  const p = m.payload;
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [other, setOther] = useState(false);
  const [redo, setRedo] = useState(false);
  const run = async (action: ReplyAction, value?: string, note?: string) => {
    setBusy(true);
    try {
      await act(m.id, action, value, note);
    } finally {
      setBusy(false);
    }
  };

  switch (m.kind) {
    case "standup": {
      const s = p.stats ?? {};
      const chips = [
        ["handled alone", s.handled], ["drafts", s.drafts], ["need your call", s.handbacks], ["spot checks", s.audits],
      ].filter(([, n]) => typeof n === "number" && n > 0);
      return (
        <>
          <p className="hand text-lg leading-none text-brand-700">Morning stand-up</p>
          <p className="mt-1">{m.body}</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5 text-xs">
            {chips.map(([k, n]) => <span key={k as string} className="rounded-full bg-brand-50 px-2.5 py-1 font-medium text-brand-800">{n as number} {k as string}</span>)}
            {typeof s.agreement === "number" && <span className="rounded-full bg-stone-100 px-2.5 py-1 text-stone-600">{pct(s.agreement)} in line with you</span>}
          </div>
        </>
      );
    }
    case "question":
      return (
        <>
          <p>{m.body}</p>
          {p.type === "case" && <CaseBox c={p.case} />}
          {open && p.type === "bank" && (
            <form className="mt-2.5 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) run("answer", text); }}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="A sentence or two is plenty"
                     className="min-w-0 flex-1 rounded-full border border-stone-300 bg-white px-3.5 py-1.5 text-sm outline-none focus:border-ink" />
              <Chip primary disabled={busy || !text.trim()} onClick={() => text.trim() && run("answer", text)}>Answer</Chip>
            </form>
          )}
          {open && (p.type === "case" || p.type === "lesson") && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {(p.options as string[]).map((o) => (
                <Chip key={o} disabled={busy} onClick={() => run(p.type === "case" ? "decide" : "lesson", o)}>
                  {p.type === "lesson" ? LESSON[o] : label(o)}
                </Chip>
              ))}
            </div>
          )}
          {open && <button type="button" onClick={() => run("dismiss")} className="mt-2 text-xs text-stone-400 hover:text-stone-600">Not now</button>}
        </>
      );
    case "handback":
      return (
        <>
          <p>{m.body}</p>
          <CaseBox c={p.case} />
          {(p.reasons as string[] | undefined)?.length ? (
            <ul className="mt-2 space-y-0.5 text-xs text-stone-500">{(p.reasons as string[]).map((r, i) => <li key={i}>• {r}</li>)}</ul>
          ) : null}
          {open && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {(p.options as string[]).map((o) => <Chip key={o} disabled={busy} onClick={() => run("decide", o)}>{label(o)}</Chip>)}
            </div>
          )}
        </>
      );
    case "draft":
      return (
        <>
          <p>{m.body}</p>
          <CaseBox c={p.case} />
          <div className="mt-2 rounded-2xl border border-brand-200 bg-brand-50/60 px-3.5 py-2.5 text-sm">
            <p className="text-xs font-medium uppercase tracking-wide text-brand-700">My draft · {label(p.decision)}</p>
            {p.reply && <p className="mt-1 whitespace-pre-wrap text-stone-700">{p.reply}</p>}
          </div>
          {open && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              <Chip primary disabled={busy} onClick={() => run("approve")}>Approve</Chip>
              {!other ? <Chip disabled={busy} onClick={() => setOther(true)}>Do it differently</Chip>
                : (p.options as string[]).filter((o) => o !== p.decision).map((o) => (
                  <Chip key={o} disabled={busy} onClick={() => run("reject", o)}>{label(o)}</Chip>
                ))}
            </div>
          )}
        </>
      );
    case "promotion":
      return (
        <>
          <p className="hand text-lg leading-none text-brand-700">{p.to === "autonomous" ? "Ready to work on my own?" : "Ready to start drafting?"}</p>
          <p className="mt-1">{m.body}</p>
          <div className="mt-2.5 grid grid-cols-3 gap-2 text-center">
            {[["mistakes", `${p.errors_above}/${p.n_above}`], ["wrong at most", pct(p.ucb)], ["of the work", pct(p.coverage)]].map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-stone-50 py-2">
                <p className="font-[family-name:var(--font-display)] text-xl font-extrabold">{v}</p>
                <p className="text-[11px] text-stone-500">{k}</p>
              </div>
            ))}
          </div>
          {open && (
            <div className="mt-2.5 flex gap-1.5">
              <Chip primary disabled={busy} onClick={() => run("sign")}>Sign</Chip>
              <Chip disabled={busy} onClick={() => run("dismiss")}>Not yet</Chip>
            </div>
          )}
        </>
      );
    case "delivery": {
      const items = (p.items as string[] | undefined) ?? [];
      const fb = p.feedback?.value as string | undefined;
      return (
        <>
          {p.title && <p className="font-semibold">{p.title}</p>}
          <p className={p.title ? "mt-0.5 text-stone-700" : ""}>{m.body}</p>
          {items.length > 0 && (
            <ul className="mt-2 divide-y divide-stone-100 rounded-2xl bg-stone-50 text-sm">
              {items.slice(0, other ? 25 : 6).map((it, i) => <li key={i} className="px-3.5 py-1.5">{it}</li>)}
              {items.length > 6 && !other && (
                <li><button type="button" onClick={() => setOther(true)} className="w-full px-3.5 py-1.5 text-left text-xs font-medium text-brand-700">Show all {items.length}</button></li>
              )}
            </ul>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {fb ? <span className="text-xs text-stone-400">{fb === "good" ? "You liked this ✓" : "Redone below ↓"}</span> : (
              <>
                <Chip disabled={busy} onClick={() => run("feedback", "good")}>👍 Good</Chip>
                <Chip disabled={busy} onClick={() => setRedo(!redo)}>↻ Redo</Chip>
                <Chip disabled={busy} onClick={() => navigator.clipboard?.writeText([p.title, m.body, ...items].filter(Boolean).join("\n"))}>Copy</Chip>
              </>
            )}
          </div>
          {!fb && redo && (
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); run("feedback", "redo", text.trim()); }}>
              <input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="What should I do differently?"
                     className="min-w-0 flex-1 rounded-full border border-stone-300 bg-white px-3.5 py-1.5 text-sm outline-none focus:border-ink" />
              <Chip primary disabled={busy} onClick={() => run("feedback", "redo", text.trim())}>Redo</Chip>
            </form>
          )}
        </>
      );
    }
    default:
      return <p>{m.body}</p>;
  }
}

export function MessageCard({ m, act, intern, growth }: { m: ChatMessage; act: Act; intern: string; growth: Growth }) {
  if (m.direction === "person") {
    return (
      <div className="flex justify-end animate-rise">
        <div className="max-w-[85%] sm:max-w-[70%]">
          <p className="rounded-3xl rounded-br-lg bg-ink px-4 py-2.5 text-[15px] text-white">{m.body}</p>
          <p className="mt-1 pr-2 text-right text-[11px] text-stone-400">{time(m.at)}</p>
        </div>
      </div>
    );
  }
  const open = m.status === "open";
  const plain = m.kind === "ack" || m.kind === "chat";
  return (
    <div className="flex items-end gap-2.5 animate-rise">
      <InternAvatar mood={(m.payload.mood as Mood) ?? MOOD[m.kind]} growth={growth} size={36} decorative animated={false} className="mb-5 shrink-0" />
      <div className="min-w-0 max-w-[88%] sm:max-w-[75%]">
        <div className={`rounded-3xl rounded-bl-lg px-4 py-3 text-[15px] leading-relaxed ${
          plain ? "bg-white ring-1 ring-stone-200" : "bg-white shadow-[0_8px_28px_-16px_rgb(27_23_20/0.35)] ring-1 ring-stone-200"} ${
          open && (m.kind === "question" || m.kind === "promotion" || m.kind === "handback" || m.kind === "draft") ? "ring-2 ring-brand-300" : ""}`}>
          <Body m={m} act={act} open={open} />
          {!open && m.kind !== "standup" && m.kind !== "ack" && m.kind !== "delivery" && <Answered m={m} />}
        </div>
        <p className="mt-1 pl-2 text-[11px] text-stone-400">{intern} · {time(m.at)}{m.urgency === "urgent" && " · urgent"}</p>
      </div>
    </div>
  );
}

export function Typing({ growth }: { growth: Growth }) {
  return (
    <div className="flex items-end gap-2.5" aria-live="polite" aria-label="Newt is typing">
      <InternAvatar mood="thinking" growth={growth} size={36} decorative animated={false} className="shrink-0" />
      <div className="flex gap-1 rounded-3xl rounded-bl-lg bg-white px-4 py-3.5 ring-1 ring-stone-200">
        {[0, 150, 300].map((d) => <span key={d} className="typing-dot h-2 w-2 rounded-full bg-stone-400" style={{ animationDelay: `${d}ms` }} />)}
      </div>
    </div>
  );
}
