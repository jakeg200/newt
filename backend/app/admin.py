"""Provisioning: organisations, people and teams. Run on the server, not through the web app.

    python -m app.admin create-org "Acme Ltd"
    python -m app.admin add-user "Acme Ltd" sarah@acme.com "Sarah K" mentor
    python -m app.admin add-team "Acme Ltd" accounts_payable sarah@acme.com ../task_types/invoice_mismatch.json
    python -m app.admin list

Each person signs in with Supabase using the email given here; roles are mentor, manager or admin.
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Apprenticeship, Org, TaskType, User
from app.task_types import TaskTypeConfig, load_task_type

ROLES = ("mentor", "manager", "admin")


class AdminError(ValueError):
    pass


def create_org(session: Session, name: str, *, region: str = "eu", synthetic: bool = False) -> Org:
    if session.scalar(select(Org).where(Org.name == name)):
        raise AdminError(f"an organisation called {name!r} already exists")
    org = Org(name=name, data_region=region, is_synthetic=synthetic)
    session.add(org)
    session.flush()
    session.add(Agent(org_id=org.id, kind="built_in", name="Built-in apprentice", model="claude-opus-5-5", version="1"))
    session.commit()
    return org


def _org(session: Session, name: str) -> Org:
    org = session.scalar(select(Org).where(Org.name == name))
    if org is None:
        raise AdminError(f"no organisation called {name!r}")
    return org


def add_user(session: Session, org_name: str, email: str, name: str, role: str) -> User:
    if role not in ROLES:
        raise AdminError(f"role must be one of {', '.join(ROLES)}")
    email = email.strip().lower()
    if session.scalar(select(User).where(User.email == email)):
        raise AdminError(f"{email} already has an account")
    user = User(org_id=_org(session, org_name).id, email=email, name=name, role=role)
    session.add(user)
    session.commit()
    return user


def add_team(session: Session, org_name: str, team: str, mentor_email: str, config: TaskTypeConfig) -> TaskType:
    org = _org(session, org_name)
    mentor = session.scalar(select(User).where(User.email == mentor_email.strip().lower(), User.org_id == org.id))
    if mentor is None or mentor.role != "mentor":
        raise AdminError(f"{mentor_email} isn't a mentor in {org_name}")
    agent = session.scalar(select(Agent).where(Agent.org_id == org.id, Agent.kind == "built_in"))
    app_ = session.scalar(select(Apprenticeship).where(Apprenticeship.agent_id == agent.id, Apprenticeship.team == team))
    if app_ is None:
        app_ = Apprenticeship(agent_id=agent.id, mentor_id=mentor.id, team=team)
        session.add(app_)
        session.flush()
    if session.scalar(select(TaskType).where(TaskType.apprenticeship_id == app_.id, TaskType.name == config.name)):
        raise AdminError(f"{team} already has a task type called {config.name!r}")
    tt = TaskType(apprenticeship_id=app_.id, name=config.name, config=config.model_dump(mode="json"), config_hash=config.config_hash())
    session.add(tt)
    session.commit()
    return tt


def main(argv: list[str] | None = None) -> None:
    from app.db import get_session

    parser = argparse.ArgumentParser(prog="python -m app.admin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-org")
    p.add_argument("name")
    p.add_argument("--region", default="eu")
    p = sub.add_parser("add-user")
    p.add_argument("org")
    p.add_argument("email")
    p.add_argument("name")
    p.add_argument("role", choices=ROLES)
    p = sub.add_parser("add-team")
    p.add_argument("org")
    p.add_argument("team")
    p.add_argument("mentor_email")
    p.add_argument("config", type=Path)
    sub.add_parser("list")
    args = parser.parse_args(argv)

    session = next(get_session())
    try:
        if args.cmd == "create-org":
            print(f"created {create_org(session, args.name, region=args.region).name}")
        elif args.cmd == "add-user":
            u = add_user(session, args.org, args.email, args.name, args.role)
            print(f"added {u.email} as {u.role}")
        elif args.cmd == "add-team":
            tt = add_team(session, args.org, args.team, args.mentor_email, load_task_type(args.config))
            print(f"added task type {tt.name!r} to team {args.team}")
        else:
            for org in session.scalars(select(Org).order_by(Org.name)):
                print(json.dumps({"org": org.name, "synthetic": org.is_synthetic,
                                  "users": [f"{u.email} ({u.role})" for u in session.scalars(select(User).where(User.org_id == org.id))]}))
    except AdminError as exc:
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
