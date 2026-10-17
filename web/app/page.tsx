"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { InternAvatar, STAGE_MOOD } from "@/components/InternAvatar";
import { api, ApiError, type BoardRow, type Stage } from "@/lib/api";
import { useUser } from "@/lib/user";

const PATH: { stage: Stage | "orientation"; label: string }[] = [
  { stage: "orientation", label: "Orientation" },
  { stage: "shadow", label: "Shadowing" },
  { stage: "supervised", label: "Supervised" },
  { stage: "autonomous", label: "Graduated" },
];

function nextStep(row: BoardRow, role: string | undefined): { text: string; href: string } {
  const manager = role === "manager";
  if (row.status === "shadow" && row.evaluation.eligible)
    return manager ? { text: "Ready for the mentor to sign supervised practice", href: "/board" } : { text: "Ready to graduate: sign supervised practice", href: "/board" };
  if (row.status === "shadow" || row.status === "demoted")
    return manager ? { text: "Shadowing: see the evidence so far", href: "/board" } : { text: "Teach it today's cases", href: "/today" };
  if (row.status === "supervised")
    return row.supervised_cases >= row.supervised_needed && manager
      ? { text: "Ready for your autonomy signature", href: "/board" }
      : { text: `Approve its drafts (${row.supervised_cases} of ${row.supervised_needed} done)`, href: "/autonomy" };
  return manager ? { text: "See hours returned", href: "/manager" } : { text: "Check hand-backs and audits", href: "/autonomy" };
}

export default function Home() {
  const { user } = useUser();
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api.board().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [user]);

  return (
    <div className="space-y-8">
      <section className="flex flex-col items-start gap-5 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-brand-100 sm:flex-row sm:items-center">
        <InternAvatar mood="hello" size={112} />
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-cap-900">
            Hi{user ? ` ${user.name.split(" ")[0]}` : ""}, I&apos;m your new intern.
          </h1>
          <p className="max-w-2xl text-stone-600">
            I learn your team&apos;s work the way a new hire does: read the handbook, shadow you, practise under supervision,
            and only work on my own once the evidence says I can be trusted.
          </p>
        </div>
      </section>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {!rows && !error && <p className="text-sm text-stone-500">Loading…</p>}
      {rows?.length === 0 && (
        <p className="text-sm text-stone-600">
          No task types yet. Start with <Link href="/orientation" className="font-medium text-brand-700 underline">orientation</Link>.
        </p>
      )}

      <ul className="grid gap-4 md:grid-cols-2">
        {rows?.map((row) => {
          const at = PATH.findIndex((p) => p.stage === (row.status === "demoted" ? "shadow" : row.status));
          const step = nextStep(row, user?.role);
          return (
            <li key={row.id} className="space-y-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-stone-200">
              <div className="flex items-center gap-3">
                <InternAvatar mood={STAGE_MOOD[row.status]} size={56} />
                <div>
                  <h2 className="font-medium text-cap-900">{row.name}</h2>
                  <p className="text-sm text-stone-500">
                    {row.status === "demoted" ? "Back to practice after audits or drift" : `Stage: ${PATH[at]?.label}`}
                  </p>
                </div>
              </div>
              <ol className="flex items-center gap-1 text-xs" aria-label="Onboarding stages">
                {PATH.map((p, i) => (
                  <li key={p.stage} className="flex flex-1 flex-col gap-1">
                    <span className={`h-1.5 rounded-full ${i <= at ? "bg-brand-500" : "bg-stone-200"}`} />
                    <span className={i === at ? "font-medium text-brand-800" : "text-stone-500"}>{p.label}</span>
                  </li>
                ))}
              </ol>
              <Link href={step.href} className="inline-flex rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
                {step.text} →
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
