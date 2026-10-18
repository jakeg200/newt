"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CaseDrawer } from "@/components/capture/CaseDrawer";
import { ConnectionCard } from "@/components/capture/ConnectionCard";
import { NewConnectionForm } from "@/components/capture/NewConnectionForm";
import { api, ApiError, type CaseDetail, type CaseSummary, type ConnectionInfo, type TaskTypeInfo, type Unmatched } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

const PAGE = 25;

function CapturePage() {
  const { user } = useUser();
  const params = useSearchParams();
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskTypeId, setTaskTypeId] = useState<string | null>(null);
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [unmatched, setUnmatched] = useState<Record<string, Unmatched[]>>({});
  const [cases, setCases] = useState<{ total: number; items: CaseSummary[] }>({ total: 0, items: [] });
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const [newToken, setNewToken] = useState<ConnectionInfo | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(
    params.get("gmail") === "connected" ? "Gmail connected. Run a sync to capture the labelled threads." :
    params.get("gmail") === "failed" ? "Google sign-in didn't complete. Try again." : null,
  );

  const canCapture = user?.role === "mentor" || user?.role === "admin";
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    if (!user) return;
    api
      .taskTypes()
      .then((list) => {
        setTaskTypes(list);
        setTaskTypeId((id) => (id && list.some((t) => t.id === id) ? id : (list[0]?.id ?? null)));
      })
      .catch(fail);
  }, [user]);

  const load = useCallback(
    async (ttId: string, page = 0) => {
      const conns = await api.connections(ttId);
      setConnections(conns);
      if (canCapture) {
        const lists = await Promise.all(conns.map((c) => api.unmatched(c.id).then((u) => [c.id, u] as const)));
        setUnmatched(Object.fromEntries(lists));
        setCases(await api.cases(ttId, page, PAGE));
      } else {
        setCases({ total: 0, items: [] });
      }
    },
    [canCapture],
  );

  useEffect(() => {
    if (!taskTypeId || !user) return;
    setError(null);
    setOffset(0);
    load(taskTypeId).catch(fail);
  }, [taskTypeId, user, load]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      if (taskTypeId) await load(taskTypeId, offset);
    } catch (e) {
      fail(e);
    }
  }

  async function openCase(id: string) {
    setOpen(true);
    setDetail(null);
    try {
      setDetail(await api.caseDetail(id));
    } catch (e) {
      setOpen(false);
      fail(e);
    }
  }

  const taskType = taskTypes.find((t) => t.id === taskTypeId);
  if (!user || !taskType) return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-4"><InternAvatar mood="learning" growth="larva" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">Capture</h1></div>
          <p className="max-w-2xl text-sm text-stone-600">
            Where the work comes from. Each item becomes a case, and what the mentor actually did is matched back to it.
            That pairing is what the agent is scored against. Personal details are redacted before anything is stored.
          </p>
        </div>
        {taskTypes.length > 1 && (
          <div className="flex gap-1 rounded-lg bg-stone-200/60 p-1 text-sm" role="tablist" aria-label="Task type">
            {taskTypes.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={t.id === taskTypeId}
                onClick={() => setTaskTypeId(t.id)}
                className={`rounded-md px-3 py-1 ${t.id === taskTypeId ? "bg-white font-medium shadow-sm" : "text-stone-600"}`}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {notice && (
        <div className="flex justify-between gap-3 rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-900">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>Dismiss</button>
        </div>
      )}
      {error && (
        <div className="flex justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Connections</h2>
            {canCapture && !adding && (
              <button type="button" onClick={() => setAdding(true)} className="rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-white">
                Add connection
              </button>
            )}
          </div>
          {adding && (
            <NewConnectionForm
              taskType={taskType}
              onCancel={() => setAdding(false)}
              onCreate={async (body) => {
                setError(null);
                try {
                  const created = await api.createConnection(body);
                  if (created.push_token) setNewToken(created);
                  await load(taskType.id, offset);
                  return true;
                } catch (e) {
                  fail(e);
                  return false;
                }
              }}
            />
          )}
          {connections.length === 0 && !adding && (
            <p className="text-sm text-stone-500">
              No connections yet.{" "}
              {canCapture ? "Start with an email export or a CSV of past decisions for a backtest." : "The mentor sets these up."}
            </p>
          )}
          {connections.map((c) => (
            <ConnectionCard
              key={c.id}
              connection={newToken?.id === c.id ? { ...c, push_token: newToken.push_token, push_url: newToken.push_url } : c}
              unmatched={unmatched[c.id]}
              canEdit={canCapture}
              onImport={(files) => act(() => api.importFiles(c.id, files))}
              onSync={() => act(() => api.sync(c.id))}
              onSignIn={async () => {
                try {
                  window.location.href = (await api.oauthStart(c.id)).url;
                } catch (e) {
                  fail(e);
                }
              }}
              onToggle={() => act(() => api.updateConnection(c.id, { status: c.status === "paused" ? "active" : "paused" }))}
              onDelete={() => act(() => api.deleteConnection(c.id))}
            />
          ))}
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="font-medium">Cases</h2>
            {canCapture && <span className="text-sm text-stone-500 tabular-nums">{cases.total}</span>}
          </div>
          {!canCapture ? (
            <p className="text-sm text-stone-500">Cases come from the mentor&apos;s work, so only the mentor sees them here.</p>
          ) : cases.items.length === 0 ? (
            <p className="text-sm text-stone-500">No cases yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-3xl border border-stone-200 bg-white">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-stone-200 text-xs text-stone-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Received</th>
                    <th className="px-3 py-2 font-medium">Item</th>
                    <th className="px-3 py-2 font-medium">Mentor&apos;s decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {cases.items.map((c) => (
                    <tr key={c.id} onClick={() => openCase(c.id)} className="cursor-pointer hover:bg-stone-50">
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-stone-600">
                        {new Date(c.received_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}{" "}
                        {new Date(c.received_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="max-w-[18rem] truncate px-3 py-2">
                        <button type="button" className="truncate text-left hover:underline" onClick={(e) => { e.stopPropagation(); openCase(c.id); }}>
                          {c.subject || c.source_ref}
                        </button>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {c.decision ? (
                          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-800">{c.decision.replace(/_/g, " ")}</span>
                        ) : (
                          <span className="text-xs text-stone-400">waiting</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {cases.total > PAGE && (
                <div className="flex items-center justify-between border-t border-stone-100 px-3 py-2 text-xs text-stone-500">
                  <span className="tabular-nums">
                    {offset + 1}–{Math.min(offset + PAGE, cases.total)} of {cases.total}
                  </span>
                  <span className="flex gap-2">
                    <button type="button" disabled={offset === 0} onClick={() => { const o = offset - PAGE; setOffset(o); act(() => load(taskType.id, o)); }} className="disabled:opacity-30">
                      Previous
                    </button>
                    <button type="button" disabled={offset + PAGE >= cases.total} onClick={() => { const o = offset + PAGE; setOffset(o); act(() => load(taskType.id, o)); }} className="disabled:opacity-30">
                      Next
                    </button>
                  </span>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {open && <CaseDrawer detail={detail} onClose={() => setOpen(false)} />}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <CapturePage />
    </Suspense>
  );
}
