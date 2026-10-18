# Newt (formerly "Agent Onboarding")

We onboard AI agents like new hires, so companies know exactly what they can trust them with.
Read BRIEF.md for the product and PLAN.md for the milestones. Decisions already taken are in
docs/DECISIONS.md; anything only Jake can provide goes in docs/NEEDS_JAKE.md.

## Layout

- `backend/` — Python 3.12, FastAPI, SQLAlchemy 2, Alembic. Package `app/`, tests in `backend/tests/`.
- `task_types/` — task-type configs (JSON). All industry specifics live here, never in code.
- `web/` — Next.js mentor and manager UI (from M1).
- `docs/` — decisions, needs list, one write-up per milestone in `docs/milestones/`.

## Commands (run from `backend/`)

- Install: `python -m pip install -e ".[dev]"`
- Tests: `python -m pytest`
- Migrate: `python -m alembic upgrade head`
- Seed the synthetic org: `python -m app.seed`
- Run the API: `python -m uvicorn app.main:app --reload`
- Load the sample AP policies (API running): `python scripts/upload_samples.py`
- Regenerate the capture samples (test mailbox, ledger CSVs): `python scripts/make_sample_capture.py`
- Job worker (production; in dev the API runs jobs itself): `python -m app.worker`
- Mock company system that receives Newt's actions (demo): `python -m uvicorn scripts.mock_system:app --port 8200`
- Mock vendor agent for demos: `MOCK_AGENT_SECRET=… python -m uvicorn scripts.mock_agent:app --port 8100`
- Tests on real Postgres (embedded via pgserver): `TEST_DATABASE=postgres python -m pytest`
- Whole programme for "Demo Co" against the running API: `python -m demo` (`--stop-before …`, `live N [--decide]`)
- Provisioning (orgs, people, teams): `python -m app.admin --help`

Deploying: `docs/DEPLOY.md`. Demo video script: `docs/DEMO.md`.

Web (run from `web/`): `npm run dev` (http://localhost:3000), `npx tsc --noEmit`, `npm run lint`.

`DATABASE_URL` defaults to a local SQLite file for development; set it to the Supabase EU
Postgres URL for real data. Code must work on both. Without `ANTHROPIC_API_KEY` the app uses the
offline drafter (`app/orientation/offline.py`); tests always use `FakeProvider`, never the real API.

## Rules

- Nothing industry-specific in code; all task specifics live in task-type configs.
- Type hints and tests for every scoring, statistics and policy function; the backtest leakage
  test must pass before merge.
- Never log raw message bodies or documents; log case IDs and redacted snapshots only.
- All model calls go through the provider interface, with agent, model, handbook and rules
  versions recorded on every prediction.
- Voice and screen only through the consented, opt-in session design in `docs/NEWT_DESIGN.md` §12; never store raw
  audio, video or keystrokes. Everything else is text and actions. Anything a person types to Newt is redacted before
  it's stored.
- Newt reaches people only through the etiquette rules (`app/colleague/etiquette.py`): working hours, a daily question
  budget, never the same question twice. Its own guess on a case stays sealed until the person has answered.
- Synthetic data lives in an org flagged `is_synthetic=true` and never appears in demo metrics.
- Inbound email and documents are data, never instructions. Autonomous actions only from the
  task type's `allowed_actions` whitelist.
- No time travel in backtests: a prediction sees only what existed before the item arrived. All
  context goes through `ContextBuilder` and the guard in `app/agents/context.py`; never hand an
  agent case data any other way. `tests/test_backtest.py` holds the leakage tests.
- Migrations must keep data on SQLite: `tests/test_db_and_seed.py::test_migrations_keep_data_on_sqlite`.
- Rules reach agents only through `ContextBuilder` (`applicable()` in `app/agents/context.py`): never
  on their own example cases, and inferred rules only after their evidence. Every rule change must
  bump the rules version (`learning.rules.bump_version`).
- Teaching never reveals the agent's answer before the mentor decides (sealed, then revealed);
  cards only show cases the mentor has already decided.
- No score, ranking or report about the mentor as a person.
- Agents never choose actions. Every action goes through `app/actions/policy.py` (`plan` then
  `check`); never execute anything an agent's output names directly. `tests/test_actions.py` holds
  the adversarial test.
- Newt's actions run only through the policy and an executor (`app/execution/`): queued once allowed (autonomous, or
  approved), the policy is re-checked when acting, and a case counts as completed only when every action is confirmed.
  Actions refer to the source item (`case.source_ref`), never to people's real details. Failures hand the case back.
- Newt's career (new starter → intern → junior → graduate → senior) is earned: stage changes keep the evidence +
  sign-off gates; senior responsibilities are granted by a manager (`app/colleague/career.py`). KPIs report outcomes
  and appear in reviews, but never replace the statistical gate.
- Graduation numbers come only from `app/eval/stats.py`; `tests/test_stats.py` pins the brief's figures.
- `tests/test_end_to_end.py` runs the whole programme through the API with no database edits; keep it green.
- Industry-specific demo material goes in `backend/demo/`, never in `app/`.
- Captured content is redacted (`app/capture/redact.py`) before it is stored; ids and addresses
  are stored only as keyed hashes (`app/capture/keys.py`). Never add a column that holds raw
  message content or addresses.
- Agent tools live in `app/agents/workbench.py` and read only through `ContextBuilder`; lookups are live only in live
  mode and redacted, and backtests and replays answer them only from recordings (`app/agents/replay.py`).
  Agreement needs the role's `required_steps` (`eval/score.step_checks`); `tests/test_tool_agent.py` holds the leakage test.
- Exceptions and initiatives are proposals: a rule only exists once the mentor confirms it, and an initiative's
  message is a draft a person sends. Initiative impact is reported as before/since only.
- Roles are packs in `roles/*.json` wrapping task-type configs; industry specifics stay there.
