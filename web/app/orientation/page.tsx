"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Documents } from "@/components/orientation/Documents";
import { HandbookView } from "@/components/orientation/HandbookView";
import { Questionnaire } from "@/components/orientation/Questionnaire";
import { SourcePanel } from "@/components/orientation/SourcePanel";
import { api, ApiError, type Handbook, type Passage, type Question, type SourceDoc } from "@/lib/api";
import { InternAvatar } from "@/components/InternAvatar";
import { useUser } from "@/lib/user";

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-medium">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
            done ? "bg-emerald-600 text-white" : "bg-stone-200 text-stone-700"
          }`}
        >
          {done ? "✓" : n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

const teamLabel = (team: string) => team.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export default function OrientationPage() {
  const { user } = useUser();
  const [teams, setTeams] = useState<string[]>([]);
  const [team, setTeam] = useState<string | null>(null);
  const [docs, setDocs] = useState<SourceDoc[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [passages, setPassages] = useState<Passage[]>([]);
  const [versions, setVersions] = useState<Handbook[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    if (!user) return;
    api
      .teams()
      .then((list) => {
        setTeams(list);
        setTeam((t) => (t && list.includes(t) ? t : (list[0] ?? null)));
      })
      .catch(fail);
  }, [user]);

  const load = useCallback(async (t: string) => {
    const [d, q, p, v] = await Promise.all([api.sources(t), api.questionnaire(t), api.passages(t), api.handbooks(t)]);
    setDocs(d);
    setQuestions(q);
    setPassages(p);
    setVersions(v);
    return v;
  }, []);

  useEffect(() => {
    if (!team || !user) return;
    setError(null);
    load(team)
      .then((v) => setSelected(v[0]?.id ?? null))
      .catch(fail);
  }, [team, user, load]);

  const passageMap = useMemo(() => new Map(passages.map((p) => [p.label, p])), [passages]);
  const role = user?.role;
  const canEdit = role === "mentor" || role === "manager" || role === "admin";
  const approved = versions.find((v) => v.status === "approved");

  async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError(null);
    try {
      return await fn();
    } catch (e) {
      fail(e);
      return undefined;
    }
  }

  if (!user || !team) {
    return <p className="text-sm text-stone-500">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-4"><InternAvatar mood="learning" growth="egg" size={72} className="hidden shrink-0 sm:block" /><h1 className="text-3xl sm:text-4xl">Orientation</h1></div>
          <p className="max-w-2xl text-sm text-stone-600">
            The agent&apos;s handbook, written from this team&apos;s own documents and its mentor&apos;s answers. Every line
            links to where it came from, and nothing is live until the manager approves it.
          </p>
        </div>
        {teams.length > 1 && (
          <div className="flex gap-1 rounded-lg bg-stone-200/60 p-1 text-sm" role="tablist" aria-label="Team">
            {teams.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={t === team}
                onClick={() => setTeam(t)}
                className={`rounded-md px-3 py-1 ${t === team ? "bg-white font-medium shadow-sm" : "text-stone-600"}`}
              >
                {teamLabel(t)}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-start justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-600">
            Dismiss
          </button>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="space-y-8">
          <Step n={1} title="Team documents" done={docs.length > 0}>
            <Documents
              docs={docs}
              canEdit={canEdit}
              onUpload={async (files) => {
                const results = (await act(() => api.upload(team, files))) ?? [];
                await act(() => load(team));
                return results;
              }}
              onDelete={async (doc) => {
                await act(() => api.deleteSource(doc.id));
                await act(() => load(team));
              }}
            />
          </Step>
          <Step n={2} title="Mentor questionnaire" done={questions.some((q) => q.answer)}>
            <Questionnaire
              questions={questions}
              canEdit={role === "mentor" || role === "admin"}
              onSave={async (answers) => {
                await act(() => api.saveAnswers(team, answers));
                await act(() => load(team));
              }}
            />
          </Step>
        </div>

        <Step n={3} title="Handbook" done={!!approved}>
          <HandbookView
            versions={versions}
            selectedId={selected}
            onSelect={setSelected}
            passages={passageMap}
            role={role}
            hasSources={passages.length > 0}
            onDraft={async () => {
              const h = await act(() => api.draft(team));
              if (h) {
                await load(team);
                setSelected(h.id);
              }
            }}
            onSave={async (content) => {
              if (!selected) return;
              const h = await act(() => api.updateHandbook(selected, content));
              if (h) setVersions((vs) => vs.map((v) => (v.id === h.id ? h : v)));
            }}
            onApprove={async () => {
              if (!selected) return;
              if (await act(() => api.approve(selected))) await load(team);
            }}
            onRevise={async () => {
              if (!selected) return;
              const h = await act(() => api.revise(selected));
              if (h) {
                await load(team);
                setSelected(h.id);
              }
            }}
            onShowSource={setSource}
          />
        </Step>
      </div>

      {source && <SourcePanel label={source} passage={passageMap.get(source)} onClose={() => setSource(null)} />}
    </div>
  );
}
