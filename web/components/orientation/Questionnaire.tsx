"use client";

import { useEffect, useMemo, useState } from "react";
import type { Question } from "@/lib/api";

export function Questionnaire({
  questions,
  canEdit,
  onSave,
}: {
  questions: Question[];
  canEdit: boolean;
  onSave: (answers: Record<string, string>) => Promise<void>;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  useEffect(() => {
    setAnswers(Object.fromEntries(questions.map((q) => [q.key, q.answer])));
  }, [questions]);

  const groups = useMemo(() => {
    const map = new Map<string, Question[]>();
    questions.forEach((q) => map.set(q.group, [...(map.get(q.group) ?? []), q]));
    return [...map.entries()];
  }, [questions]);

  const dirty = questions.some((q) => (answers[q.key] ?? "") !== q.answer);
  const answered = questions.filter((q) => q.answer.trim()).length;

  async function save() {
    setSaving(true);
    try {
      await onSave(answers);
      setSavedAt(new Date());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        {answered} of {questions.length} answered.{" "}
        {canEdit ? "Short answers are fine; each one becomes a source the handbook can cite." : "Only the mentor answers these."}
      </p>
      {groups.map(([group, qs]) => (
        <fieldset key={group} className="space-y-3">
          <legend className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">{group}</legend>
          {qs.map((q) => (
            <label key={q.key} className="block space-y-1">
              <span className="flex items-baseline justify-between gap-2 text-sm">
                <span>{q.question}</span>
                <span className="shrink-0 font-mono text-[11px] text-stone-400">{q.label}</span>
              </span>
              <textarea
                value={answers[q.key] ?? ""}
                readOnly={!canEdit}
                onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })}
                rows={2}
                className="w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm read-only:bg-stone-50 read-only:text-stone-600"
              />
            </label>
          ))}
        </fieldset>
      ))}
      {canEdit && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={!dirty || saving}
            onClick={save}
            className="rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save answers"}
          </button>
          {savedAt && !dirty && <span className="text-sm text-stone-500">Saved</span>}
        </div>
      )}
    </div>
  );
}
