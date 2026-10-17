"use client";

import { useEffect } from "react";
import type { Passage } from "@/lib/api";

export function SourcePanel({ passage, label, onClose }: { passage?: Passage; label: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/20" onClick={onClose}>
      <aside
        role="dialog"
        aria-label={`Source ${label}`}
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-xs text-stone-500">Source {label}</div>
            <div className="font-medium">{passage?.document ?? "Missing source"}</div>
            {passage?.page && <div className="text-sm text-stone-500">Page {passage.page}</div>}
          </div>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-sm text-stone-500 hover:bg-stone-100">
            Close
          </button>
        </div>
        {passage ? (
          <p className="whitespace-pre-wrap rounded-md bg-stone-50 p-3 text-sm leading-relaxed">{passage.text}</p>
        ) : (
          <p className="text-sm text-red-700">
            This label doesn&apos;t match any current passage. The document may have been removed.
          </p>
        )}
      </aside>
    </div>
  );
}
