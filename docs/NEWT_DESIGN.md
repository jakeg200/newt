# Newt: how it learns, works and fits into a team

The design behind Newt as a colleague: the first-principles model, what exists today, and the order to build the
rest. Status markers: **built** (in the code now), **next** (designed, not built), **later**.

---

## 1. Landscape and positioning

Most of these figures come from secondary write-ups with differing definitions, so they're ranges, not facts.

| What the market shows | What it means for Newt |
|---|---|
| Most agent pilots never reach production: estimates run from ~60% to ~90% ([Composio/Forrester/Deloitte summaries](https://www.beri.net/article/ai-agent-pilots-fail-88-percent-production-2026)). Gartner is reported to expect >40% of agentic projects to be cancelled by end-2027. The causes are messy integration, **no agreed success criteria**, **governance gaps** (permissions, override, audit), poor observability and reliability. | Newt's onboarding *is* the path from pilot to production. The report card supplies the success criteria, authority levels the governance, plus an audit trail, a backtest before going live, and hand-backs. |
| The "learning gap": pilots stall less because of model quality and more because tools don't learn from or adapt to workflows. Generic chat works for individuals and stalls in companies ([MIT NANDA, 2025, via Fortune](https://fortune.com/2025/08/18/mit-report-95-percent-generative-ai-pilots-at-companies-failing-cfo)). | Learning on the job is the product, not a feature. |
| People are the barrier: skills gaps, too little time, and training that arrives after rollout ([Skillsoft](https://www.skillsoft.com/blog/the-ai-skills-gap-in-the-workplace-the-statistics-that-matter-in-2026), [Deloitte](https://www.deloitte.com/us/en/what-we-do/capabilities/applied-artificial-intelligence/content/state-of-ai-in-the-enterprise.html)). We found no evidence that prompt workshops work. | **Flip the burden:** people don't learn AI; Newt learns *them*. Firms become AI-native role by role, without retraining everyone. |
| Traditional firms and SMEs lag: about 20% of EU firms use AI, 17% of small firms against 55% of large ones. The barriers are cost, legal uncertainty, expertise and trust ([Eurostat via summary](https://pasqualepillitteri.it/en/news/9727/digital-decade-2026-europe-cloud-skills-gap)). | Easy, safe and legally clear out of the box: consent, redaction, EU hosting and bounded authority. |
| "AI employees" mostly cover one slice of a job ([market maps](https://www.teamday.ai/blog/ai-employees-market-map-2026)). Sierra and Decagon rely on forward-deployed engineers, with 3–10 week set-ups and behaviour changes that go through the vendor ([Sacra](https://sacra.com/research/decagon-vs-sierra/)). | The customer's own expert trains Newt, self-serve. The onboarding replaces the forward-deployed engineer. |
| Task mining is moving privacy-first (on-device redaction, pausing, excluded apps), and always-on recording is often blocked by IT and legal ([Mimica](https://www.mimica.ai/blog/what-is-task-mining)). | Screen learning only through opt-in "show me" sessions (§12). |
| **Hone** ([hone.com](https://hone.com/)) raised a $60M seed (Benchmark and Index, Oct 2026) for "Engines that own outcomes". Its engines onboard themselves, replay a company's history before going live, live in Slack, Teams and email, and self-improve with replay-tested changes ([Closing the Gap #1](https://hone.com/blog/closing-the-gap/)). | The engine thesis is investable. Newt's difference: it **earns** every step, from intern to senior, on evidence and signatures; it's hired for a **role with KPIs** rather than handed a goal; and it's **self-serve** for traditional and mid-market firms. |
| Agent memory is becoming infrastructure. Obsolete knowledge needs lifecycle states ([arXiv 2608.18177](https://arxiv.org/pdf/2608.18177)). | Memory with active, dormant and retired states, plus consolidation (§7). |

**Positioning:** make any firm AI-native without retraining its people. Hire Newts for real roles. They learn the work
from your experts, earn trust on evidence, and plug into how you already work. Not another chat window.

## 2. Thesis

LLMs can already do most knowledge work. What they can't do is **hold a job**, which needs five things:

1. **Context:** your rules, exceptions and people.
2. **Integration:** being where the work arrives.
3. **Accountability:** knowing what it may do alone.
4. **Continuity:** getting better at *your* job.
5. **Initiative:** owning a queue without being prompted.

Today a person is the integrator: they carry the context, prompt the tool, check the output and move it into the
system. **Newt removes the human-as-integrator for one role.** Models are a commodity; the role layer is the product.

**Better than a human intern, measurably:**
- A lesson applies to every future case at once, and past work is re-checked.
- It never forgets.
- Every decision shows its sources and reasons.
- It's available instantly.
- It measures itself.

It starts weaker on context and judgement, which is exactly what §3 closes. The **learning curve** (cases and days to
reach a given agreement) is the benchmark against a human ramp-up (§13).

**Framing:** every expert gets an apprentice that takes the work they shouldn't be doing, and whose growth they own.
Newt is not a replacement. People are never scored (an existing rule).

## 3. How a new hire gets good, and how Newt mirrors it

Grounded in established models of workplace learning:
- **70-20-10:** most learning comes from doing, then from people and feedback, least from courses.
- **Cognitive apprenticeship:** modelling, then coaching, then scaffolding, then fading.
- **Legitimate peripheral participation:** start at the safe edges, move to the centre.
- **Deliberate practice** and the 30-60-90-day plan.

| How a new hire improves | What Newt does | Burden on people | Status |
|---|---|---|---|
| Reads in | Drafts its own handbook from the team's documents | Manager approves once | built |
| Watches the expert | Shadows real work captured from systems | None | built |
| | "Show me" sessions | A minute, when they choose | later |
| Small safe tasks first, then bigger | Tasks given in conversation | Ask it like a person | built |
| | Low-risk segments graduate first | Ask it like a person | next |
| Feedback in the flow | **Implicit:** an approval, edit or override *is* the lesson | None extra | built |
| | One tap only where it differed | | built |
| Asks good questions | Curiosity planner: valuable, batched, rationed, never twice; question banks per role | A few a week, falling | built |
| Learns who's who | Org model: people, counterparties, who decides what | None | next |
| Reflects, writes things down | Nightly consolidation; proposes handbook revisions | Approve or reject | next |
| Mistakes made safely | Hand-backs, blind spot checks, automatic demotion | Only when it matters | built |
| Goals and check-ins | Morning stand-up | Read it | built |
| | Weekly 1:1 note and its own 30-60-90 plan | Read it | next |
| | Report card | Read it | built |
| Earns trust by being reliable | Track record; asks for promotion with evidence | Sign | built |
| Oversight fades | Asks less and acts more as evidence grows | Falls weekly | built |

**Rules that stop Newt becoming admin:**
1. Learn from what people already do first.
2. Implicit feedback over buttons.
3. Every interruption earns its place: a value threshold, a daily budget, working hours, batching, one tap.
4. Never ask twice, and never ask what it could look up.
5. Newt does its own paperwork; people approve.
6. Silent when nothing needs you.
7. **Net time positive from week one.** The attention Newt costs the team must stay well below the time it saves, and
   fall over time. This is measured as Newt's cost, never as a score of a person.

## 4. Core model: role → responsibilities → authority

- **Role:** a job on a team.
- **Responsibility:** a recurring kind of work inside it (today's task type, **built**), or a one-off task given in
  conversation (**built**). Both sit on one continuum, at different trust levels.
- **Authority matrix (next):** responsibility × segment → level. The levels are *observe → draft → act with approval →
  act and report*. Today's stages (shadow, supervised, autonomous) are this matrix with one segment. Splitting into
  segments (e.g. "price variances under £500") lets easy work graduate first. Newt requests each promotion with the
  evidence (**built** for whole task types).

## 5. Episodes: the unit of learning

An episode is context → Newt's sealed answer → the person's action → outcome → feedback. Today it's spread across
`Case`, `Prediction`, `HumanAction`, `Comparison` and `Lesson`. Conversation answers become episodes too: answering a
question about a case records the person's decision (`HumanAction`, source `conversation`), which reveals and scores
the sealed prediction.

## 6. Signals in

Every signal is redacted before it's stored and carries `observed_at`, so the time-travel guard
(`app/agents/context.py`) applies to all of them.

- **Systems:** email, ledgers, ticketing, via `app/capture/` (**built**).
- **Conversation:** with Newt (**built**).
- **Voice-note and call transcripts** (**later**).
- **"Show me" step logs** (**later**, §12).
- **Documents:** via orientation (**built**).
- **Outcomes:** audits and reversals (**built** in part).

## 7. Memory

Typed, versioned and sourced, with lifecycle states (active, dormant, retired):

| Memory | What it holds | Status |
|---|---|---|
| Handbook | Explicit, approved procedure | built |
| Rules | Learned or stated, versioned, retirable | built |
| Case memory | Past episodes, retrieved by similarity | built |
| Question-bank answers | First-week knowledge from the mentor (feeds the handbook) | built |
| Procedures | Step sequences from show-me sessions and repeated actions | later |
| Org model | People, roles, counterparties, preferences, who to ask | next |
| Taste | Reply and report style, from edits and feedback on deliveries | built (captured), next (used) |

Everything reaches the agent only through `ContextBuilder`.

## 8. The learning engine

- **Extractors** (built):
  - documents → handbook;
  - episodes → rules (`app/learning/rules.py`);
  - corrections → preference pairs;
  - question-bank answers → questionnaire → handbook.
- **Curiosity planner** (built, `app/colleague/curiosity.py`):
  - Asks about unsure cases it's shadowing, ranked by `(1 − confidence) × (1 + ln(1 + similar open cases))`. Its own
    guess stays sealed.
  - Asks about disagreements from the latest backtest.
  - Asks the role's question bank.
  - Has a value threshold, a daily budget, at most two open at once, and dedupe keys.
  - Counterfactual probes ("if it were £6k, still approve?") are **next**.
- **Consolidation ("sleep")** (next): nightly merging and conflict detection; proposed handbook revisions for the
  manager to approve.
- **Policy improvement** (later): fine-tuning or RL on preference pairs, across customers per role, offline only, and
  always gated by re-certification.
- **Never regress** (built): every rule, handbook or model change is replayed on past work before it goes live.

## 9. The work engine

Intake comes from queues and from tasks given in conversation. Newt plans and acts inside its authority, then:
confidence → hand-back if unsure (`graduation/handback.py`) → actions only through `actions/policy.py`. Deliveries go
back to whoever asked. Tasks run through the provider interface, with a deterministic offline fallback
(`app/colleague/assist.py`).

## 10. The trust engine

Built today:
- statistics in `eval/stats.py`;
- the graduation engine (`graduation/engine.py`);
- blind spot checks, drift and demotion;
- re-certification on model and procedure changes;
- the track record PDF.

Next: per-segment bounds for the authority matrix.

## 11. The interaction layer: Newt as a colleague

**Channels:**
- the app's conversation (**built**);
- Slack, Teams and email (**next**; the `channel` preference exists);
- voice notes and call requests (**later**);
- the web app as Newt's "HR file": report card, setup and audits (**built**).

**Behaviours (built):**
- a morning stand-up;
- questions with tap-to-answer chips;
- drafts approved inline;
- hand-backs resolved inline;
- tasks delivered with 👍, redo and copy;
- promotion requests with evidence and a Sign button.

**Next:** a weekly 1:1 note, proactive suggestions, and the 30-60-90 plan.

**Etiquette (built, `app/colleague/etiquette.py`):**
- Work arrives in working hours without using the budget.
- Questions are rationed per day, in working hours only.
- Urgent things arrive out of hours only if the person allows it.
- Messages held back follow the person's current preferences.
- Calls are always a request, never a surprise.

**A day in the life (mentor):**
> 09:00. Newt: *Morning stand-up. I handled 14 cases on my own; 3 drafts are ready; 1 case needs your call.*
> 09:02. Sarah approves two drafts and taps "escalate" on the hand-back.
> 11:30. Newt: *I'm not sure what you'd do with Contoso invoice INV-91009. There are 4 more like it waiting. What's your call?* Sarah taps "query supplier". Newt: *Thanks. I'd have said approve, so that's a useful lesson.*
> 14:10. Sarah: *Always escalate bank detail changes.* Newt: *Got it. I'm re-checking my recent answers with it.*
> 16:00. Sarah: *Pull together this month's queries.* Newt delivers the list; Sarah taps 👍.

**A day in the life (manager):**
> 09:00. Newt: *Morning stand-up. 107 cases handled this month, 10.7 hours returned.*
> Later: *60 practice cases approved and my error bound is still 0.8%. May I handle the routine cases on my own?* [Sign]

## 12. Consent, privacy and EU

**Consent:**
- Per person and per capture type (the `consents` table exists).
- Voice and screen only ever through consented, opt-in sessions:
  - **"Show me" sessions** are started by the person, scoped to chosen apps, and pausable. They're redacted on the
    device and turned into step logs; the raw video is discarded.
  - **Voice:** transcripts are redacted; raw audio is not kept.

**Privacy:**
- Raw audio, video and keystrokes are never stored.
- Text typed to Newt is redacted before storage (**built**).

**EU:**
- EU hosting; GDPR; works-council consultation where capture touches employees.
- Check the AI Act position: back-office roles are likely not high-risk, but anything about managing people would be.

**Liability:** bounded authority, a full audit trail and hand-backs. Contracts define responsibility.

## 13. Evaluation

**For the product:**
- agreement, error bound, coverage and hours returned (**built**);
- time to competence (**next**);
- **net time** (**next**): team minutes spent on Newt (answering, approving, teaching) against minutes saved. It must
  be positive from week one and the attention cost must fall.

**For Newt against a human intern:** a learning curve of agreement against cases seen, on the same history, compared
with the team's own ramp-up data where available.

## 14. Map from today's code

| Design | Code |
|---|---|
| Responsibility | `TaskType` + `task_types/*.json` (now with `question_bank`) |
| Authority level | `TaskType.status` (shadow, supervised, autonomous, demoted) |
| Episode | `Case`, `Prediction`, `HumanAction`, `Comparison`, `Lesson` |
| Conversation | `Message` and `User.preferences`; `app/colleague/*`; `app/api/messages.py`; `web/app/page.tsx` and `web/components/chat/*` |
| Memory | `Handbook`, `Rule`, `QuestionnaireAnswer`, case retrieval in `agents/retrieval.py` |
| Trust | `eval/stats.py`, `graduation/*`, `backtest/runner.py` (re-probation) |
| Policy | `actions/policy.py` |

## 15. Build sequence

1. **Conversation, etiquette, curiosity, tasks, promotions.** Built on branch `newt-colleague`.
2. **Slack/Teams/email delivery** of the same messages, with one-tap answers in the message.
3. **Consolidation:** nightly notes, handbook revisions Newt proposes, memory lifecycle, the weekly 1:1.
4. **Authority matrix by segment:** per-segment bounds, promotion requests per segment.
5. **Org model** and counterfactual probes.
6. **Voice:** voice notes, then requested calls with transcripts.
7. **"Show me" sessions:** a desktop or browser capture client, on-device redaction, step logs to procedures.
8. **Cross-customer role priors** (opt-in) and preference-based fine-tuning experiments.

## 16. Doing the work, outcomes and the career ladder (built)

**USP:** Newt joins as an intern, learns the job, and keeps getting promoted on performance. Everything below serves
that.

**Career ladder** (`app/colleague/career.py`):
- **New starter:** orientation.
- **Intern:** shadowing, with sealed predictions.
- **Junior:** supervised; drafts that run only after approval.
- **Graduate:** autonomous on routine work; hands back the unusual; spot-checked.
- **Senior:** a graduate with extra responsibilities, such as chasing replies itself. Requested by Newt after 3+ clean
  spot checks and granted by a manager.

Stage changes keep the existing statistical gate and sign-offs. Promotion requests arrive as **performance reviews**:
the evidence plus KPIs. The Report card shows the ladder with dates.

**Finished work** (`app/execution/`):
- Allowed actions (autonomous, or approved) become jobs.
- The policy is checked again when acting.
- The executor posts a signed action to the team's **destination**: their system or Zapier/Make/n8n.
- Actions refer to the **source item**, never to people's details; the firm's system resolves the recipient.
- A case counts as **completed** only when every action is confirmed, either straight away or via the signed callback.
- Failures retry 3 times with backoff, then come back to the mentor with the reason and a "Try again" option.
- With no destination, work is simulated and labelled everywhere.

**Persistence:** per-decision follow-up days. If nothing has happened since Newt finished, it asks "Shall I chase?"; a
senior Newt chases on its own and says so.

**Routines** (`app/execution/routines.py`): for each decision, which actions to run and when to follow up. Newt
proposes them from history ("you replied on 92% of these"); the mentor agrees or edits them. Changing an approved
routine re-certifies.

**Outcome KPIs** (`app/outcomes/kpis.py`):
- Weekly, on confirmed completions: finished by Newt, share of the work, hours to finish, backlog, hours returned, value.
- Which KPIs and their targets live in the task-type config; the manager can override targets.
- The Report card leads with an **outcome chart**: the goal line, each promotion marked, and supporting numbers.
- The weekly "What I got done" message reports against those KPIs.

**Newt's first day** (`/first-day`), a guided conversation:
1. Name the intern.
2. How success is measured (KPI goals).
3. How trust is earned (the ladder and the hard rules).
4. Team know-how (the question bank).
5. Routines.
6. Systems (connect and test).
7. It starts as an intern.

**Demo:** `scripts/mock_system.py` (launch config `mock-system`) stands in for the firm's system.

## 17. From assistant to verified colleague

Copilot owns *assistance for a person*; Hone owns *declarative outcomes* and trusts its engines from day one. The
scarce thing is neither: it's work moving off people **at a risk the business can sign for**. Newt earns its way from
decisions to outcomes: it captures an expert's unwritten judgement, proves itself decision by decision, and is
promoted until it owns an outcome, with one expert supervising a team of Newts.

**A capable Newt** (`app/agents/workbench.py`, `tool_agent.py`, `replay.py`):
- Tools: search past cases, read an earlier case, look up a record in the firm's system, check the rules, calculate,
  propose. Which tools a role uses, and which lookups, live in the task-type config (`tools`, `lookups`).
- Every tool reads through `ContextBuilder`: past cases only before the item arrived; lookups live only in live mode,
  answered by the destination's signed `query` webhook and redacted before Newt sees them.
- With a key, `ToolApprentice` runs a step-limited tool loop (8 steps); without one, the offline `WorkbenchPlanner`
  (search → lookups → rules → propose) produces real trajectories.
- **Step-checked agreement** (`eval/score.step_checks`): a right answer without the evidence the role requires
  (`required_steps`, e.g. look up the PO before approving), or with a tool the role doesn't allow, counts as a
  disagreement. Graduation statistics are unchanged; they consume the stricter agreement.
- **Replay**: backtests and re-probation answer lookups only from recorded trajectories; anything unrecorded is
  "unavailable". Model swaps re-certify multi-step work without touching live systems.

**Judgement capture** (`app/learning/judgement.py`, `/judgement`): what only the team knew, as an asset. Written
(handbook, with sources) and unwritten (rules from behaviour and from the mentor, with coverage, agreement and
whether they're proven), mentor "why" notes, exceptions mined from repeated disagreements ("you escalate these
even under the limit: 4 examples, right?"; confirming makes it a rule), and conflicts between rules. Exported as
Markdown or PDF. Curiosity asks one "why?" after a disagreement, within the etiquette budget.

**Decisions to outcomes** (`app/outcomes/insights.py`): a sixth rank, **Outcome owner**, above senior: certified
coverage of 40%+ and two weeks on track, then a manager signs. An owner finds what drives exceptions (config-driven
`insight_dimensions`, e.g. supplier) and proposes initiatives with a draft for a person to send; progress is reported
as the driver's exception rate before and since, nothing more.

**Supervisor console** (`/team`, `app/outcomes/capacity.py`): every Newt with its evidence line, a capacity plan at
the firm's risk limit with what-ifs at 1/2/5/10% (from `eval/stats.py`), what still needs people, and the role
redesign card: "you supervise 2 Newts carrying 64% of the work; you focus on these exceptions".

**Role packs** (`roles/*.json`, `RolePack`): a role is its task-type config plus a title, tagline and default
routines. First day starts with the role library; a manager hires a Newt for a role (`POST /role-packs/{id}/hire`,
or `app.admin.hire`). Industries come as packs, never code.

**Interface:** Home · Needs you · Team · Judgement · Report card · Setup. Home carries the evidence line ("certified
on 298 cases · wrong at most 2.1% · would carry 81%"); the Report card shows a real case worked step by step.

**Next iteration:** licences and insurance on the certified record; choosing a first industry; cross-firm priors
(opt-in).

## 18. Where people work, getting better safely, proven on whole processes

Three things Hone has that Newt lacked, each built Newt's way (evidence first, a person signs).

**Process replays** (`app/clock.py`, `app/sim/`, `eval/process.py`): certification covered single decisions; owner-level
work runs over days. A replay takes a past case as a process (it arrived; the team decided, replied, chased, closed;
the supplier's answer came days later in the thread) and reruns it with Newt in the team's place:
- One clock: every timestamp goes through `now()`, so simulated time moves only when the replay moves it, and weeks
  of waiting pass in milliseconds.
- The real pipeline (`live.predict_one`, policy, executor, follow-ups, chases) runs in a sandbox (a separate
  connection whose transaction is always rolled back); nothing survives a replay.
- The director answers Newt's actions like the firm's system and lets the recorded world happen at its recorded
  times. It never invents a reply; Newt only sees a thread reply once the clock has reached it.
- Scored against the team: decision, required evidence, policy, replied when they replied, chased when no reply
  came and not after one did. Handed back is its own honest outcome. The result is evidence beside the statistical
  gate in promotion requests, never instead of it.
- On the demo, the first replay found a real bug: a routine with a follow-up on approvals made Newt "chase" a
  supplier it had never written to. Follow-ups now need a message Newt sent.

**The improvement loop** (`learning/improve.py`, `eval/blast.py`): changes used to go live and be re-checked after.
Now every change (a rule taught, edited, accepted or retired; a live routine changed; a confirmed exception) is
replayed on past cases before it goes live: answer the suite as things stand, make the change in the sandbox, answer
again on the same recordings, and compare. The blast radius says what it fixes, what it breaks and what it moves,
with the cases. A mentor's change that breaks nothing goes live by itself; anything else waits for the mentor, who
sees the cases. Rules under test (status "testing") are invisible to agents. Routine changes replay whole processes.
The Judgement page keeps the change log. The suite over-represents the touched cases, so it says nothing about the
overall error bound: that is re-certified on the frozen record when the change goes live, as before.

**Newt where people work** (`app/channels/`): Slack, Teams or email, chosen per person, besides the app. Newt's
messages are still written, stored and timed by the colleague service and etiquette; a channel only delivers them,
with the app's own buttons (one card mapping onto `colleague.service.reply`). Taps and replies come back
authenticated (Slack signing secret with a five-minute window; Bot Framework token; a signed per-message reply
address plus the sender's own address for email) and run through the same code as the app. Moving to a channel
brings the latest waiting work along (five, not a flood); stale work is never sent. What leaves is the message Newt
wrote, never case inputs. `scripts/mock_chat.py` stands in for Slack in demos.

**Next iteration:** licences and insurance on the certified record; a first industry; a design partner's real
history (threads included), which is what makes process replays meaningful.

## 19. Open questions

- Which roles first?
- Voice provider and call UX.
- Desktop or browser client for show-me sessions.
- Pricing (per Newt per month, or per case).
- How the net-time measure is collected without scoring people.
- How much autonomy segmentation customers can understand.
