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
