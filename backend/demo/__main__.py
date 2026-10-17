"""Run the onboarding programme against a running API, for a demo org you can click through.

    cd backend
    .venv\\Scripts\\python -m demo                           whole programme for "Demo Co"
    .venv\\Scripts\\python -m demo --stop-before graduate    leave a step to do on screen
                                                         (approve-handbook, graduate, autonomy, swap)
    .venv\\Scripts\\python -m demo live 15                   15 new invoices arrive now
    .venv\\Scripts\\python -m demo live 15 --decide          …and the mentor's system reports what they did

It provisions "Demo Co" (flagged synthetic) in the API's database, then drives everything else
through the HTTP API, waiting for the API's in-process worker between steps.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx
from sqlalchemy import func, select

from app.config import BACKEND_DIR, get_settings
from app.db import get_session
from app.models import Job
from demo.ap_data import live_items, mentor_actions, number_from
from demo.programme import STOPS, TEAM, StepError, provision, run

FEED = BACKEND_DIR.parent / ".demo-feed.json"  # the demo's REST push token; gitignored


def _feed(http: httpx.Client, mentor: dict) -> dict:
    """A REST connection for on-demand live items. Its token is shown once, so it's kept locally, per database."""
    db = hashlib.sha256(get_settings().database_url.encode()).hexdigest()[:16]  # not the URL: it may hold a password
    if FEED.exists():
        data = json.loads(FEED.read_text())
        if data.get("db") == db:
            return data
    tt = next(t for t in http.get("/task-types", headers=mentor).json() if t["team"] == TEAM)
    conn = http.post("/connections", json={"name": "Demo live feed", "provider": "rest", "task_type_id": tt["id"]}, headers=mentor).json()
    data = {"db": db, "id": conn["id"], "token": conn["push_token"]}
    FEED.write_text(json.dumps(data))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m demo")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "live"])
    parser.add_argument("count", nargs="?", type=int, default=15)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--stop-before", choices=STOPS)
    parser.add_argument("--decide", action="store_true", help="live: also send the mentor's decisions")
    parser.add_argument("--timeout", type=float, default=900, help="seconds to wait for queued work at each step")
    args = parser.parse_args()

    session = next(get_session())
    people = provision(session)

    def drain() -> None:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            session.expire_all()
            if not session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(("queued", "running")))):
                return
            time.sleep(0.5)
        raise SystemExit("timed out waiting for the API's worker; is the API running with INLINE_WORKER=true?")

    with httpx.Client(base_url=args.api, timeout=300) as http:
        try:
            http.get("/health").raise_for_status()
        except httpx.HTTPError:
            raise SystemExit(f"can't reach the API at {args.api}") from None
        if args.command == "live":
            feed = _feed(http, people.mentor)
            first = max(feed.get("next", 0), 1000)  # past the programme's own invoices and earlier live runs
            number_from(first)
            items = live_items(args.count)
            FEED.write_text(json.dumps({**feed, "next": first + len(items)}))
            auth = {"Authorization": f"Bearer {feed['token']}"}
            http.post(f"/capture/push/{feed['id']}", json={"items": items}, headers=auth).raise_for_status()
            drain()
            if args.decide:
                http.post(f"/capture/push/{feed['id']}", json={"actions": mentor_actions(items)}, headers=auth).raise_for_status()
                drain()
            print(f"{len(items)} invoices arrived" + (" and the mentor's decisions were reported" if args.decide else ""))
            return
        try:
            out = run(http, drain, people, log=print, stop_before=args.stop_before)
        except StepError as exc:
            raise SystemExit(f"stopped: {exc}") from None
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
