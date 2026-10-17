"use client";

import { useState } from "react";
import type { Handbook, HandbookContent, Issue, Passage, Role, SectionKey } from "@/lib/api";

type AnyItem = { id: string; sources: string[] } & Record<string, unknown>;

interface Field {
  key: string;
  label: string;
  kind?: "text" | "long" | "lines" | "access";
}

const SECTIONS: { key: SectionKey; title: string; blurb: string; fields: Field[] }[] = [
  { key: "decision_rules", title: "Decision rules", blurb: "How to decide", fields: [{ key: "text", label: "Rule", kind: "long" }, { key: "applies_to", label: "Applies to" }] },
  { key: "always_escalate", title: "Always hand back", blurb: "Cases a person must handle", fields: [{ key: "text", label: "Case", kind: "long" }] },
  { key: "procedures", title: "Procedures", blurb: "Recurring workflows, step by step", fields: [{ key: "title", label: "Title" }, { key: "steps", label: "Steps (one per line)", kind: "lines" }] },
  { key: "access_scopes", title: "Access", blurb: "Least access that does the job", fields: [{ key: "system", label: "System" }, { key: "access", label: "Access", kind: "access" }, { key: "reason", label: "Why", kind: "long" }] },
  { key: "escalation_contacts", title: "Escalation contacts", blurb: "Who to hand back to", fields: [{ key: "contact", label: "Contact" }, { key: "when", label: "When", kind: "long" }] },
  { key: "glossary", title: "Glossary", blurb: "Team terms", fields: [{ key: "term", label: "Term" }, { key: "definition", label: "Definition", kind: "long" }] },
];

const STATUS_STYLE: Record<Handbook["status"], string> = {
  draft: "bg-amber-100 text-amber-900",
  approved: "bg-emerald-100 text-emerald-900",
  superseded: "bg-stone-200 text-stone-700",
};

