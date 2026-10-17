"""Seed the synthetic org: one mentor and manager per team, a built-in agent, and one
apprenticeship per task-type config, with generated cases. Generic: nothing here knows
what an invoice or a repair is; it reads the configs.

Run: python -m app.seed
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Agent, Apprenticeship, Case, HumanAction, Org, TaskType, User
from app.task_types import TaskTypeConfig, load_all

SYNTHETIC_ORG_NAME = "Synthetic Co"
CASES_PER_TASK_TYPE = 40
RNG_SEED = 7
START = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


def _field_value(rng: random.Random, name: str, spec, i: int):
    if spec.type == "enum":
        return rng.choice(spec.options) if spec.options else f"{name}_{rng.randint(1, 4)}"
    if spec.type == "number":
        return round(rng.uniform(10, 5000), 2)
    if spec.type == "boolean":
        return rng.random() < 0.5
    if spec.type == "date":
        return (START + timedelta(days=rng.randint(0, 200))).date().isoformat()
    if spec.type == "text":
        return f"synthetic {name} for case {i}"
    return f"{name.upper()}-{rng.randint(100, 999)}"


def _generate_cases(session: Session, task_type: TaskType, config: TaskTypeConfig, rng: random.Random) -> None:
    for i in range(CASES_PER_TASK_TYPE):
        received = START + timedelta(hours=7 * i + rng.randint(0, 5))
        case = Case(
            task_type_id=task_type.id,
            source_ref=f"synthetic://{task_type.name}/{i}",
            received_at=received,
            snapshot={inp: f"synthetic {inp} #{i}" for inp in config.inputs},
            is_backtest=True,
            status="decided",
        )
        session.add(case)
        session.flush()
        session.add(
            HumanAction(
                case_id=case.id,
                action_type="decision",
                payload={
                    "decision": rng.choices(config.decision, weights=[6] + [2] * (len(config.decision) - 1))[0],
                    "fields": {n: _field_value(rng, n, s, i) for n, s in config.fields.items()},
                    "text_outputs": {t: f"synthetic {t} for case {i}" for t in config.text_outputs},
                },
                acted_at=received + timedelta(minutes=rng.randint(5, 240)),
                source="synthetic",
            )
        )


def seed(session: Session) -> Org:
    """Idempotent: running twice leaves one synthetic org with one row per task type."""
    rng = random.Random(RNG_SEED)
    configs = load_all(get_settings().task_types_dir)

    org = session.scalar(select(Org).where(Org.name == SYNTHETIC_ORG_NAME, Org.is_synthetic.is_(True)))
    if org is None:
        org = Org(name=SYNTHETIC_ORG_NAME, is_synthetic=True)
        session.add(org)
        session.flush()

    manager = session.scalar(select(User).where(User.email == "manager@synthetic.test"))
    if manager is None:
        manager = User(org_id=org.id, role="manager", email="manager@synthetic.test", name="Morgan (manager)")
        session.add(manager)

    agent = session.scalar(select(Agent).where(Agent.org_id == org.id, Agent.kind == "built_in"))
    if agent is None:
        agent = Agent(org_id=org.id, kind="built_in", model="fake-provider", version="0")
        session.add(agent)
    session.flush()

    for key, config in configs.items():
        mentor_email = f"mentor+{key}@synthetic.test"
        mentor = session.scalar(select(User).where(User.email == mentor_email))
        if mentor is None:
            mentor = User(org_id=org.id, role="mentor", email=mentor_email, name=f"Mentor ({config.name})")
            session.add(mentor)
            session.flush()

        apprenticeship = session.scalar(
            select(Apprenticeship).where(Apprenticeship.agent_id == agent.id, Apprenticeship.team == key)
        )
        if apprenticeship is None:
            apprenticeship = Apprenticeship(agent_id=agent.id, mentor_id=mentor.id, team=key)
            session.add(apprenticeship)
            session.flush()

        task_type = session.scalar(
            select(TaskType).where(TaskType.apprenticeship_id == apprenticeship.id, TaskType.name == config.name)
        )
        if task_type is None:
            task_type = TaskType(
                apprenticeship_id=apprenticeship.id,
                name=config.name,
                config=config.model_dump(mode="json"),
                config_hash=config.config_hash(),
            )
            session.add(task_type)
            session.flush()
            _generate_cases(session, task_type, config, rng)
        elif task_type.config_hash != config.config_hash():
            # The synthetic org follows the configs on disk. Real orgs version config changes (M5).
            task_type.config = config.model_dump(mode="json")
            task_type.config_hash = config.config_hash()

    session.commit()
    return org


def main() -> None:
    from app.db import get_session

    session = next(get_session())
    org = seed(session)
    names = session.scalars(
        select(TaskType.name).join(Apprenticeship).join(Agent).where(Agent.org_id == org.id).order_by(TaskType.name)
    ).all()
    print(f"Seeded {org.name} (synthetic) with task types: {', '.join(names)}")


if __name__ == "__main__":
    main()
