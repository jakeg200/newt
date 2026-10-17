# Deploying

Three pieces, all in the EU: **Supabase** (Postgres and sign-in), **Fly.io** (the API and the job
worker), **Vercel** (the web app). About an hour the first time. Every value below comes from your
own accounts; nothing here needs to be committed.

## 0. Before you start

- The code needs to be in a GitHub repository (Vercel deploys from it; Fly can deploy from your machine).
- Install the Fly CLI: <https://fly.io/docs/flyctl/install/>.

## 1. Supabase (database and sign-in)

1. Create a project in an EU region (Frankfurt, `eu-central-1`, matches `fly.toml`).
2. **Database URL:** Project Settings → Database → Connection string → URI, using the session pooler.
   It looks like `postgresql://postgres.xxxx:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres`.
   Use it as-is; the app adds the driver itself.
3. **Auth keys:** Project Settings → API. You need the project URL, the anon (public) key for the
   web app, and the JWT secret for the API. On projects using the newer asymmetric signing keys,
   the API reads them from the project URL instead, so the JWT secret isn't needed.
4. **Sign-in:** Authentication → Providers → Email: on. Authentication → URL Configuration: set the
   Site URL to your Vercel URL (step 3) and add it to the redirect URLs. Self-signup isn't used:
   people get accounts through `app.admin` (step 4).

## 2. Fly.io (API and worker)

From the repository root:

```
fly launch --no-deploy --copy-config      # keeps fly.toml; pick a unique app name
fly secrets set ^
  DATABASE_URL="postgresql://…" ^
  APP_SECRET="<a long random string; never change it once real data exists>" ^
  SUPABASE_URL="https://xxxx.supabase.co" ^
  SUPABASE_JWT_SECRET="…" ^
  ANTHROPIC_API_KEY="sk-ant-…" ^
  API_URL="https://<your-app>.fly.dev" ^
  WEB_URL="https://<your-web>.vercel.app" ^
  CORS_ORIGINS="[\"https://<your-web>.vercel.app\"]"
fly deploy
fly scale count app=1 worker=1
```

The deploy runs the database migrations first (`release_command`). `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` are only needed for Gmail capture; the Google OAuth redirect URI is
`https://<your-app>.fly.dev/oauth/google/callback`.

Check it: `https://<your-app>.fly.dev/health` should return `{"status":"ok"}`.

## 3. Vercel (web app)

1. New project from the GitHub repo, **root directory `web`**.
2. Environment variables:
   - `NEXT_PUBLIC_API_URL` = `https://<your-app>.fly.dev`
   - `NEXT_PUBLIC_SUPABASE_URL` = your Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = the anon key
3. Deploy. With the Supabase variables set, the app shows a sign-in page instead of the
   development user picker.

## 4. Accounts

People sign in with the email you give them here; there's no self-signup.

```
fly ssh console -C "python -m app.admin create-org 'Acme Ltd'"
fly ssh console -C "python -m app.admin add-user 'Acme Ltd' sarah@acme.com 'Sarah K' mentor"
fly ssh console -C "python -m app.admin add-user 'Acme Ltd' morgan@acme.com 'Morgan' manager"
fly ssh console -C "python -m app.admin add-team 'Acme Ltd' accounts_payable sarah@acme.com /srv/task_types/invoice_mismatch.json"
fly ssh console -C "python -m app.admin list"
```

A design partner's own task type is a new JSON file in `task_types/` (copy an existing one), deployed
like any other change.

## Notes

- The worker runs queued work (backtests, live predictions, re-probation). If it's scaled to zero,
  that work waits.
- Back up before migrations on real data: Supabase → Database → Backups.
- Locally, run the test suite against real Postgres with `TEST_DATABASE=postgres python -m pytest`
  (an embedded Postgres via `pgserver`).