function ItemBody({ section, item }: { section: SectionKey; item: AnyItem }) {
  switch (section) {
    case "procedures":
      return (
        <div>
          <div className="font-medium">{String(item.title)}</div>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5">
            {(item.steps as string[]).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      );
    case "glossary":
      return (
        <p>
          <span className="font-medium">{String(item.term)}</span>: {String(item.definition)}
        </p>
      );
    case "access_scopes":
      return (
        <p>
          <span className="font-medium">{String(item.system)}</span>{" "}
          <span className="rounded bg-stone-100 px-1.5 py-0.5 text-xs uppercase tracking-wide">{String(item.access)}</span>{" "}
          <span className="text-stone-600">{String(item.reason)}</span>
        </p>
      );
    case "escalation_contacts":
      return (
        <p>
          <span className="font-medium">{String(item.contact)}</span> <span className="text-stone-600">{String(item.when)}</span>
        </p>
      );
    case "decision_rules":
      return (
        <p>
          {String(item.text)}
          {typeof item.applies_to === "string" && item.applies_to && item.applies_to !== "all" && (
            <span className="ml-2 rounded bg-sky-50 px-1.5 py-0.5 text-xs text-sky-800">{String(item.applies_to)}</span>
          )}
        </p>
      );
    default:
      return <p>{String(item.text)}</p>;
  }
}

function SourceChips({
  sources,
  known,
  onShow,
}: {
  sources: string[];
  known: Map<string, Passage>;
  onShow: (label: string) => void;
}) {
  if (!sources.length) return <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700">No source</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {sources.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onShow(s)}
          title={known.get(s)?.document ?? "Missing source"}
          aria-label={`Source ${s}: ${known.get(s)?.document ?? "missing"}`}
          className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
            known.has(s) ? "bg-brand-50 text-brand-800 hover:bg-brand-100" : "bg-red-50 text-red-700"
          }`}
        >
          {s}
        </button>
      ))}
    </span>
  );
}

function ItemEditor({
  fields,
  item,
  onCancel,
  onSave,
}: {
  fields: Field[];
  item: AnyItem;
  onCancel: () => void;
  onSave: (item: AnyItem) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => ({
    ...Object.fromEntries(fields.map((f) => [f.key, f.kind === "lines" ? (item[f.key] as string[]).join("\n") : String(item[f.key] ?? "")])),
    sources: item.sources.join(", "),
  }));
  const set = (k: string, v: string) => setValues({ ...values, [k]: v });
  const input = "w-full rounded-md border border-stone-300 bg-white px-2 py-1 text-sm";

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        const next: AnyItem = { ...item, sources: values.sources.split(/[\s,]+/).filter(Boolean) };
        fields.forEach((f) => {
          next[f.key] = f.kind === "lines" ? values[f.key].split("\n").map((s) => s.trim()).filter(Boolean) : values[f.key].trim();
        });
        onSave(next);
      }}
    >
      {fields.map((f) => (
        <label key={f.key} className="block space-y-0.5">
          <span className="text-xs text-stone-500">{f.label}</span>
          {f.kind === "access" ? (
            <select value={values[f.key]} onChange={(e) => set(f.key, e.target.value)} className={input}>
              {["none", "read", "draft", "write"].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          ) : f.kind === "long" || f.kind === "lines" ? (
            <textarea value={values[f.key]} onChange={(e) => set(f.key, e.target.value)} rows={f.kind === "lines" ? 5 : 2} className={input} />
          ) : (
            <input value={values[f.key]} onChange={(e) => set(f.key, e.target.value)} className={input} />
          )}
        </label>
      ))}
      <label className="block space-y-0.5">
        <span className="text-xs text-stone-500">Sources (labels, comma-separated)</span>
        <input value={values.sources} onChange={(e) => set("sources", e.target.value)} className={`${input} font-mono`} />
      </label>
      <div className="flex gap-2">
        <button type="submit" className="rounded-md bg-stone-900 px-3 py-1 text-sm font-medium text-white">
          Save
        </button>
        <button type="button" onClick={onCancel} className="rounded-md px-3 py-1 text-sm text-stone-600 hover:bg-stone-100">
          Cancel
        </button>
      </div>
    </form>
  );
}

function blankItem(fields: Field[]): AnyItem {
  const item: AnyItem = { id: "", sources: [] };
  fields.forEach((f) => (item[f.key] = f.kind === "lines" ? [] : f.kind === "access" ? "read" : f.key === "applies_to" ? "all" : ""));
  return item;
}

export function HandbookView({
  versions,
  selectedId,
  onSelect,
  passages,
  role,
  hasSources,
  onDraft,
  onSave,
  onApprove,
  onRevise,
  onShowSource,
}: {
  versions: Handbook[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  passages: Map<string, Passage>;
  role: Role | undefined;
  hasSources: boolean;
  onDraft: () => Promise<void>;
  onSave: (content: HandbookContent) => Promise<void>;
  onApprove: () => Promise<void>;
  onRevise: () => Promise<void>;
  onShowSource: (label: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const handbook = versions.find((v) => v.id === selectedId) ?? versions[0];
  const canEdit = role === "mentor" || role === "manager" || role === "admin";

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  }

  const draftButton = canEdit && (
    <button
      type="button"
      disabled={!!busy || !hasSources}
      onClick={() => run("draft", onDraft)}
      className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-40"
      title={hasSources ? undefined : "Upload documents or answer the questionnaire first"}
    >
      {busy === "draft" ? "Drafting… (up to 2 minutes)" : versions.length ? "Draft a new version" : "Draft the handbook"}
    </button>
  );

  if (!handbook) {
    return (
      <div className="space-y-3 text-sm text-stone-600">
        <p>No handbook yet. Drafting reads every document passage and questionnaire answer, and cites them on every line.</p>
        {draftButton}
      </div>
    );
  }

  const content = handbook.content;
  const isDraft = handbook.status === "draft";
  const issues: Issue[] = handbook.meta.issues ?? [];
  const blocking = issues.filter((i) => i.problem === "no source");
  const issueIds = new Set(issues.map((i) => i.id));
  const meta = handbook.meta;
  const drafter =
    meta.provider === "anthropic"
      ? `Drafted by ${meta.model} in ${meta.duration_s?.toFixed(0)}s · $${meta.cost_usd?.toFixed(2)}`
      : meta.provider === "fake"
        ? "Drafted offline (keyword rules). Add an API key for a model-written draft."
        : meta.revised_from
          ? `Revision of version ${meta.revised_from}`
          : null;

  async function saveContent(next: HandbookContent) {
    await run("save", () => onSave(next));
    setEditing(null);
  }

  function updateItem(section: SectionKey, item: AnyItem) {
    const list = content[section] as unknown as AnyItem[];
    const exists = list.some((i) => i.id === item.id && item.id);
    const next = exists ? list.map((i) => (i.id === item.id ? item : i)) : [...list, item];
    return saveContent({ ...content, [section]: next });
  }

  function deleteItem(section: SectionKey, id: string) {
    const list = content[section] as unknown as AnyItem[];
    return saveContent({ ...content, [section]: list.filter((i) => i.id !== id) });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={handbook.id}
          onChange={(e) => onSelect(e.target.value)}
          className="rounded-md border border-stone-300 bg-white px-2 py-1.5 text-sm"
          aria-label="Handbook version"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              Version {v.version} · {v.status}
            </option>
          ))}
        </select>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[handbook.status]}`}>{handbook.status}</span>
        {handbook.approved_at && (
          <span className="text-sm text-stone-500">Approved {new Date(handbook.approved_at).toLocaleString()}</span>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          {isDraft && role === "manager" && (
            <button
              type="button"
              disabled={!!busy || blocking.length > 0}
              onClick={() => run("approve", onApprove)}
              className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-40"
              title={blocking.length ? "Every item needs a source before approval" : undefined}
            >
              {busy === "approve" ? "Approving…" : "Approve handbook"}
            </button>
          )}
          {!isDraft && canEdit && handbook.status === "approved" && (
            <button
              type="button"
              disabled={!!busy}
              onClick={() => run("revise", onRevise)}
              className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-stone-50"
            >
              Start a revision
            </button>
          )}
          {draftButton}
        </div>
      </div>

      {drafter && <p className="-mt-3 text-xs text-stone-500">{drafter}</p>}

      {isDraft && blocking.length > 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {blocking.length} item{blocking.length > 1 ? "s have" : " has"} no source. Cite a passage or delete{" "}
          {blocking.length > 1 ? "them" : "it"} before approval.
        </div>
      )}
      {isDraft && role !== "manager" && (
        <p className="text-sm text-stone-500">Edit anything below. The manager approves it when it&apos;s right.</p>
      )}

      <section className="rounded-lg border border-stone-200 bg-white p-4">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Purpose</h3>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="max-w-3xl">{content.purpose.text || <span className="text-stone-400">Not set</span>}</p>
          <SourceChips sources={content.purpose.sources} known={passages} onShow={onShowSource} />
        </div>
      </section>

      {SECTIONS.map((section) => {
        const items = content[section.key] as unknown as AnyItem[];
        return (
          <section key={section.key} className="rounded-lg border border-stone-200 bg-white">
            <header className="flex items-baseline justify-between gap-2 border-b border-stone-100 px-4 py-2.5">
              <h3 className="font-medium">
                {section.title} <span className="text-sm font-normal text-stone-500">· {section.blurb}</span>
              </h3>
              <span className="text-xs text-stone-500">{items.length}</span>
            </header>
            <ul className="divide-y divide-stone-100">
              {items.map((item) => {
                const key = `${section.key}:${item.id}`;
                return (
                  <li key={item.id} className={`px-4 py-2.5 text-sm ${issueIds.has(item.id) && isDraft ? "bg-red-50/40" : ""}`}>
                    {editing === key ? (
                      <ItemEditor fields={section.fields} item={item} onCancel={() => setEditing(null)} onSave={(it) => updateItem(section.key, it)} />
                    ) : (
                      <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
                        <span className="w-7 shrink-0 font-mono text-[11px] leading-5 text-stone-400">{item.id}</span>
                        <div className="min-w-0 flex-1">
                          <ItemBody section={section.key} item={item} />
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <SourceChips sources={item.sources} known={passages} onShow={onShowSource} />
                          {isDraft && canEdit && (
                            <>
                              <button type="button" onClick={() => setEditing(key)} className="text-xs text-stone-500 hover:text-stone-900">
                                Edit
                              </button>
                              <button
                                type="button"
                                disabled={!!busy}
                                onClick={() => deleteItem(section.key, item.id)}
                                className="text-xs text-stone-400 hover:text-red-700"
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
              {editing === `${section.key}:new` && (
                <li className="px-4 py-2.5">
                  <ItemEditor fields={section.fields} item={blankItem(section.fields)} onCancel={() => setEditing(null)} onSave={(it) => updateItem(section.key, it)} />
                </li>
              )}
            </ul>
            {isDraft && canEdit && editing !== `${section.key}:new` && (
              <button
                type="button"
                onClick={() => setEditing(`${section.key}:new`)}
                className="w-full border-t border-stone-100 px-4 py-2 text-left text-sm text-stone-500 hover:bg-stone-50"
              >
                + Add
              </button>
            )}
          </section>
        );
      })}

      {content.open_questions.length > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="mb-2 font-medium">Open questions for the mentor</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {content.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
