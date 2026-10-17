"""Input drift: are recent live items still like the ones the agent graduated on?

Measured as the share of items whose closest earlier case is too dissimilar to learn from (the
same test hand-back uses). Drift is flagged when recent items are unfamiliar far more often than
the graduation record was; a graduated task type then goes back to shadow.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import ContextBuilder, utc
from app.graduation.engine import GRADUATED, demote, frozen_case_ids
from app.graduation.handback import OOD_SIMILARITY
from app.models import Case, DriftCheck, TaskType, utcnow

WINDOW = timedelta(days=30)
MIN_RECENT = 20
MARGIN = 0.15


def _unfamiliar(builder: ContextBuilder, case: Case) -> bool:
    as_of = utc(case.received_at)
    earlier = [cid for cid, d in builder.decided.items() if cid != case.id and d.decided_at < as_of]
    top = builder.index.top_k(case.id, earlier, 1)
    return not top or top[0][1] < OOD_SIMILARITY


def check(session: Session, tt: TaskType) -> DriftCheck:
    builder = ContextBuilder(session, tt)
    baseline_ids = frozen_case_ids(session, tt)
    baseline = [builder.cases[i] for i in baseline_ids if i in builder.cases]
    since = utcnow() - WINDOW
    recent = [c for c in builder.cases.values() if not c.is_backtest and utc(c.received_at) >= since]
    base_rate = sum(_unfamiliar(builder, c) for c in baseline) / len(baseline) if baseline else 0.0
    recent_rate = sum(_unfamiliar(builder, c) for c in recent) / len(recent) if recent else 0.0
    drifted = len(recent) >= MIN_RECENT and recent_rate > base_rate + MARGIN
    result: dict[str, Any] = {"baseline_cases": len(baseline), "baseline_unfamiliar": round(base_rate, 4),
                              "recent_cases": len(recent), "recent_unfamiliar": round(recent_rate, 4), "margin": MARGIN}
    row = DriftCheck(task_type_id=tt.id, drifted=drifted, result=result)
    session.add(row)
    session.commit()
    if drifted and tt.status in GRADUATED:
        demote(session, tt, "shadow", f"input drift: {recent_rate:.0%} of recent items are unlike anything seen (was {base_rate:.0%})", result)
    return row
