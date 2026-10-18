"""One clock for the whole app.

Every timestamp goes through `now()` (via `models.utcnow`). In production it's the real time. A process replay runs
inside `simulated(start)`, where time only moves when the replay moves it: weeks of waiting for replies and
follow-ups pass in milliseconds, and every job, follow-up and message lands at the right simulated moment.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SimClock:
    t: datetime

    def advance_to(self, t: datetime) -> None:
        """Skip ahead to t. Time never runs backwards."""
        if t > self.t:
            self.t = t


_sim: ContextVar[SimClock | None] = ContextVar("sim_clock", default=None)


def now() -> datetime:
    clock = _sim.get()
    return clock.t if clock is not None else datetime.now(timezone.utc)


def simulating() -> bool:
    return _sim.get() is not None


@contextmanager
def simulated(start: datetime) -> Iterator[SimClock]:
    clock = SimClock(start if start.tzinfo else start.replace(tzinfo=timezone.utc))
    token = _sim.set(clock)
    try:
        yield clock
    finally:
        _sim.reset(token)
