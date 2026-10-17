"use client";

import { useEffect } from "react";
import type { CaseDetail } from "@/lib/api";

const METHOD_LABEL: Record<string, string> = {
  explicit: "named the item",
  reply_header: "reply headers",
  thread: "same thread",
  reference: "reference number",
};

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1">
      <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">{title}</h3>
      {children}
    </section>
  );
}

export function CaseDrawer({ detail, onClose }: { detail: CaseDetail | null; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/20" onClick={onClose}>
      <aside
        role="dialog"
        aria-label="Case"
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-xl space-y-5 overflow-y-auto bg-white p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-stone-500">{detail ? new Date(detail.received_at).toLocaleString() : "Loading…"}</p>
            <h2 className="font-medium">{detail?.snapshot.subject || "(no subject)"}</h2>
            {detail && (
              <p className="text-xs text-stone-500">
                From {detail.snapshot.from ?? "unknown"} · {detail.is_backtest ? "history (backtest)" : "live"}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-sm text-stone-500 hover:bg-stone-100">
            Close
          </button>
        </div>

        {detail && (
          <>
            <p className="rounded-md bg-stone-50 px-3 py-2 text-xs text-stone-600">
              Personal details are replaced with stable tags like [EMAIL 3fa9c1] before storage. The same person always gets the
              same tag.
            </p>
            {Object.entries(detail.snapshot.inputs).map(([name, text]) => (
              <Block key={name} title={name.replace(/_/g, " ")}>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{text || <span className="text-stone-400">Empty</span>}</p>
              </Block>
            ))}
            {detail.snapshot.history.length > 0 && (
              <Block title="Earlier in the thread">
                {detail.snapshot.history.map((h, i) => (
                  <p key={i} className="whitespace-pre-wrap border-l-2 border-stone-200 pl-2 text-sm text-stone-600">
                    <span className="text-xs text-stone-500">{new Date(h.at).toLocaleString()} · {h.from}</span>
                    <br />
                    {h.text}
                  </p>
                ))}
              </Block>
            )}
            <Block title="What the mentor did">
              {detail.actions.length === 0 && <p className="text-sm text-stone-500">Nothing captured yet.</p>}
              {detail.actions.map((a) => (
                <div key={a.id} className="space-y-1 rounded-md border border-stone-200 p-3 text-sm">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium capitalize">{a.type}</span>
                    {a.payload.decision ? (
                      <span className="rounded bg-teal-50 px-1.5 py-0.5 text-xs text-teal-800">{a.payload.decision.replace(/_/g, " ")}</span>
                    ) : (
                      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">no decision rule matched</span>
                    )}
                    <span className="text-xs text-stone-500">
                      {new Date(a.acted_at).toLocaleString()}
                      {a.match_method && ` · matched by ${METHOD_LABEL[a.match_method] ?? a.match_method}`}
                    </span>
                  </p>
                  {a.payload.recipients && <p className="text-xs text-stone-500">To {a.payload.recipients.join(", ")}</p>}
                  {Object.entries(a.payload.text_outputs ?? {}).map(([k, v]) => (
                    <p key={k} className="whitespace-pre-wrap text-stone-700">
                      <span className="text-xs text-stone-500">{k.replace(/_/g, " ")}: </span>
                      {v}
                    </p>
                  ))}
                  {a.payload.note && <p className="whitespace-pre-wrap text-stone-700">{a.payload.note}</p>}
                  {a.payload.fields && Object.keys(a.payload.fields).length > 0 && (
                    <p className="text-xs text-stone-600">
                      {Object.entries(a.payload.fields)
                        .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
                        .join(" · ")}
                    </p>
                  )}
                </div>
              ))}
            </Block>
          </>
        )}
      </aside>
    </div>
  );
}
