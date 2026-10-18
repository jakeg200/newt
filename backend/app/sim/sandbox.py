"""A throwaway copy of the world for one replay.

The replay runs the real pipeline (predict, policy, executor, follow-ups), which commits as it goes. The sandbox is a
separate connection holding one outer transaction that is always rolled back; the session inside turns each commit
into a savepoint. Nothing a replay does survives it, on SQLite or Postgres.

SQLite needs the standard pysqlite recipe for savepoints (the driver's own transaction handling is switched off and
SQLAlchemy emits BEGIN itself), so the sandbox keeps its own engine per database rather than changing the app's.
Callers commit their own work before opening a sandbox: on SQLite only one connection may write at a time.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.db import normalise_url

_engines: dict[str, Engine] = {}


def _engine_for(url: str) -> Engine:
    url = normalise_url(url)
    if url in _engines:
        return _engines[url]
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _connect(dbapi_conn, _record) -> None:
            dbapi_conn.isolation_level = None  # let SQLAlchemy manage transactions, so SAVEPOINT works
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        @event.listens_for(engine, "begin")
        def _begin(conn) -> None:
            conn.exec_driver_sql("BEGIN")
    else:
        engine = create_engine(url, pool_pre_ping=True)
    _engines[url] = engine
    return engine


@contextmanager
def sandbox(session: Session) -> Iterator[Session]:
    """A session on the same database as `session` whose every change is rolled back at the end."""
    url = session.get_bind().url.render_as_string(hide_password=False)
    conn = _engine_for(url).connect()
    outer = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        outer.rollback()
        conn.close()
