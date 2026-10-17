"use client";

import { useEffect, useState } from "react";
import type { Attribution, TeachingCard as Card } from "@/lib/api";

const label = (s: unknown) => (s === null || s === undefined || s === "" ? "–" : String(s).replace(/_/g, " "));

const KIND: Record<Card["kind"], { text: string; style: string }> = {
  disagreement: { text: "You differed", style: "bg-red-100 text-red-800" },
  unsure: { text: "Intern was unsure", style: "bg-amber-100 text-amber-900" },
  spot_check: { text: "Spot check", style: "bg-sky-100 text-sky-900" },
};

export const BUTTONS: { key: Attribution; label: string; hint: string; shortcut: string }[] = [
  { key: "intern_wrong", label: "Intern wrong", hint: "Counts as its mistake and becomes a lesson", shortcut: "1" },
  { key: "both_fine", label: "Both fine", hint: "Its answer works too", shortcut: "2" },
  { key: "mentor_changed", label: "I'd change my call", hint: "My decision was off; don't count it", shortcut: "3" },
  { key: "couldnt_know", label: "Intern couldn't have known", hint: "Something it can't see decided this", shortcut: "4" },
];

function Answer({ title, decision, fields, texts, mismatched, highlight }: {
  title: string;
  decision: string | null | undefined;
  fields: Record<string, unknown>;
  texts: Record<string, string>;
  mismatched: Set<string>;
  highlight: boolean;
}) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">{title}</h4>
      <p className={`inline-block rounded px-2 py-0.5 text-sm font-medium ${highlight ? "bg-red-50 text-red-800" : "bg-stone-100"}`}>
        {label(decision)}
      </p>
      {Object.keys(fields).length > 0 && (
        <dl className="space-y-0.5 text-sm">
          {Object.entries(fields).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <dt className="text-stone-500">{label(k)}</dt>
              <dd className={mismatched.has(k) ? "font-medium text-red-700" : ""}>{label(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {Object.entries(texts).map(([k, v]) => (
        <div key={k} className="text-sm">
          <p className="text-xs text-stone-500">{label(k)}</p>
          <p className="whitespace-pre-wrap rounded-md bg-stone-50 p-2">{v}</p>
        </div>
      ))}
    </div>
  );
}

export function TeachingCard({ card, busy, onTeach }: {
  card: Card;
  busy: boolean;
  onTeach: (a: { attribution: Attribution; note: string; reply_ok: boolean | null; rule_text: string }) => void;
}) {
  const [note, setNote] = useState("");
  const [replyOk, setReplyOk] = useState<boolean | null>(null);
  const [makeRule, setMakeRule] = useState(false);
  const [rule, setRule] = useState("");
  const [why, setWhy] = useState(false);

  useEffect(() => {
    setNote("");
    setReplyOk(null);
    setMakeRule(false);
    setWhy(false);
    setRule(`When an item mentions "", choose ${label(card.mentor.decision)}.`);
  }, [card.prediction_id, card.mentor.decision]);

  const teach = (attribution: Attribution) => {
    if (!busy) onTeach({ attribution, note, reply_ok: replyOk, rule_text: makeRule ? rule : "" });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") return;
      const b = BUTTONS.find((x) => x.shortcut === e.key);
      if (b) teach(b.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const mismatched = new Set(Object.entries(card.comparison.field_scores).filter(([, s]) => !s.match).map(([k]) => k));
  const tj = card.comparison.text_judgement;
  const judged = tj.status === "judged";
  const kind = KIND[card.kind];

  return (
    <article className="space-y-5 rounded-lg border border-stone-200 bg-white p-5">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${kind.style}`}>{kind.text}</span>
          <span className="text-xs text-stone-500">{new Date(card.case.received_at).toLocaleString()}</span>
          {card.confidence !== null && <span className="text-xs text-stone-500">· intern {Math.round(card.confidence * 100)}% sure</span>}
        </div>
        <h3 className="font-medium">{card.case.subject || "(no subject)"}</h3>
        {Object.entries(card.case.inputs).filter(([, v]) => v).map(([k, v]) => (
          <p key={k} className="whitespace-pre-wrap text-sm text-stone-700">
            <span className="text-xs text-stone-500">{label(k)}: </span>
            {v}
          </p>
        ))}
      </header>

      <div className="grid gap-5 border-t border-stone-100 pt-4 sm:grid-cols-2">
        <Answer title="What you did" decision={card.mentor.decision} fields={card.mentor.fields} texts={card.mentor.text_outputs}
                mismatched={new Set()} highlight={false} />
        <div className="space-y-2">
          <Answer title="What the intern would have done" decision={card.agent.decision} fields={card.agent.fields ?? {}}
                  texts={card.agent.text_outputs ?? {}} mismatched={mismatched} highlight={!card.comparison.decision_match} />
          {judged && (
            <div className="space-y-1 text-sm">
              <p className="text-xs text-stone-500">
                Reply judge ({tj.judge}): {tj.acceptable ? "would send unchanged" : "needs changes"}
              </p>
              <p className="flex items-center gap-2">
                <span>Would you send the intern&apos;s reply?</span>
                {[true, false].map((v) => (
                  <button key={String(v)} type="button" onClick={() => setReplyOk(replyOk === v ? null : v)}
                          className={`rounded px-2 py-0.5 text-xs ${replyOk === v ? "bg-stone-900 text-white" : "bg-stone-100"}`}>
                    {v ? "Yes" : "No"}
                  </button>
                ))}
              </p>
            </div>
          )}
          {card.agent.rationale && (
            <details className="text-sm text-stone-600">
              <summary className="cursor-pointer text-xs text-stone-500">Why the intern chose this</summary>
              <p className="mt-1">{card.agent.rationale}</p>
              {(card.agent.missing_info ?? []).length > 0 && <p className="mt-1 text-xs">Missing: {card.agent.missing_info!.join("; ")}</p>}
            </details>
          )}
        </div>
      </div>

      <div className="space-y-3 border-t border-stone-100 pt-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {BUTTONS.map((b) => (
            <button key={b.key} type="button" disabled={busy} onClick={() => teach(b.key)} title={b.hint}
                    className="rounded-md border border-stone-300 bg-white px-2 py-2 text-sm font-medium hover:border-stone-900 disabled:opacity-40">
              {b.label}
              <span className="ml-1 text-xs font-normal text-stone-400">{b.shortcut}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <button type="button" onClick={() => setWhy(!why)} className="text-stone-600 hover:text-stone-900">
            {why ? "− Why (optional)" : "+ Why (optional)"}
          </button>
          <label className="flex items-center gap-1.5 text-stone-600">
            <input type="checkbox" checked={makeRule} onChange={(e) => setMakeRule(e.target.checked)} />
            Make this a rule
          </label>
        </div>
        {why && (
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="A sentence is plenty."
                    className="w-full rounded-md border border-stone-300 px-2.5 py-1.5 text-sm" />
        )}
        {makeRule && (
          <div className="space-y-1">
            <textarea value={rule} onChange={(e) => setRule(e.target.value)} rows={2}
                      className="w-full rounded-md border border-stone-300 px-2.5 py-1.5 text-sm" />
            <p className="text-xs text-stone-500">
              Plain English. Name the decision, and quote the words that trigger it. It applies to future cases, never to this one.
            </p>
          </div>
        )}
      </div>
    </article>
  );
}
