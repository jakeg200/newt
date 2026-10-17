"use client";

import { useState } from "react";
import type { NewConnection, Provider, TaskTypeInfo } from "@/lib/api";

const PROVIDERS: { value: Provider; label: string; help: string }[] = [
  { value: "email_upload", label: "Email export (.eml / .mbox)", help: "Upload past emails. Good for a first backtest." },
  { value: "gmail", label: "Gmail (read-only, one label)", help: "Reads only threads under one label, including the mentor's replies." },
  { value: "csv", label: "CSV or JSON export", help: "Rows from a ledger, ticket system or spreadsheet, with the decision made." },
  { value: "rest", label: "REST push", help: "Another system sends items and decisions to an endpoint with a token." },
];

function columnTemplate(tt: TaskTypeInfo) {
  return JSON.stringify(
    {
      item_ref: "id",
      received_at: "received_at",
      subject: "title",
      inputs: Object.fromEntries(tt.inputs.map((i) => [i, i])),
      decision: "outcome",
      decision_map: Object.fromEntries(tt.decision.map((d) => [d, d])),
      acted_at: "decided_at",
    },
    null,
    2,
  );
}

export function NewConnectionForm({
  taskType,
  onCreate,
  onCancel,
}: {
  taskType: TaskTypeInfo;
  onCreate: (body: NewConnection) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [provider, setProvider] = useState<Provider>("email_upload");
  const [name, setName] = useState("");
  const [addresses, setAddresses] = useState("");
  const [bodyInput, setBodyInput] = useState(taskType.inputs[0] ?? "");
  const [label, setLabel] = useState("");
  const [columns, setColumns] = useState(columnTemplate(taskType));
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isEmail = provider === "email_upload" || provider === "gmail";
  const input = "w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const body: NewConnection = { name: name.trim(), provider, task_type_id: taskType.id };
    if (isEmail) {
      body.mentor_addresses = addresses.split(/[\s,;]+/).filter(Boolean);
      body.body_input = bodyInput;
      body.consent = consent;
    }
    if (provider === "gmail") body.label = label.trim();
    if (provider === "csv") {
      try {
        body.columns = JSON.parse(columns);
      } catch {
        setError("The column map isn't valid JSON.");
        return;
      }
    }
    setBusy(true);
    try {
      if (await onCreate(body)) onCancel();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-stone-200 bg-white p-4">
      <fieldset className="space-y-1.5">
        <legend className="mb-1 text-sm font-medium">Source</legend>
        {PROVIDERS.map((p) => (
          <label key={p.value} className="flex items-start gap-2 text-sm">
            <input type="radio" name="provider" checked={provider === p.value} onChange={() => setProvider(p.value)} className="mt-1" />
            <span>
              {p.label}
              <span className="block text-xs text-stone-500">{p.help}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="block space-y-1 text-sm">
        <span>Name</span>
        <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Sarah's AP inbox" className={input} />
      </label>

      {isEmail && (
        <>
          <label className="block space-y-1 text-sm">
            <span>Mentor&apos;s email address(es)</span>
            <input required value={addresses} onChange={(e) => setAddresses(e.target.value)} placeholder="sarah@company.com" className={input} />
            <span className="block text-xs text-stone-500">Their messages count as actions; everything else is an item.</span>
          </label>
          <label className="block space-y-1 text-sm">
            <span>Email body fills</span>
            <select value={bodyInput} onChange={(e) => setBodyInput(e.target.value)} className={input}>
              {taskType.inputs.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </select>
          </label>
        </>
      )}
      {provider === "gmail" && (
        <label className="block space-y-1 text-sm">
          <span>Gmail label</span>
          <input required value={label} onChange={(e) => setLabel(e.target.value)} placeholder="AP/Mismatch" className={input} />
          <span className="block text-xs text-stone-500">Nothing outside this label is read.</span>
        </label>
      )}
      {provider === "csv" && (
        <label className="block space-y-1 text-sm">
          <span>Column map</span>
          <textarea value={columns} onChange={(e) => setColumns(e.target.value)} rows={12} className={`${input} font-mono text-xs`} />
          <span className="block text-xs text-stone-500">Values are your file&apos;s column names. Use dots for nested JSON.</span>
        </label>
      )}
      {isEmail && (
        <label className="flex items-start gap-2 rounded-md bg-stone-50 p-2.5 text-sm">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
          <span>
            I&apos;m the mentor and I agree to this capture. Personal details are redacted before anything is stored, I can
            pause it at any time, and deleting the connection deletes every case it captured.
          </span>
        </label>
      )}

      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
          {busy ? "Creating…" : "Create connection"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-md px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100">
          Cancel
        </button>
      </div>
    </form>
  );
}
