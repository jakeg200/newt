from sqlalchemy import func, inspect, select

from app.db import Base, make_engine
from app.models import Agent, Apprenticeship, Case, HumanAction, Org, TaskType, User
from app.seed import CASES_PER_TASK_TYPE, seed


def test_migrations_create_every_model_table(db_url: str):
    engine = make_engine(db_url)
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    engine.dispose()
    assert tables == set(Base.metadata.tables)


def test_seed_creates_synthetic_org_with_two_task_types(session):
    org = seed(session)
    assert org.is_synthetic
    task_types = session.scalars(
        select(TaskType).join(Apprenticeship).join(Agent).where(Agent.org_id == org.id)
    ).all()
    assert {t.name for t in task_types} == {"Invoice mismatch under £5k", "Tenant repair request"}
    assert all(t.status == "shadow" for t in task_types)
    assert session.scalar(select(func.count()).select_from(Case)) == 2 * CASES_PER_TASK_TYPE
    # Every synthetic decision is one of its task type's own options.
    for t in task_types:
        actions = session.scalars(select(HumanAction).join(Case).where(Case.task_type_id == t.id)).all()
        assert actions and {a.payload["decision"] for a in actions} <= set(t.config["decision"])


def test_seed_is_idempotent(session):
    seed(session)
    seed(session)
    assert session.scalar(select(func.count()).select_from(Org)) == 1
    assert session.scalar(select(func.count()).select_from(TaskType)) == 2
    assert session.scalar(select(func.count()).select_from(Case)) == 2 * CASES_PER_TASK_TYPE
    assert session.scalar(select(func.count()).select_from(User)) == 3  # manager + two mentors
