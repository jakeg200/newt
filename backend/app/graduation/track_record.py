"""The track record: one per task type, the thing a partner signs, an auditor reads and an
insurer prices. Exported as JSON and as a one-page PDF."""

from typing import Any

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.models import Agent, Apprenticeship, Audit, DriftCheck, GraduationEvent, Handbook, TaskType, User
from app.task_types import TaskTypeConfig


def _date(dt) -> str | None:
    return utc(dt).date().isoformat() if dt else None


def _note(evidence: dict[str, Any]) -> str | None:
    if "recertified" in evidence:
        verdict = "re-certified" if evidence["recertified"] else "failed re-certification"
        return f"{verdict} on the frozen record after {evidence.get('reason')}"
    return evidence.get("reason")


def build(session: Session, tt: TaskType) -> dict[str, Any]:
    from app.graduation.engine import evaluate, last_graduation

    task = TaskTypeConfig.model_validate(tt.config)
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    mentor = session.get(User, app_.mentor_id)
    agent = session.get(Agent, app_.agent_id)
    events = list(session.scalars(select(GraduationEvent).where(GraduationEvent.task_type_id == tt.id).order_by(GraduationEvent.signed_at)))
    grad = last_graduation(session, tt)
    basis = grad.evidence if grad else evaluate(session, tt)
    signoffs = {}
    for e in events:
        if e.signed_by and e.to_status in ("supervised", "autonomous"):
            signer = session.get(User, e.signed_by)
            signoffs["mentor" if e.to_status == "supervised" else "manager"] = {"name": signer.name if signer else None, "date": _date(e.signed_at)}
    audits = [a for a in session.scalars(select(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_not(None)))
              if not grad or utc(a.completed_at) >= utc(grad.signed_at)]
    drift = session.scalar(select(DriftCheck).where(DriftCheck.task_type_id == tt.id).order_by(DriftCheck.checked_at.desc()).limit(1))
    handbook = session.scalar(select(Handbook).where(Handbook.team == app_.team, Handbook.status == "approved").order_by(Handbook.version.desc()).limit(1))
    return {
        "task_type": {"name": task.name, "definition": task.trigger, "decisions": task.decision, "alpha": task.alpha},
        "status": tt.status,
        "mentor": mentor.name if mentor else None,
        "team": app_.team,
        "cases": {"backtest": basis.get("backtest_cases"), "live": basis.get("live_cases")},
        "agreement_rate": basis.get("agreement_rate"),
        "error_upper_bound_95": basis.get("ucb"),
        "tau": basis.get("tau"),
        "coverage": basis.get("coverage"),
        "hand_back_rate": basis.get("hand_back_rate"),
        "cases_above_tau": basis.get("n_above"),
        "errors_above_tau": basis.get("errors_above"),
        "audits": {"passed": sum(a.result == "pass" for a in audits), "total": len(audits)},
        "last_drift_check": {"date": _date(drift.checked_at), "drifted": drift.drifted} if drift else None,
        "versions": {"agent": agent.name or agent.kind, "model": agent.model, "agent_version": agent.version,
                     "handbook": handbook.version if handbook else None, "rules": app_.rules_version, "config_hash": tt.config_hash[:12]},
        "signoffs": signoffs,
        "history": [{"date": _date(e.signed_at), "from": e.from_status, "to": e.to_status,
                     "by": "system" if not e.signed_by else (session.get(User, e.signed_by).role if session.get(User, e.signed_by) else None),
                     "note": _note(e.evidence)} for e in events],
        "evaluated_at": basis.get("evaluated_at"),
    }


def _pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{x * 100:.{digits}f}%"


def _safe(text: str) -> str:
    """Core PDF fonts are Latin-1 only."""
    for a, b in (("–", "-"), ("—", "-"), ("→", "->"), ("τ", "tau"), ("α", "alpha"), ("’", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def pdf(record: dict[str, Any]) -> bytes:
    doc = FPDF(format="A4")
    doc.set_auto_page_break(True, margin=15)
    doc.add_page()
    doc.set_font("Helvetica", "B", 16)
    doc.cell(0, 10, "Agent track record", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    doc.set_text_color(90, 90, 90)
    doc.multi_cell(0, 5, _safe(f"{record['task_type']['name']}: {record['task_type']['definition']}"), new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(0, 0, 0)
    doc.ln(3)
    v = record["versions"]
    a = record["audits"]
    rows = [
        ("Status", record["status"]),
        ("Mentor and team", f"{record['mentor']}, {record['team'].replace('_', ' ')}"),
        ("Cases (backtest / live)", f"{record['cases']['backtest']} / {record['cases']['live']}"),
        ("Agreement rate", _pct(record["agreement_rate"])),
        ("Error upper bound (95%)", f"{_pct(record['error_upper_bound_95'], 2)} at alpha = {_pct(record['task_type']['alpha'], 0)}"),
        ("Confidence threshold (tau)", "-" if record["tau"] is None else f"{record['tau']:.3f}"),
        ("Coverage / hand-back rate", f"{_pct(record['coverage'], 0)} / {_pct(record['hand_back_rate'], 0)}"),
        ("Audits passed", f"{a['passed']} of {a['total']}"),
        ("Last drift check", "none yet" if not record["last_drift_check"] else
         f"{record['last_drift_check']['date']}, {'drift found' if record['last_drift_check']['drifted'] else 'clear'}"),
        ("Model and procedure version", f"{v['model']} {v['agent_version']}, handbook v{v['handbook']}, rules v{v['rules']}, config {v['config_hash']}"),
        ("Sign-offs", ", ".join(f"{k} {s['date']} ({s['name']})" for k, s in record["signoffs"].items()) or "none yet"),
    ]
    for key, value in rows:
        doc.set_font("Helvetica", "B", 10)
        doc.cell(65, 7, key)
        doc.set_font("Helvetica", "", 10)
        doc.multi_cell(0, 7, _safe(str(value)), new_x="LMARGIN", new_y="NEXT")
    if record["history"]:
        doc.ln(4)
        doc.set_font("Helvetica", "B", 11)
        doc.cell(0, 8, "History", new_x="LMARGIN", new_y="NEXT")
        doc.set_font("Helvetica", "", 9)
        for h in record["history"]:
            doc.multi_cell(0, 5, _safe(f"{h['date']}  {h['from']} -> {h['to']}  ({h['by']}){'  ' + h['note'] if h['note'] else ''}"),
                           new_x="LMARGIN", new_y="NEXT")
    doc.ln(4)
    doc.set_font("Helvetica", "I", 8)
    doc.set_text_color(110, 110, 110)
    doc.multi_cell(0, 4, "The error bound is a one-sided 95% Clopper-Pearson upper bound on disagreement with the mentor, "
                         "among cases the agent handles (confidence at or above tau). Cases below tau are handed back to a person.",
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(doc.output())
