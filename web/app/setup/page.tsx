"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ContactPrefs } from "@/components/ContactPrefs";
import { InternAvatar, type Growth } from "@/components/InternAvatar";
import { PageHeader } from "@/components/ui";
import { api, type ManagerTeam } from "@/lib/api";
import { useTaskTypes } from "@/lib/useTaskTypes";

const STEPS: { href: string; title: string; body: string; growth: Growth; manager?: boolean }[] = [
  { href: "/orientation", title: "Give it the handbook", body: "Upload your team's policies and answer a few questions. It drafts a handbook; the manager approves it.", growth: "egg" },
  { href: "/capture", title: "Connect the work", body: "Point it at the inbox, ledger or export where this work happens, so it can watch what your team does.", growth: "larva" },
  { href: "/backtest", title: "Replay past cases", body: "It works through last year's cases, seeing only what was known at the time, and is scored against your team.", growth: "larva" },
  { href: "/learned", title: "Rules it follows", body: "Everything it has learned, in plain English. Edit one and it re-checks its recent answers.", growth: "eft" },
  { href: "/manager", title: "Team settings", body: "Rename your intern, and set minutes per case and hourly cost for the value numbers.", growth: "adult", manager: true },
];

export default function SetupPage() {
  const { user, taskType } = useTaskTypes();
  const [team, setTeam] = useState<ManagerTeam | null>(null);

  useEffect(() => {
    if (user && taskType) api.managerDashboard().then((m) => setTeam(m.teams.find((t) => t.team === taskType.team) ?? null)).catch(() => {});
  }, [user, taskType]);

  const intern = taskType?.intern_name ?? "your intern";
  return (
    <div className="space-y-8">
      <PageHeader title={<>Set up <span className="hl">{intern}</span></>} mood="learning"
                  intro="The one-off steps that get a new intern started, and the settings behind it." />
      <ol className="stagger grid gap-3 md:grid-cols-2">
        {STEPS.map((s, i) => {
          const done = s.href === "/orientation" ? Boolean(team?.handbook) : undefined;
          return (
            <li key={s.href}>
              <Link href={s.href} className="lift flex h-full gap-4 rounded-3xl border border-stone-200 bg-white p-5">
                <InternAvatar growth={s.growth} size={56} decorative animated={false} className="shrink-0" />
                <div className="space-y-1">
                  <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                    Step {i + 1}{s.manager && " · manager"}
                    {done && <span className="rounded-full bg-emerald-100 px-2 py-0.5 normal-case tracking-normal text-emerald-800">done</span>}
                  </p>
                  <h2 className="text-lg font-extrabold">{s.title}</h2>
                  <p className="text-sm text-stone-600">{s.body}</p>
                </div>
              </Link>
            </li>
          );
        })}
      </ol>
      {user && <ContactPrefs intern={intern === "your intern" ? "Newt" : intern} />}
      <p className="text-sm text-stone-500">
        Detailed views: <Link href="/board" className="underline">task board</Link> · <Link href="/autonomy" className="underline">autonomy log</Link> ·{" "}
        <Link href="/today" className="underline">teaching only</Link>
      </p>
    </div>
  );
}
