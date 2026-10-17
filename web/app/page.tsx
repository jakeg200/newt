import Link from "next/link";

const STAGES = [
  { name: "Orientation", body: "Turn the team's documents and the mentor's answers into the agent's handbook. The manager approves it.", ready: true },
  { name: "Shadowing", body: "The agent makes sealed predictions, scored against what the mentor actually did.", ready: false },
  { name: "Supervised practice", body: "The agent drafts, the mentor approves in one tap, and corrections teach it.", ready: false },
  { name: "Graduation", body: "Each task type earns autonomy on a statistical bar, signed by the manager.", ready: false },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <div className="max-w-2xl space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Onboard an AI agent like a new hire</h1>
        <p className="text-stone-600">
          Each stage produces evidence. Start with orientation: the handbook every agent reads before its first case.
        </p>
      </div>
      <ol className="grid gap-4 sm:grid-cols-2">
        {STAGES.map((s, i) => (
          <li key={s.name} className="rounded-lg border border-stone-200 bg-white p-5">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Stage {i + 1}</div>
            <h2 className="font-medium">{s.name}</h2>
            <p className="mt-1 text-sm text-stone-600">{s.body}</p>
            {s.ready ? (
              <Link href="/orientation" className="mt-3 inline-block text-sm font-medium text-teal-700 hover:underline">
                Open orientation →
              </Link>
            ) : (
              <p className="mt-3 text-sm text-stone-400">Coming next</p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
