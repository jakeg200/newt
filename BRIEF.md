# Product brief

Full brief: "Agent Onboarding: MVP & YC Build Brief" (claude.ai doc). This is the part the code needs.

## What we build

Software that takes an AI agent through the onboarding a new hire gets — orientation, shadowing,
supervised practice, probation and reviews — on one team's real work, and produces a statistical
track record per task type that a manager signs. Guardrails say what an agent can't do; we prove
what it can.

Users: **mentor** (the team expert whose decisions set the standard, ~10 minutes a day),
**manager** (approves the handbook, signs graduations), **agent** (our built-in Claude apprentice
or an external agent called through a webhook).

## The programme

1. **Orientation** — draft an agent handbook from the team's documents plus a mentor
   questionnaire; least-privilege scopes and escalation contacts; the manager approves it.
2. **Shadowing** — backtest on months of history using only what was known at the time; then
   live sealed predictions scored against what the mentor actually did.
3. **Supervised practice** — the agent drafts, the mentor approves in one tap.
4. **Probation and graduation** — per task type, on a statistical bar, signed by the manager.
5. **Reviews** — blind audits, drift checks, promotion and demotion, re-certification.
6. **Model swaps** — a new model re-runs probation on the frozen record first.

## Task types

An item comes in, a person decides, the decision is recorded. Defined by config (see
`task_types/`): trigger, inputs, decision options, fields (critical or not), text outputs,
allowed actions, `alpha`, `min_cases`. Every agent returns `decision`, `fields`, `text_outputs`,
`rationale`, `missing_info`, `self_reported_confidence`.

## Scoring

- Decision: exact match (primary). Structured fields: per field after normalising; critical
  fields weigh most. Text: LLM judge ("would the mentor send this unchanged?"), trusted only once
  judge-vs-mentor agreement is above ~90%. Routing: exact match.
- Agreement = decision and critical fields match and text judged acceptable.
- Mentor attribution of each disagreement: `intern_wrong` (error + lesson), `both_fine`
  (agreement), `mentor_changed` (excluded), `couldnt_know` (should-have-handed-back example).

## Graduation rule

Confidence = self-consistency (5 samples) + a logistic-regression classifier, calibrated with
isotonic regression on held-out backtest cases. Choose the lowest threshold τ such that among
calibration cases with confidence ≥ τ, the one-sided 95% Clopper–Pearson upper bound
`Beta⁻¹(0.95; k+1, n−k)` on the error rate is ≤ α. Below τ the agent hands back. Coverage = share
above τ.

Known answers (α = 2%): 0 errors → 149 cases; 1 error → 236; 2 errors → 313.

Default bars: α = 2% for anything sent outside the company, 5% for structured fields; ≥150 cases
including ≥50 live; coverage ≥40%.

Stages: shadow → supervised (bar met + mentor signs) → autonomous (50+ supervised cases, no failed
audit, manager signs; blind audits on 5–10%) → demoted (to supervised if the upper bound on
hold-out plus post-graduation audits exceeds α; to shadow if the lower bound on the last 50 audits
exceeds α, on input drift, or on a failed regression after a model or procedure change).

Hand-back when confidence < τ, the item is out of distribution, or a hard rule fires.

## Non-goals for the MVP

Screen, desktop, audio or video capture; industry-specific features or custom builds; billing,
SOC 2, Slack, mobile; fine-tuning frontier models; any score of the mentor as a person; autonomous
sending before 50 supervised cases.
