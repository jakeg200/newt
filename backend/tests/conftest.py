import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ["ENV"] = "dev"  # before app imports read settings
os.environ["INLINE_WORKER"] = "false"  # tests run jobs explicitly, never against dev.db
os.environ["ANTHROPIC_API_KEY"] = ""  # tests never call the real API, even with a key in .env

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import BACKEND_DIR  # noqa: E402
from app.db import get_session, make_engine  # noqa: E402
from app.main import app  # noqa: E402


def migrate(url: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


_pg: dict = {}


def _postgres_url() -> str:
    """TEST_DATABASE=postgres runs every test on a real Postgres (embedded, via pgserver): the schema
    is migrated once into a template, and each test gets a fresh copy of it."""
    import uuid

    import pgserver
    from sqlalchemy import create_engine, text

    if "server" not in _pg:
        import tempfile

        _pg["server"] = pgserver.get_server(tempfile.mkdtemp(prefix="ao-pg-"), cleanup_mode="stop")
        base = _pg["server"].get_uri().replace("postgresql://", "postgresql+psycopg://")
        _pg["base"] = base.rsplit("/", 1)[0]
        admin = create_engine(f"{_pg['base']}/postgres", isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS ao_template"))
            conn.execute(text("CREATE DATABASE ao_template"))
        migrate(f"{_pg['base']}/ao_template")
        _pg["admin"] = admin
    name = f"t_{uuid.uuid4().hex[:12]}"
    with _pg["admin"].connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name} TEMPLATE ao_template"))
    return f"{_pg['base']}/{name}"


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    if os.environ.get("TEST_DATABASE") == "postgres":
        return _postgres_url()
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    migrate(url)
    return url


@pytest.fixture
def session(db_url: str) -> Iterator[Session]:
    engine = make_engine(db_url)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as s:
        yield s
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
