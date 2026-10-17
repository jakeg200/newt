# Needs Jake

Things only you can provide. The build continues against stand-ins until they arrive.

- [ ] **A design partner's data**: their policy documents (5+), 6–12 months of history for one task type, a named mentor and manager. This is what M6's acceptance actually needs; everything runs on synthetic data until then.
- [ ] `ANTHROPIC_API_KEY` in `backend/.env`. Without it, handbooks come from the offline keyword drafter and the apprentice is the offline nearest-cases baseline, so the M1 (2 min), M3 (30 min) and M5 (10 min re-probation) timings can't be measured with Claude. A 300-case backtest is estimated at about $31 (Opus 5.5, 5 samples); the Backtest screen shows the estimate before you start.
- [ ] `APP_SECRET` (a long random string) before any real data. It keys pseudonyms, match hashes and token encryption. Changing it later breaks matching against already-captured cases.
- [ ] **A GitHub repository** for the code (Vercel deploys from it). Say the word and I'll push the branches.
- [ ] **Supabase** project in an EU region: database URL, project URL, anon key, JWT secret (docs/DEPLOY.md §1).
- [ ] **Fly.io** account for the API and worker, **Vercel** account for the web app (docs/DEPLOY.md §2–3).
- [ ] A Gmail test account and a Google OAuth client (web application type, Gmail API enabled), only if a design partner uses Gmail: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Until then Gmail is tested against a mocked Google only.
