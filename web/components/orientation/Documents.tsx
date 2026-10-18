"use client";

import { useRef, useState } from "react";
import type { SourceDoc, UploadResult } from "@/lib/api";

const ACCEPT = ".pdf,.docx,.txt,.md";

export function Documents({
  docs,
  canEdit,
  onUpload,
  onDelete,
}: {
  docs: SourceDoc[];
  canEdit: boolean;
  onUpload: (files: File[]) => Promise<UploadResult[]>;
  onDelete: (doc: SourceDoc) => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);

  async function upload(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    try {
      setResults(await onUpload(files));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  const problems = results.filter((r) => r.error || r.duplicate);

  return (
    <div className="space-y-3">
      {canEdit && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            upload(Array.from(e.dataTransfer.files));
          }}
          className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm ${
            dragging ? "border-brand-500 bg-brand-50" : "border-stone-300 bg-stone-50"
          }`}
        >
          <p className="text-stone-600">
            {busy ? "Reading documents…" : "Drop policies, procedures and guides here"}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => input.current?.click()}
            className="rounded-full border border-stone-300 bg-white px-4 py-1.5 font-medium hover:bg-stone-50 disabled:opacity-50"
          >
            Choose files
          </button>
          <p className="text-xs text-stone-500">PDF, Word (.docx), .txt or .md · up to 20 MB each</p>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => upload(Array.from(e.target.files ?? []))}
          />
        </div>
      )}

      {problems.length > 0 && (
        <ul className="space-y-1 text-sm">
          {problems.map((r, i) => (
            <li key={i} className={r.error ? "text-red-700" : "text-stone-500"}>
              {r.filename}: {r.error ?? "already uploaded"}
            </li>
          ))}
        </ul>
      )}

      {docs.length === 0 ? (
        <p className="text-sm text-stone-500">No documents yet.</p>
      ) : (
        <ul className="divide-y divide-stone-100 rounded-3xl border border-stone-200 bg-white">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="w-6 shrink-0 text-right font-mono text-xs text-stone-500">{d.doc_index}</span>
              <span className="min-w-0 flex-1 truncate" title={d.filename}>
                {d.filename}
              </span>
              <span className="shrink-0 text-xs text-stone-500">
                {d.passages} passage{d.passages === 1 ? "" : "s"}
              </span>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => {
                    if (confirm(`Remove ${d.filename}? Handbook items citing it will need a new source.`)) onDelete(d);
                  }}
                  className="shrink-0 text-xs text-stone-400 hover:text-red-700"
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
