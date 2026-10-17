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
