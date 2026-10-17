# Needs Jake

Things only you can provide. The build continues against stand-ins until they arrive.

- [ ] `ANTHROPIC_API_KEY` in `backend/.env`. Without it, handbooks come from the offline keyword drafter, and M1's 2-minute bar can't be measured with Claude. The apprentice needs it from M3.
- [ ] Supabase project in an EU region: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET` in `backend/.env`
- [ ] A Gmail test account and a Google OAuth client (web application type, redirect URI `http://127.0.0.1:8000/oauth/google/callback`, Gmail API enabled): set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `backend/.env`. Until then Gmail is tested against a mocked Google only.
- [ ] `APP_SECRET` (a long random string) in `backend/.env` before any real data. It keys pseudonyms, match hashes and token encryption. Changing it later breaks matching against already-captured cases.
- [ ] Hosting accounts: Fly.io or Render (EU) for the API, Vercel for the web app (M6)
- [ ] A design partner's policy documents (5+) and 6–12 months of history for one task type (M1–M3)
