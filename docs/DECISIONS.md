# Decisions

Defaults taken so the build doesn't stop to ask. Change any of them by editing this file.

| Date | Decision | Why |
| --- | --- | --- |
| 2026-10-17 | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic for the backend | One language for ML and API (brief) |
| 2026-10-17 | Development database is a local SQLite file; production is Supabase Postgres (EU). Models use portable types (string UUIDs, JSON with a JSONB variant on Postgres) | No account or Docker needed to start; same migrations run on both |
| 2026-10-17 | pgvector and embeddings arrive with M3, Postgres only | Not needed before similar-case retrieval |
| 2026-10-17 | Auth: Supabase Auth JWTs in production. In `ENV=dev`, an `X-Dev-User` header names the acting user; it is refused in any other environment | Lets M0–M4 run without Supabase keys |
| 2026-10-17 | Allowed actions are generic verbs (`draft_reply`, `send_reply`, `set_status`, `set_field`, `route`), validated against a registry in code; the task-type config says which ones a task may use | Keeps industry words out of code while still whitelisting actions |
| 2026-10-17 | Task-type configs reject unknown keys | A typo in a config should fail loudly, not silently change scoring |
| 2026-10-17 | Synthetic cases are generated generically from each config (placeholder inputs, random decisions) | Enough to exercise the pipeline in M0; realistic fixtures come with M3 |
| 2026-10-17 | Background work uses a Postgres/SQLite `jobs` table polled by a worker, no Redis | Brief: one less service to run |
| 2026-10-17 | Model: `claude-opus-5-5`, adaptive thinking, JSON-schema structured output, streamed; effort `medium` for handbook drafting (configurable via `HANDBOOK_EFFORT`) | Opus 5.5's default effort; keeps a five-document draft inside the 2-minute bar. Raise to `high` if drafts miss rules |
| 2026-10-17 | Server-side refusal fallback (`fallbacks: "default"`) on every Claude call; the model that actually served is recorded | A false-positive refusal shouldn't stop onboarding, and the track record must name the real model |
| 2026-10-17 | Passages are labelled `<document>.<passage>` per team; questionnaire answers are `Q.<key>` | Short labels the model can cite reliably and people can read |
| 2026-10-17 | Handbook items with no valid source block approval; unknown labels are stripped on save | "Every rule links to its source passage" is enforced, not hoped for |
| 2026-10-17 | Handbook item ids come from a per-version counter and are never reused | Later lessons and audits will refer to rules by id |
| 2026-10-17 | Approved handbooks are frozen; changes start a revision (new draft version) | The approved version is what the agent was certified against |
| 2026-10-17 | Policy documents are stored unredacted; redaction applies to case data from M2 | They're company documents, and redacting them would remove escalation contacts the handbook needs |
| 2026-10-17 | Handbook drafting runs inside the request | Simple, and fine under 2 minutes; move to the jobs table if it grows |
| 2026-10-17 | Each connection belongs to one task type | Keeps "which task is this item?" out of code; a Gmail label or export per task type does the routing |
| 2026-10-17 | Personal data becomes keyed pseudonyms (`[EMAIL 3fa9c1]`), never stored raw; ids and addresses kept only as keyed hashes | Redact before storage, while keeping "this reply went to the sender" visible to the agent |
| 2026-10-17 | The matcher leaves ambiguous actions unmatched rather than guessing | A wrong match corrupts the track record; an unmatched one only costs coverage |
| 2026-10-17 | Unmatched actions are stored redacted and hashed, and retried when new cases arrive | Upload order and slow sources shouldn't lose evidence |
| 2026-10-17 | Decisions are inferred from actions through rules in the task-type config (`capture.decision_rules`) | Industry specifics stay in config; unknown actions are kept with no decision instead of being forced into one |
| 2026-10-17 | Gmail scope is `gmail.readonly`, filtered to one label; tokens are Fernet-encrypted with a key derived from `APP_SECRET` | Least privilege, and nothing is readable from a database dump alone |
| 2026-10-17 | Mail from before a Gmail connection was made is backtest; after that, live | Matches how shadowing starts: history first, then live |
| 2026-10-17 | Captured cases are visible to the mentor and admins only | It's the mentor's work; managers see aggregates (M6) |
| 2026-10-17 | Every context piece records when it existed; the time-travel guard checks all of them and scans the item, handbook and rules for the mentor's own words on the case | A leak must stop the run, not quietly inflate a track record |
| 2026-10-17 | The handbook and rules are standing knowledge (used whatever their date), but a rule learned from the case being predicted is a leak | The handbook is the agent's training; what the mentor taught on this exact case is the answer |
| 2026-10-17 | Similar-case retrieval is TF-IDF over redacted text, not embeddings (for now) | No extra service, works on SQLite, deterministic in tests. This replaces the earlier plan to add pgvector in M3 |
| 2026-10-17 | Built-in apprentice: `claude-opus-5-5`, 5 self-consistency samples, effort `medium`, cached system prompt | The brief's confidence method; caching cuts the repeated handbook to ~5% of input cost |
| 2026-10-17 | Without an API key the built-in agent is a nearest-past-cases baseline, labelled as such | Everything runs end to end offline, and real agents have a floor to beat |
| 2026-10-17 | An unknown or wrong critical field makes a case a disagreement, even with the right decision | The brief's agreement rule; graduation bounds rely on it |
| 2026-10-17 | Agent failures (errors, timeouts, invalid answers) are hand-backs, never agreements or errors in the bound | An agent can't improve its record by failing |
| 2026-10-17 | External agents: HTTPS only (HTTP localhost in dev), HMAC-SHA256-signed bodies, secret shown once and stored encrypted, private and link-local addresses refused | Vendors can verify us; endpoints can't be used to reach our own network |
| 2026-10-17 | Backtests select the most recent N decided history cases; earlier ones serve only as past cases | Every predicted case has history to learn from, as in live shadowing |
| 2026-10-17 | Jobs run in-process in development (`INLINE_WORKER`), in `python -m app.worker` in production | No extra process to run while building |
| 2026-10-17 | SQLite migrations run with foreign keys off | Table rebuilds on SQLite otherwise cascade-delete dependent rows |
| 2026-10-17 | Replies are judged only when the agent made the mentor's decision; a missing draft is "missing", never acceptable | A reply to the wrong decision isn't worth judging; leaving the reply out can't help the agent's score |
| 2026-10-17 | Judge: `claude-opus-5-5` at effort `medium`, offline word-overlap judge without a key; trusted at 20+ rated replies with 90%+ agreement | The brief's bar; the model choice is yours to change (`JUDGE_MODEL`) |
| 2026-10-17 | Lessons re-score in place: comparisons keep the original agreement plus the mentor's attribution; "I'd change my call" excludes the case | The raw score stays auditable, and the effective score reflects teaching |
| 2026-10-17 | "Both fine" implies the reply is fine; "Intern wrong" on a case where only the reply differed implies it isn't | Fewer taps, and more judge-agreement data |
| 2026-10-17 | Teaching queue = disagreements, then unsure (<70%), then ~1 in 10 agreed cases with a reply as spot checks | Ten minutes a day on what matters; spot checks stop the judge and the agreement figure from going unchecked |
| 2026-10-17 | Inferred rules are used only on cases after their evidence; mentor-written or mentor-edited rules are standing knowledge, never used on their own examples | No leaks through rules, while a rule the mentor states applies like the handbook |
| 2026-10-17 | Every rule change bumps the apprenticeship's rules version and re-predicts the backlog (50 cases, one sample each) | Shows the effect at once, at about $1 with Claude |
| 2026-10-17 | Offline rule inference: one- or two-word phrases at ≥90% precision and ≥5 cases, two-word phrases preferred | Readable rules, no model needed, and tests stay deterministic |
| 2026-10-17 | Confidence = mean of self-consistency and a forward-chained logistic regression, calibrated by isotonic regression; τ = lowest threshold with UCB95 ≤ α | The brief's method; forward chaining keeps the classifier from seeing later decisions |
| 2026-10-17 | Graduation evidence = latest backtest + all live scored predictions; bars: 150+ cases above τ, 50+ live, coverage ≥ 40% | The brief's default bars |
| 2026-10-17 | The mentor signs supervised; the manager signs autonomous (after 50+ supervised cases, no failed audit, bar still met) | The brief's stages; the accountable manager owns autonomy |
| 2026-10-17 | At signature, τ and the calibration are frozen on the task type, with up to 150 recent evidence cases as the frozen record | Live work and re-probation use exactly what was signed |
| 2026-10-17 | Demotion: to supervised when graduation evidence plus audits no longer clears α; to shadow when the last 50 audits' lower bound exceeds α, on drift, or on failed re-probation | The brief's rules, including why a 50-audit upper bound can't be used |
| 2026-10-17 | Agents never choose actions: actions come from the decision, fields and reply, then pass a policy (whitelist, sender-only replies, no links of any domain, no other addresses, named fields) | Inbound email is untrusted; a fooled agent still can't act outside the whitelist |
| 2026-10-17 | Autonomous actions are simulated (logged as executed) until production connectors exist | The trust machinery can be proven before anything reaches a customer's systems |
| 2026-10-17 | About 1 in 10 autonomously handled cases gets a blind audit (deterministic by case) | The brief's 5–10%; deterministic so it can't be gamed by retrying |
| 2026-10-17 | Model swaps, rule changes and newly approved handbooks trigger re-probation of graduated task types | A changed procedure is a changed agent |
| 2026-10-17 | The frozen record is the graduation evidence (up to 600 cases), not a 150-case sample; re-probation runs at concurrency 48 | Re-certification needs the same statistical power as graduation; time stays near 10 minutes |
| 2026-10-17 | "Both fine" alternatives and "I'd change my call" exclusions carry over to later predictions of the same case | The brief: the alternative is stored as acceptable |
| 2026-10-17 | Similar-case retrieval ignores tokens containing digits | Reference numbers identify one document; matching on them finds the referenced invoice rather than similar situations |
| 2026-10-17 | Only the task's allowed action types are planned; one blocked action stops the whole case and hands it back to the mentor | A status change without its reply is half done, and "actions blocked" should mean the policy stopped something |
| 2026-10-18 | Newt works like a colleague: the conversation is the main surface (stand-up, questions, drafts, hand-backs, tasks, promotions); the web app is its "HR file" | People shouldn't learn a tool; Newt fits how they already work. Design in docs/NEWT_DESIGN.md |
| 2026-10-18 | Colleague etiquette: work in working hours without a budget; questions rationed (default 5 a day, at most 2 open), never repeated; urgent out of hours only if allowed; held-back messages follow current preferences | No-admin rule: every interruption must earn its place |
| 2026-10-18 | Answers in conversation flow through existing paths: a case answer is the person's decision (source `conversation`), so the sealed prediction is revealed and scored; rules via `rules.write` plus re-predict and re-certify; question-bank answers into the questionnaire | One learning pipeline, one set of guarantees |
| 2026-10-18 | Voice and screen are allowed only as consented, opt-in sessions (show-me sessions redacted on device, steps not video); raw media never stored | Richer learning without surveillance; works in the EU |
| 2026-10-18 | Positioning: earned trust ("AI that earns its job"); a Newt is hired for a role with KPIs; first customers are traditional and mid-market firms, self-serve | Differentiates from outcome-owning enterprise agents (e.g. Hone): Newt earns every step on evidence |
| 2026-10-18 | Real execution through destinations: signed webhooks into the firm's system or Zapier/Make/n8n; actions refer to the source item, never personal data; simulated (and labelled) when nothing is connected | Keeps the privacy rules (we hold only redacted data) and is the most self-serve way to connect any system |
| 2026-10-18 | Finished means confirmed: a case is completed only when every action is confirmed; up to 3 tries with backoff, then handed back with the reason; the policy is re-checked when acting | Outcomes must be real, and an honest hand-back beats silent failure |
| 2026-10-18 | Career ladder new starter → intern → junior → graduate → senior; senior responsibilities (e.g. chasing on its own) requested by Newt after 3+ clean spot checks and granted by a manager | The USP: Newt keeps getting promoted on performance |
| 2026-10-18 | Routines per decision (which actions, follow-up days) proposed by Newt from history, agreed by the mentor; changing an approved routine re-certifies a graduated Newt | Agreeing how a new hire handles things; a changed procedure is a changed agent |
| 2026-10-18 | KPIs are generic metrics on confirmed completions (finished by Newt, share, hours to finish, backlog, hours returned, value); which ones and the targets live in task-type configs, with manager overrides | Industry specifics stay in config; outcomes, never people, are measured |
| 2026-10-18 | Any role, not one vertical; framed as an apprentice for every expert, not a replacement | Jake's decision; adoption depends on the experts wanting it |
| 2026-10-17 | Manager dashboard: hours returned use the manager's own minutes per case; history's time-to-decision is shown only as context | Time-to-decision is elapsed time, not effort, and would overstate hours |
| 2026-10-17 | Production auth: Supabase access tokens (HS256 secret or JWKS), email mapped to a provisioned user; no self-signup; accounts via `python -m app.admin` | The buyer controls who's in; no open registration on a system holding work data |
| 2026-10-17 | Demo and end-to-end material lives in `backend/demo/`, outside `app/` | It's accounts-payable specific; `app/` stays industry-free |
| 2026-10-17 | Hosting: Fly.io in Frankfurt (API and worker processes, migrations on release), Vercel for the web app, Supabase EU | The brief's EU hosting; one image for API and worker |
