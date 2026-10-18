"use client";

import { useRef, useState } from "react";
import type { ConnectionInfo, Unmatched } from "@/lib/api";
import { RunReport } from "./RunReport";

const PROVIDER_LABEL: Record<ConnectionInfo["provider"], string> = {
  email_upload: "Email export",
  gmail: "Gmail",
  csv: "CSV / JSON",
  rest: "REST push",
};

const STATUS_STYLE = {
  active: "bg-emerald-100 text-emerald-900",
  pending: "bg-amber-100 text-amber-900",
  paused: "bg-stone-200 text-stone-700",
};

export function ConnectionCard({
  connection,
  unmatched,
  canEdit,
  onImport,
  onSync,
  onSignIn,
  onToggle,
  onDelete,
}: {
  connection: ConnectionInfo;
  unmatched?: Unmatched[];
  canEdit: boolean;
  onImport: (files: File[]) => Promise<void>;
  onSync: () => Promise<void>;
  onSignIn: () => Promise<void>;
  onToggle: () => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const c = connection;
  const accepts = c.provider === "email_upload" ? ".eml,.mbox" : c.provider === "csv" ? ".csv,.json" : null;

  async function run(what: string, fn: () => Promise<void>) {
    setBusy(what);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  }

  const button = "rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs font-medium hover:bg-stone-50 disabled:opacity-40";

  return (
    <article className="space-y-3 rounded-3xl border border-stone-200 bg-white p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{c.name}</h3>
          <p className="text-xs text-stone-500">
            {PROVIDER_LABEL[c.provider]}
            {c.filter.label && ` · label "${c.filter.label}"`}
            {c.mentor_addresses.length > 0 && ` · mentor ${c.mentor_addresses.join(", ")}`}
          </p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[c.status]}`}>{c.status}</span>
      </header>

      <p className="text-sm text-stone-600">
        <span className="font-medium tabular-nums text-stone-900">{c.cases}</span> cases,{" "}
        <span className="tabular-nums">{c.decided}</span> with the mentor&apos;s decision
      </p>

      {c.push_token && (
        <div className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs">
          <p className="font-medium">Copy this token now. It won&apos;t be shown again.</p>
          <p>
            POST to <code className="break-all">{c.push_url}</code> with{" "}
            <code className="break-all">Authorization: Bearer {c.push_token}</code>
          </p>
        </div>
      )}

      {c.last_run ? (
        <div className="border-t border-stone-100 pt-3">
          <p className="mb-2 text-xs text-stone-500">Last run {new Date(c.last_run.started_at).toLocaleString()}</p>
          <RunReport stats={c.last_run.stats} unmatched={unmatched} />
        </div>
      ) : (
        c.provider !== "rest" && c.status === "active" && <p className="text-sm text-stone-500">Nothing captured yet.</p>
      )}

      {canEdit && (
        <div className="flex flex-wrap gap-2 border-t border-stone-100 pt-3">
          {accepts && c.status === "active" && (
            <>
              <button type="button" disabled={!!busy} onClick={() => input.current?.click()} className={button}>
                {busy === "import" ? "Importing…" : "Import files"}
              </button>
              <input
                ref={input}
                type="file"
                multiple
                accept={accepts}
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length) run("import", () => onImport(files));
                  e.target.value = "";
                }}
              />
            </>
          )}
          {c.provider === "gmail" && c.status === "pending" && (
            <button type="button" disabled={!!busy} onClick={() => run("signin", onSignIn)} className={button}>
              Sign in with Google
            </button>
          )}
          {c.provider === "gmail" && c.status === "active" && (
            <button type="button" disabled={!!busy} onClick={() => run("sync", onSync)} className={button}>
              {busy === "sync" ? "Syncing…" : "Sync now"}
            </button>
          )}
          {c.status !== "pending" && (
            <button type="button" disabled={!!busy} onClick={() => run("toggle", onToggle)} className={button}>
              {c.status === "paused" ? "Resume" : "Pause"}
            </button>
          )}
          <button
            type="button"
            disabled={!!busy}
            onClick={() => {
              if (confirm(`Delete "${c.name}" and all ${c.cases} cases it captured? This can't be undone.`)) run("delete", onDelete);
            }}
            className="ml-auto rounded-md px-2.5 py-1 text-xs text-stone-500 hover:text-red-700"
          >
            Delete
          </button>
        </div>
      )}
    </article>
  );
}
