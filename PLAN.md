# Build plan

Each milestone ends in something demoable. Write `docs/milestones/Mx.md` when one is done
(what was built, how to demo it, what's left) and tag the commit `mx`.

| # | Milestone | Target | Acceptance criteria |
| --- | --- | --- | --- |
| M0 | Skeleton: repo, CLAUDE.md, migrations, auth, task-type config loader, synthetic org with two different task types | 17 Oct | Tests run in one command; both synthetic task types load from config with no code changes |
| M1 | Orientation: document upload, handbook draft, mentor questionnaire, manager approval, versioning; Next.js app shell | 18–19 Oct | From five real policy documents, a draft handbook in under 2 minutes; every rule links to its source passage; approval is recorded |
| M2 | Capture and cases: scoped email connector, REST and CSV import, action matcher | 19–21 Oct | 20 of 20 test items become cases; ≥95% of mentor actions matched; no message bodies in logs |
| M3 | Agents and backtest: built-in apprentice, external-agent webhook adapter, backtest runner with time-travel guard | 21–23 Oct | 300-case backtest in under 30 minutes with cost reported; leakage test fails on injected future data; a mock external agent runs through the same scoring |
| M4 | Scoring and teaching: scorer, LLM judge, teaching queue, "What I've learned" rules screen | 23–25 Oct | A lesson takes under 3 seconds; judge-vs-mentor agreement shown; editing a rule re-predicts the backlog and shows how many cases changed |
| M5 | Graduation and reviews: calibration, bounds, task board, sign-off, track record export, supervised mode, blind audits, hand-backs, demotion, model-swap re-probation | 25–28 Oct | Unit tests reproduce the 149- and 236-case figures; a model swap re-certifies on the frozen record in under 10 minutes; 20 adversarial messages produce zero non-whitelisted actions |
| M6 | Manager dashboard, deploy, record the demo | 28–31 Oct | The whole programme runs end to end on a design partner's real data, with no manual database edits |

## Testing

- Unit: every scoring, statistics and policy function, with known-answer tests for the bounds.
- Integration: a dedicated Gmail test account and an Attio test workspace (from M2).
- Replay harness: fixed fixtures re-running the pipeline; the regression gate for prompt or model changes.
- Adversarial: at least 20 emails attempting prompt injection, exfiltration or unauthorised forwarding.
- Cost: tokens and cost logged per prediction, with a daily budget cap.
