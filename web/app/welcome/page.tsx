import Link from "next/link";
import { InternAvatar, type Growth, type Mood } from "@/components/InternAvatar";
import { Reveal } from "@/components/Reveal";
import { Bubble } from "@/components/ui";

const STORY: { growth: Growth; mood: Mood; size: number; stage: string; title: string; body: string; says: string }[] = [
  { growth: "egg", mood: "neutral", size: 140, stage: "Orientation", title: "It reads the handbook first.",
    body: "Upload your team's policies and answer a few questions. Newt drafts its own handbook, with every rule linked to where it came from. Nothing is live until your manager approves it.",
    says: "I've read your 5 policies. 14 rules, each linked to its source. Ready for your manager to check." },
  { growth: "larva", mood: "learning", size: 160, stage: "Shadowing", title: "Then it watches you work.",
    body: "On every new case, Newt writes down what it would do, sealed until you've decided. Then you see both side by side. One tap teaches it, and the lesson sticks.",
    says: "I'd have queried the supplier. You escalated. Got it: anything over the £5,000 limit goes to you." },
  { growth: "eft", mood: "drafting", size: 190, stage: "Supervised practice", title: "It drafts. You approve.",
    body: "Once the evidence clears your bar, Newt starts preparing the work for real: the decision, the fields, the reply. You approve in one tap or fix it, and it learns from the fix.",
    says: "3 replies drafted for you. Anything unusual I've handed back, with the reason." },
  { growth: "adult", mood: "graduated", size: 230, stage: "Graduated", title: "Then it works on its own.",
    body: "Your manager signs. Newt handles the routine cases alone, hands back anything unusual, and some of its work comes back to you blind as a spot check. Slip up, and it goes back to practice.",
    says: "Handled 36 invoices on my own today. 2 handed back to you. Spot checks: all passed." },
];

export default function Welcome() {
  return (
    <div className="space-y-28 pb-10">
      {/* Hero */}
      <section className="grid items-center gap-10 pt-10 md:grid-cols-[1.25fr_1fr]">
        <div className="stagger space-y-6">
          <p className="hand text-3xl text-brand-700">Your next hire is a newt.</p>
          <h1 className="text-5xl leading-[1.02] sm:text-7xl">
            Onboard AI <br />like a <span className="hl">new hire</span>.
          </h1>
          <p className="max-w-xl text-lg text-stone-600">
            Newt learns your team&apos;s job the way a person does: it reads the handbook, shadows your experts, practises under
            supervision, and only works alone once the evidence says it can be trusted.
          </p>
          <div className="flex flex-wrap gap-3">
            <a href="#pilot" className="lift rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white">Join the pilot</a>
            <a href="#how" className="lift rounded-full border border-stone-300 bg-white px-6 py-3 text-sm font-semibold">See how it learns ↓</a>
          </div>
        </div>
        <div className="relative flex min-h-[22rem] items-center justify-center">
          <InternAvatar mood="hello" size={300} />
          <div className="float absolute -top-2 right-0 hidden w-64 lg:block" style={{ ["--tilt" as string]: "2deg" }}>
            <Bubble name="Newt" mood="working" time="2m ago">Handled 14 invoices. 2 need you.</Bubble>
          </div>
          <div className="float absolute bottom-0 left-0 hidden w-64 lg:block" style={{ ["--tilt" as string]: "-2deg", animationDelay: "1.2s" }}>
            <Bubble name="Newt" mood="learning" growth="larva" time="now">Got it. Bank detail changes always go to you.</Bubble>
          </div>
        </div>
      </section>

      {/* The growth story */}
      <section id="how" className="scroll-mt-24 space-y-16">
        <Reveal className="mx-auto max-w-2xl space-y-3 text-center">
          <h2 className="text-4xl font-extrabold sm:text-5xl">Every new hire <span className="hl">grows into the job</span>.</h2>
          <p className="text-lg text-stone-600">Newt does too, from egg to graduate, one stage at a time, and only on evidence.</p>
        </Reveal>
        {STORY.map((s, i) => (
          <Reveal key={s.stage}>
            <div className={`grid items-center gap-8 md:grid-cols-2 ${i % 2 ? "md:[&>*:first-child]:order-2" : ""}`}>
              <div className="flex justify-center">
                <InternAvatar growth={s.growth} mood={s.mood} size={s.size} />
              </div>
              <div className="space-y-4">
                <p className="text-sm font-semibold uppercase tracking-wide text-brand-700">Stage {i + 1} · {s.stage}</p>
                <h3 className="font-[family-name:var(--font-display)] text-3xl font-extrabold sm:text-4xl">{s.title}</h3>
                <p className="text-lg text-stone-600">{s.body}</p>
                <div className="max-w-md">
                  <Bubble name="Newt" mood={s.mood} growth={s.growth}>{s.says}</Bubble>
                </div>
              </div>
            </div>
          </Reveal>
        ))}
      </section>

      {/* Why trust it */}
      <section id="trust" className="scroll-mt-24 space-y-10">
        <Reveal className="mx-auto max-w-2xl space-y-3 text-center">
          <h2 className="text-4xl font-extrabold sm:text-5xl">Autonomy is <span className="hl">earned</span>, not assumed.</h2>
          <p className="text-lg text-stone-600">
            Every stage has a bar your team sets. Newt&apos;s report card shows exactly where it stands, in plain numbers.
          </p>
        </Reveal>
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ["Sealed predictions", "It commits to an answer before seeing yours, so its track record can't be flattered."],
            ["A limit you choose", "It only works alone where the worst-case error rate is under your limit, say 2%."],
            ["Blind spot checks", "Some of its solo work comes back to you without its answer. Fail, and it goes back to practice."],
          ].map(([t, b], i) => (
            <Reveal key={t} delay={i * 90}>
              <div className="h-full space-y-2 rounded-3xl border border-stone-200 bg-white p-6">
                <h3 className="font-[family-name:var(--font-display)] text-xl font-extrabold">{t}</h3>
                <p className="text-stone-600">{b}</p>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal className="mx-auto max-w-xl">
          <div className="space-y-3 rounded-3xl border border-stone-200 bg-white p-6">
            <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Example report card (illustration)</p>
            <div className="grid grid-cols-3 gap-3 text-center">
              {[["97%", "in line with your team"], ["1.4%", "wrong at most, when sure"], ["62%", "of the work it can take"]].map(([n, l]) => (
                <div key={l}>
                  <p className="font-[family-name:var(--font-display)] text-3xl font-extrabold">{n}</p>
                  <p className="text-xs text-stone-500">{l}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* Call to action */}
      <section id="pilot" className="scroll-mt-24">
        <Reveal>
          <div className="flex flex-col items-center gap-6 rounded-[2.5rem] bg-ink px-6 py-14 text-center text-white">
            <InternAvatar mood="graduated" size={150} />
            <h2 className="text-4xl font-extrabold sm:text-5xl">Hire your first newt.</h2>
            <p className="max-w-lg text-lg text-white/70">
              We&apos;re onboarding our first teams now. Bring one repetitive job and a year of its history, and see how Newt
              would have done, before it touches anything.
            </p>
            <Link href="/" className="lift rounded-full bg-brand-500 px-6 py-3 text-sm font-semibold text-ink">Try the demo</Link>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
