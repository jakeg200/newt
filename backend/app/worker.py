"""The job worker: polls the jobs table and runs what it finds. No Redis.

Production: `python -m app.worker`. Development: the API starts an in-process worker thread
(INLINE_WORKER=true), so there's nothing extra to run.
"""

import threading
import time
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.backtest.runner import execute
from app.logs import get_logger
from app.models import Job, utcnow

log = get_logger("worker")

HANDLERS: dict[str, Callable[[Session, dict], object]] = {
    "backtest": lambda session, payload: execute(session, payload["run_id"]),
}


def claim(session: Session) -> Job | None:
    """Take the oldest queued job. The conditional update means two workers never take the same one."""
    for job in session.scalars(select(Job).where(Job.status == "queued", Job.run_at <= utcnow()).order_by(Job.run_at).limit(5)):
        result = session.execute(
            update(Job).where(Job.id == job.id, Job.status == "queued")
            .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1)
        )
        session.commit()
        if result.rowcount == 1:
            session.refresh(job)
            return job
    return None


def run_once(session: Session) -> bool:
    job = claim(session)
    if job is None:
        return False
    handler = HANDLERS.get(job.type)
    try:
        if handler is None:
            raise ValueError(f"no handler for job type {job.type!r}")
        handler(session, job.payload)
        job.status, job.error = "done", None
    except Exception as exc:
        session.rollback()
        job = session.get(Job, job.id)
        job.status, job.error = "failed", f"{type(exc).__name__}: {str(exc)[:300]}"
        log.exception("job %s failed", job.id)
    job.finished_at = utcnow()
    session.commit()
    return True


class InlineWorker:
    def __init__(self, maker: sessionmaker, interval_s: float = 1.0) -> None:
        self.maker, self.interval_s = maker, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="inline-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self.maker() as session:
                    worked = run_once(session)
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._stop.wait(self.interval_s)


def main() -> None:
    from app.db import get_engine

    maker = sessionmaker(bind=get_engine(), expire_on_commit=False)
    log.info("worker started")
    while True:
        with maker() as session:
            if not run_once(session):
                time.sleep(1.0)


if __name__ == "__main__":
    main()
