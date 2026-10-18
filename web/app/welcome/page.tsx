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

const FAQ: [string, string][] = [
  ["What exactly is Newt?",
   "An AI employee you hire for one specific job on one team. It learns that job the way a new hire would, from your handbook and from watching your expert, and it only takes on work it has proven it can do."],
  ["Does my team need to learn prompting or AI tools?",
   "No. Your experts keep doing their job in the systems they already use. Newt learns by watching what they decide. Teaching it takes one tap on the cases where it disagreed, about ten minutes a day."],
  ["How does it actually learn?",
   "Four ways: a handbook drafted from your own policies (approved by your manager), shadowing real work with sealed predictions, one-tap lessons when it gets something wrong, and plain-English rules you can give it any time, like \"always escalate bank detail changes\"."],
  ["When does it start working on its own?",
   "Only when its report card clears a bar your team sets, such as being wrong at most 2% of the time on the cases it's sure about, over enough real cases to be sure. Your mentor signs it into supervised practice; your manager signs it into working alone."],
  ["What happens when it makes a mistake?",
   "Unusual cases are handed straight back to a person, with the reason. Some of its solo work comes back to your team blind as a spot check. If it slips, it automatically goes back to practice until it has earned its place again."],
  ["Does it keep improving after it graduates?",
   "Yes. Every correction, spot check and new rule feeds back in, and when we upgrade the underlying model it re-proves itself on its past work before it's allowed back on the job."],
  ["What kind of jobs can it do?",
   "Repetitive judgement work that arrives in a queue or an inbox and follows written policy: checking invoices against purchase orders, triaging repair or support requests, routing and answering routine questions. One role at a time."],
  ["What about our data?",
   "Personal details are redacted before anything is stored, Newt is built to run on EU hosting, and it only ever sees text. It can only take actions you've explicitly allowed for that role."],
  ["How quickly will we know if it's any good?",
   "Before it touches anything live. Give us last year's history for the role and Newt replays it, seeing only what was known at the time, so you see exactly how it would have done."],
];

export default function Welcome() {
  return (
    <div className="space-y-28 pb-10">
      {/* Hero */}
      <section className="grid items-center gap-10 pt-10 md:grid-cols-[1.25fr_1fr]">
        <div className="stagger space-y-6">
          <p className="hand text-3xl text-brand-700">Your next hire is a newt.</p>
          <h1 className="text-5xl leading-[1.02] sm:text-7xl">
            AI employees, <br />trained like a <span className="hl">new hire</span>.
          </h1>
          <p className="max-w-xl text-lg text-stone-600">
            Hire Newt for one job on your team. It starts as an intern: it reads your handbook, shadows your best person,
            practises under supervision, and graduates to working alone once the evidence says it&apos;s ready. Then it keeps
            getting better.
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

      {/* What it is */}
      <section className="space-y-10">
        <Reveal className="mx-auto max-w-3xl space-y-4 text-center">
          <h2 className="text-4xl font-extrabold sm:text-5xl">Not a tool to learn. <span className="hl">A colleague to train.</span></h2>
          <p className="text-lg text-stone-600">
            Your team doesn&apos;t need to learn prompting or change how they work. They keep doing their job; Newt learns it
            from them, one role at a time, and gets measurably better every week.
          </p>
        </Reveal>
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ["1", "Hire it for one role", "Pick a job your team does every day: checking invoices, triaging requests, answering the same questions. Newt joins that team and learns that job."],
            ["2", "It learns from your best person", "It watches what your expert actually decides, compares it with its own sealed answer, and takes one-tap lessons. No prompts, no training courses."],
            ["3", "It earns more responsibility", "Intern, then supervised, then graduate. Each step needs evidence and a signature. And it never stops learning: corrections keep making it better."],
          ].map(([n, t, b], i) => (
            <Reveal key={n} delay={i * 90}>
              <div className="h-full space-y-3 rounded-3xl border border-stone-200 bg-white p-6">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 font-[family-name:var(--font-display)] font-extrabold">{n}</span>
                <h3 className="font-[family-name:var(--font-display)] text-xl font-extrabold">{t}</h3>
                <p className="text-stone-600">{b}</p>
              </div>
            </Reveal>
          ))}
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

      {/* FAQ */}
      <section id="faq" className="mx-auto max-w-3xl scroll-mt-24 space-y-6">
        <Reveal className="text-center">
          <h2 className="text-4xl font-extrabold sm:text-5xl">Questions, answered.</h2>
        </Reveal>
        <div className="divide-y divide-stone-200 rounded-3xl border border-stone-200 bg-white">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group px-6 py-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-[family-name:var(--font-display)] text-lg font-extrabold">
                {q}
                <span className="shrink-0 text-2xl font-normal text-brand-600 transition-transform group-open:rotate-45" aria-hidden>+</span>
              </summary>
              <p className="mt-3 text-stone-600">{a}</p>
            </details>
          ))}
        </div>
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
