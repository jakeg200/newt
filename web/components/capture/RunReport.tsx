import type { RunStats, Unmatched } from "@/lib/api";

const METHODS: { key: string; label: string }[] = [
  { key: "matched_explicit", label: "named the item" },
  { key: "matched_reply_header", label: "reply headers" },
  { key: "matched_thread", label: "same thread" },
  { key: "matched_reference", label: "reference number" },
];

export function RunReport({ stats, unmatched }: { stats: RunStats; unmatched?: Unmatched[] }) {
  const considered = stats.actions_matched - stats.earlier_actions_matched + stats.actions_unmatched;
  const methods = METHODS.filter((m) => (stats[m.key as `matched_${string}`] ?? 0) > 0);
  const redacted = Object.entries(stats.redactions ?? {});

  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-stone-500">New cases</dt>
          <dd className="text-lg font-semibold tabular-nums">{stats.cases_created}</dd>
          {stats.duplicate_items > 0 && <dd className="text-xs text-stone-500">{stats.duplicate_items} already captured</dd>}
        </div>
        <div>
          <dt className="text-xs text-stone-500">Actions matched</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {considered === 0 ? (
              <span className="text-stone-400">–</span>
            ) : (
              <>
                {stats.actions_matched - stats.earlier_actions_matched}
                <span className="text-sm font-normal text-stone-500"> of {considered}</span>
              </>
            )}
          </dd>
          {stats.match_rate !== null && <dd className="text-xs text-stone-500">{Math.round(stats.match_rate * 100)}%</dd>}
        </div>
        <div>
          <dt className="text-xs text-stone-500">Earlier actions matched</dt>
          <dd className="text-lg font-semibold tabular-nums">{stats.earlier_actions_matched}</dd>
        </div>
        <div>
          <dt className="text-xs text-stone-500">Problems</dt>
          <dd className={`text-lg font-semibold tabular-nums ${stats.error_count ? "text-red-700" : ""}`}>{stats.error_count}</dd>
        </div>
      </dl>

      {methods.length > 0 && (
        <p className="text-xs text-stone-600">
          Matched by{" "}
          {methods.map((m, i) => (
            <span key={m.key}>
              {i > 0 && ", "}
              {m.label} <span className="tabular-nums">({stats[m.key as `matched_${string}`]})</span>
            </span>
          ))}
          {stats.actions_without_decision > 0 && `. ${stats.actions_without_decision} matched with no decision rule.`}
        </p>
      )}
      {redacted.length > 0 && (
        <p className="text-xs text-stone-600">
          Redacted before storage: {redacted.map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ")}.
        </p>
      )}
      {stats.errors.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-red-700">Show problems</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-stone-700">
            {stats.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}
      {unmatched && unmatched.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-stone-700">{unmatched.length} unmatched action(s) waiting</summary>
          <ul className="mt-1 space-y-1">
            {unmatched.map((u) => (
              <li key={u.id} className="rounded bg-stone-50 px-2 py-1">
                <span className="font-medium">{u.summary.subject || "(no subject)"}</span>{" "}
                <span className="text-stone-500">· {new Date(u.acted_at).toLocaleString()} · {u.reason}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-stone-500">These are retried automatically when new items arrive.</p>
        </details>
      )}
    </div>
  );
}
