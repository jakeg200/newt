"""The conversation between Newt and one person about one task type.

`refresh` is called whenever the thread is read (and by the worker). It is idempotent: dedupe keys mean nothing is
said twice, and etiquette decides when each message may appear. Answers flow back through the existing paths:
a decision on a case is the person's action on it (so the sealed prediction is revealed and scored), a lesson is a
lesson, a rule is a rule (versioned, re-predicted, re-certified), a question-bank answer joins the questionnaire.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context import utc
from app.capture.redact import Redactor
from app.colleague import assist, career, curiosity, etiquette
from app.graduation import engine
from app.learning import teaching
from app.live import decide_draft, pending_drafts, score_cases
from app.manager import DEFAULT_INTERN_NAME
from app.models import (ActionLog, Agent, Apprenticeship, Audit, Case, HumanAction, Improvement, Message, Prediction, Rule,
                        TaskType, User,
                        utcnow)
from app.task_types import TaskTypeConfig

MAX_OPEN_QUESTIONS = 2  # never more than this many unanswered questions waiting at once
MENTOR_ROLES = ("mentor", "admin")


class ConversationError(ValueError):
    pass


def intern_name(session: Session, tt: TaskType) -> str:
    app_ = session.get(Apprenticeship, tt.apprenticeship_id)
    return (app_.settings or {}).get("intern_name") or DEFAULT_INTERN_NAME


def _label(s: Any) -> str:
    return str(s or "").replace("_", " ")


def out(m: Message) -> dict[str, Any]:
    return {"id": m.id, "direction": m.direction, "kind": m.kind, "body": m.body, "payload": m.payload, "status": m.status,
            "urgency": m.urgency, "at": utc(m.deliver_after) if m.direction == "newt" else utc(m.created_at),
            "answered_at": m.answered_at}


def _exists(session: Session, user: User, key: str) -> bool:
    return session.scalar(select(Message.id).where(Message.user_id == user.id, Message.dedupe_key == key).limit(1)) is not None


def _say(session: Session, user: User, tt: TaskType, kind: str, body: str, payload: dict[str, Any] | None = None, *,
         key: str | None = None, at: datetime | None = None, urgency: str = "normal", status: str = "open") -> Message:
    m = Message(task_type_id=tt.id, user_id=user.id, direction="newt", kind=kind, body=body, payload=payload or {},
                dedupe_key=key, deliver_after=at or utcnow(), urgency=urgency, status=status)
    session.add(m)
    return m


def _questions_today(session: Session, user: User, tt: TaskType, now: datetime, prefs: etiquette.Prefs) -> int:
    day = etiquette.local_day(now, prefs)
    rows = session.scalars(select(Message.deliver_after).where(Message.user_id == user.id, Message.task_type_id == tt.id,
                                                               Message.kind == "question", Message.deliver_after <= now))
    return sum(1 for at in rows if etiquette.local_day(utc(at), prefs) == day)


# The morning stand-up ---------------------------------------------------------------------

def _standup(session: Session, user: User, tt: TaskType, now: datetime) -> tuple[str, dict[str, Any]]:
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last = session.scalar(select(func.max(Message.deliver_after)).where(
        Message.user_id == user.id, Message.task_type_id == tt.id, Message.kind == "standup"))
    since = utc(last) if last else since
    handled = len({c for (c,) in session.execute(select(ActionLog.case_id).join(Case, Case.id == ActionLog.case_id).where(
        Case.task_type_id == tt.id, ActionLog.mode == "autonomous", ActionLog.status == "executed", ActionLog.created_at >= since))})
    drafts = len(pending_drafts(session, tt))
    handbacks = sum(1 for (out_,) in session.execute(select(Prediction.output).join(Case, Case.id == Prediction.case_id).where(
        Case.task_type_id == tt.id, Case.status == "open", Prediction.run_id.is_(None))) if ((out_ or {}).get("hand_back") or {}).get("hand_back"))
    audits = session.scalar(select(func.count()).select_from(Audit).where(Audit.task_type_id == tt.id, Audit.result.is_(None))) or 0
    ev = engine.evaluate(session, tt)
    finished = sum(1 for (at,) in session.execute(select(Case.completed_at).where(Case.task_type_id == tt.id, Case.completed_at.is_not(None)))
                   if utc(at) >= since)
    stats = {"handled": handled, "finished": finished, "drafts": drafts, "handbacks": handbacks, "audits": audits, "stage": tt.status,
             "rank": career.rank(session, tt), "agreement": ev.get("agreement_rate"), "ucb": ev.get("ucb"), "alpha": ev.get("alpha"),
             "coverage": ev.get("coverage")}
    parts = []
    if finished:
        parts.append(f"I finished {finished} {'case' if finished == 1 else 'cases'}" + (" since yesterday." if last else " so far."))
    if tt.status == "autonomous" and not finished:
        parts.append(f"I handled {handled} {'case' if handled == 1 else 'cases'} on my own" + (" since yesterday." if last else "."))
    elif tt.status == "supervised":
        parts.append(f"{drafts} {'draft is' if drafts == 1 else 'drafts are'} ready for you to approve.")
    else:
        parts.append(f"I'm shadowing. {round((ev.get('agreement_rate') or 0) * 100)}% in line with you so far.")
    if user.role in MENTOR_ROLES:
        if handbacks:
            parts.append(f"{handbacks} {'case needs' if handbacks == 1 else 'cases need'} your call.")
        if audits:
            parts.append(f"{audits} spot {'check' if audits == 1 else 'checks'} waiting.")
    if not any(stats[k] for k in ("handled", "finished", "drafts", "handbacks", "audits")) and tt.status != "shadow":
        parts.append("Nothing needs you yet.")
    return " ".join(parts), stats


def status_line(session: Session, user: User, tt: TaskType, messages: list[dict[str, Any]]) -> str:
    """What Newt is doing right now, in one line, like a colleague's status."""
    waiting = sum(1 for m in messages if m["direction"] == "newt" and m["status"] == "open" and m["kind"] not in ("delivery",))
    if waiting:
        return f"{waiting} {'thing is' if waiting == 1 else 'things are'} waiting on you."
    running = session.scalar(select(func.count()).select_from(ActionLog).join(Case, Case.id == ActionLog.case_id).where(
        Case.task_type_id == tt.id, ActionLog.exec_status.in_(("queued", "running")))) or 0
    if running:
        return f"Finishing {running} {'action' if running == 1 else 'actions'} in your systems."
    if tt.status in ("shadow", "demoted"):
        return "Shadowing your work and taking notes."
    return "Things are running smoothly. No asks from you."


def _weekly(session: Session, tt: TaskType, now: datetime) -> tuple[str, dict[str, Any]]:
    from app.outcomes.kpis import outcomes

    o = outcomes(session, tt, now, weeks=2)
    this = o["weeks"][-1]
    n = this["completed_by_newt"]
    body = f"This week I finished {n} {'case' if n == 1 else 'cases'}"
    if this["share_by_newt"] is not None:
        body += f", {round(this['share_by_newt'] * 100)}% of the work"
    if this["hours_returned"]:
        body += f", giving back {this['hours_returned']} hours"
    body += "."
    misses = [k["label"] for k in o["kpis"] if k["on_track"] is False]
    hits = [k for k in o["kpis"] if k["on_track"] is True]
    if misses:
        body += f" Behind on: {', '.join(misses)}."
    elif hits:
        body += " Everything I'm measured on is on track."
    else:
        body += " Nothing to measure against yet."
    return body, {"kpis": o["kpis"], "simulated": o["simulated"], "rank": career.rank(session, tt)}


# Promotions ---------------------------------------------------------------------------------

def _promotion(session: Session, user: User, tt: TaskType) -> tuple[str, str, dict[str, Any]] | None:
    """A request to move up, sent to whoever may sign it, only when the evidence is there: a performance review."""
    if user.role in ("manager", "admin"):
        process_line, process = career.process_evidence(session, tt)
        owner = career.owner_ready(session, tt)
        if owner:
            return ("owner", (f"I'm carrying {round(owner['coverage'] * 100)}% of this role with certified evidence, and every goal has been "
                              f"on track for {career.OWNER_WEEKS_ON_TRACK} weeks. May I own '{owner['label']}' as an outcome? I'll find what "
                              "drives it, propose fixes for you to agree, and report the result every week." + process_line),
                    {**engine.evaluate(session, tt), "responsibility": "owner", "process": process})
        ready = career.senior_ready(session, tt)
        if ready:
            return ("senior", (f"I've passed {ready['audits_passed']} spot checks in a row since graduating. May I take on chasing "
                               "replies myself? I'll follow up politely when nothing has happened, and tell the team each time." + process_line),
                    {**engine.evaluate(session, tt), "responsibility": "follow_ups", "process": process})
    ev = engine.evaluate(session, tt)
    if tt.status in ("shadow", "demoted") and ev.get("eligible") and user.role in MENTOR_ROLES:
        return ("supervised", (f"{ev['errors_above']} mistakes in {ev['n_above']} cases I was sure about. At worst I'd be wrong "
                               f"{round(ev['ucb'] * 100, 1)}% of the time, under your {round(ev['alpha'] * 100)}% limit. "
                               "May I start drafting the work for you to approve?"), ev)
    if tt.status == "supervised" and user.role in ("manager", "admin"):
        grad = engine.last_graduation(session, tt)
        done = engine.supervised_cases(session, tt, utc(grad.signed_at) if grad else None)
        if done >= engine.SUPERVISED_BEFORE_AUTONOMY and ev.get("eligible"):
            return ("autonomous", (f"{done} practice cases approved and my error bound is still {round(ev['ucb'] * 100, 1)}%. "
                                   "May I handle the routine cases on my own? Anything unusual still comes back to the team."), ev)
    return None


# Improvements ----------------------------------------------------------------------------------

def tell_improvement(session: Session, tt: TaskType, imp: Improvement, *, live: bool) -> Message:
    """The result of testing a change, to the mentor. Live: it broke nothing, so it's in use. Otherwise: the cases it
    would change, and their call."""
    from app.eval import blast

    mentor = session.get(User, session.get(Apprenticeship, tt.apprenticeship_id).mentor_id)
    user = session.get(User, imp.proposed_by) if imp.proposed_by else mentor
    if user is None or user.role not in MENTOR_ROLES:
        user = mentor
    b = imp.blast or {}
    what = imp.summary
    if live:
        body = f"{what}. {blast.sentence(b)} So it's live, and I'm re-checking my recent answers with it."
        kind, status = "ack", "done"
    elif imp.source == "mentor":
        body = (f"Before I use it: {what}. {blast.sentence(b)} Your team decided those {b.get('broke', 0)} differently. "
                "Use it anyway?")
        kind, status = "improvement", "open"
    else:
        body = f"I'd like to change how I work. {what}. {blast.sentence(b)} Shall I?"
        kind, status = "improvement", "open"
    when = etiquette.deliver_at(utcnow(), etiquette.prefs_from(user.preferences), kind="work")
    m = _say(session, user, tt, kind, body, {"improvement_id": imp.id, "blast": b, "summary": what},
             key=f"improvement:{imp.id}", at=when, status=status)
    session.commit()
    return m


# Refresh --------------------------------------------------------------------------------------

def _settle_stale(session: Session, user: User, tt: TaskType) -> None:
    """Work dealt with elsewhere (Needs you, the source system) is marked done so the thread stays true."""
    for m in session.scalars(select(Message).where(Message.user_id == user.id, Message.task_type_id == tt.id,
                                                   Message.status == "open", Message.kind.in_(("draft", "handback", "question")))):
        pid = m.payload.get("prediction_id")
        if m.kind == "draft" and not session.scalar(select(ActionLog.id).where(ActionLog.prediction_id == pid, ActionLog.status == "pending").limit(1)):
            m.status = "done"
        elif m.kind == "handback" or m.payload.get("type") == "case":
            case = session.get(Case, (m.payload.get("case") or {}).get("id"))
            if case is None or case.status != "open":
                m.status = "done"


def _reschedule(session: Session, user: User, tt: TaskType, now: datetime, prefs: etiquette.Prefs) -> None:
    """Messages waiting for working hours follow the person's current preferences: if they've opened up their
    hours, what was held back arrives now rather than at the old time."""
    for m in session.scalars(select(Message).where(Message.user_id == user.id, Message.task_type_id == tt.id,
                                                   Message.status == "open", Message.deliver_after > now)):
        when = etiquette.deliver_at(now, prefs, kind="question" if m.kind == "question" else "work",
                                    urgency=m.urgency, asked_today=_questions_today(session, user, tt, now, prefs))  # type: ignore[arg-type]
        if when < utc(m.deliver_after):
            m.deliver_after = when


def refresh(session: Session, user: User, tt: TaskType, now: datetime | None = None) -> None:
    now = now or utcnow()
    prefs = etiquette.prefs_from(user.preferences)
    _settle_stale(session, user, tt)
    _reschedule(session, user, tt, now, prefs)

    day = etiquette.local_day(now, prefs)
    key = f"standup:{tt.id}:{day}"
    if etiquette.working(now, prefs) and not _exists(session, user, key):
        body, stats = _standup(session, user, tt, now)
        _say(session, user, tt, "standup", body, {"stats": stats}, key=key, at=now, status="done")

    promo = _promotion(session, user, tt)
    if promo:
        to, body, ev = promo
        key = f"promotion:{tt.id}:{to}:{tt.status}"
        if not _exists(session, user, key):
            from app.outcomes.kpis import outcomes

            kpis = [k for k in outcomes(session, tt, now, weeks=2)["kpis"] if k["this_week"] is not None][:3]
            _say(session, user, tt, "promotion", body, {"to": to, "rank": career.rank(session, tt), "ucb": ev.get("ucb"), "alpha": ev.get("alpha"),
                                                        "n_above": ev.get("n_above"), "errors_above": ev.get("errors_above"),
                                                        "coverage": ev.get("coverage"), "kpis": kpis, "responsibility": ev.get("responsibility")},
                 key=key, at=etiquette.deliver_at(now, prefs, kind="work"))

    if user.role in ("manager", "admin") and career.rank(session, tt) == "owner" and etiquette.working(now, prefs):
        from app.outcomes import insights

        idea = insights.propose(session, tt, intern_name(session, tt))
        if idea and not _exists(session, user, f"initiative:{tt.id}:{idea['key']}"):
            _say(session, user, tt, "initiative", f"{idea['why']} Shall I take this on?",
                 {**idea, "type": "initiative", "options": ["yes", "no"]}, key=f"initiative:{tt.id}:{idea['key']}", at=now)

    local = now.astimezone(etiquette.ZoneInfo(prefs.timezone))
    last_workday = max(prefs.workdays) if prefs.workdays else 4
    if etiquette.working(now, prefs) and local.weekday() == last_workday and local.hour >= 15:
        key = f"weekly:{tt.id}:{local.isocalendar()[0]}-{local.isocalendar()[1]}"
        if not _exists(session, user, key):
            body, payload = _weekly(session, tt, now)
            _say(session, user, tt, "weekly", body, payload, key=key, at=now, status="done")

    if user.role not in MENTOR_ROLES:
        session.commit()
        return

    for c in curiosity.work_items(session, tt):
        if not _exists(session, user, c.dedupe_key):
            _say(session, user, tt, c.kind, c.body, c.payload, key=c.dedupe_key, at=etiquette.deliver_at(now, prefs, kind="work"))

    waiting = session.scalar(select(func.count()).select_from(Message).where(
        Message.user_id == user.id, Message.task_type_id == tt.id, Message.kind == "question", Message.status == "open")) or 0
    asked = _questions_today(session, user, tt, now, prefs)
    room = min(MAX_OPEN_QUESTIONS - waiting, prefs.questions_per_day - asked)
    if room > 0 and etiquette.working(now, prefs):
        for c in curiosity.questions(session, tt):
            if room <= 0:
                break
            if _exists(session, user, c.dedupe_key):
                continue
            _say(session, user, tt, "question", c.body, {**c.payload, "value": c.value}, key=c.dedupe_key, at=now)
            room -= 1
    session.commit()


def thread(session: Session, user: User, tt: TaskType, now: datetime | None = None, limit: int = 120) -> list[dict[str, Any]]:
    now = now or utcnow()
    refresh(session, user, tt, now)
    rows = session.scalars(select(Message).where(Message.user_id == user.id, Message.task_type_id == tt.id,
                                                 Message.deliver_after <= now).order_by(Message.deliver_after, Message.created_at))
    return [out(m) for m in list(rows)[-limit:]]


# People talking to Newt -------------------------------------------------------------------------

def post(session: Session, user: User, tt: TaskType, text: str, now: datetime | None = None) -> list[dict[str, Any]]:
    """Someone says something to Newt. Their words are redacted before they're stored."""
    now = now or utcnow()
    text = text.strip()
    if not text:
        raise ConversationError("say something first")
    mine = Message(task_type_id=tt.id, user_id=user.id, direction="person", kind="chat", body=Redactor()(text),
                   status="done", deliver_after=now, created_at=now)
    session.add(mine)
    intern = intern_name(session, tt)
    kind = assist.intent(text)
    if kind == "rule":
        if user.role not in MENTOR_ROLES:
            reply = _say(session, user, tt, "ack", "Rules come from my mentor, so they can check them against how the work is done. "
                                                    "I've noted it; ask them to send it to me.", at=now, status="done")
        else:
            from app.learning import improve

            imp = improve.propose(session, tt, user, "add_rule", text=Redactor()(text))
            decision = session.get(Rule, imp.rule_id).decision
            body = (f"Got it: when that comes up, choose {_label(decision)}. " if decision else "Got it. ")
            reply = _say(session, user, tt, "ack", body + "Before I use it, I'm testing it on past cases to see what it changes.",
                         {"rule_id": imp.rule_id, "improvement_id": imp.id}, at=now, status="done")
    elif kind == "status":
        body, stats = _standup(session, user, tt, now)
        reply = _say(session, user, tt, "standup", body, {"stats": stats}, at=now, status="done")
    else:
        result = assist.run_task(session, tt, text, now, intern)
        reply = _say(session, user, tt, "delivery", result["summary"], {**result, "request": Redactor()(text)}, at=now)
    session.commit()
    return [out(mine), out(reply)]


def _decide_case(session: Session, user: User, tt: TaskType, case_id: str, decision: str, now: datetime) -> None:
    task = TaskTypeConfig.model_validate(tt.config)
    if decision not in task.decision:
        raise ConversationError(f"decision must be one of {task.decision}")
    case = session.get(Case, case_id)
    if case is None or case.task_type_id != tt.id:
        raise ConversationError("case not found")
    session.add(HumanAction(case_id=case.id, action_type="decision", acted_at=now, source="conversation",
                            source_ref=f"conversation:{case.id}", match_method="explicit", payload={"decision": decision, "via": "conversation"}))
    case.status = "decided"
    session.commit()
    score_cases(session, [case.id])


def reply(session: Session, user: User, message_id: str, action: str, value: str | None = None, note: str | None = None,
          now: datetime | None = None) -> list[dict[str, Any]]:
    """Someone answers one of Newt's messages with a tap (or a few words)."""
    now = now or utcnow()
    m = session.get(Message, message_id)
    if m is None or m.user_id != user.id or m.direction != "newt":
        raise LookupError("message not found")
    if m.status not in ("open",) and not (m.kind == "delivery" and action == "feedback"):
        raise ConversationError("this has already been dealt with")
    tt = session.get(TaskType, m.task_type_id)
    p = m.payload
    said: list[Message] = []
    mentor_only = action in ("decide", "approve", "reject", "lesson", "answer", "chase")
    if mentor_only and user.role not in MENTOR_ROLES:
        raise PermissionError("only the mentor can answer this")

    if action == "dismiss":
        m.status = "dismissed"
    elif action == "decide":  # a case question or a hand-back: the answer is the person's decision on the case
        _decide_case(session, user, tt, p["case"]["id"], value or "", now)
        if m.kind == "question" and p.get("type") == "case":
            pred = session.get(Prediction, p["prediction_id"])
            guess = (pred.output or {}).get("decision") if pred else None
            said.append(_say(session, user, tt, "ack", "Thanks, that's what I'd have done." if guess == value
                             else f"Thanks. I'd have said {_label(guess)}, so that's a useful lesson.", at=now, status="done"))
        else:
            said.append(_say(session, user, tt, "ack", "Thanks, done. I'll learn from how you handled it.", at=now, status="done"))
    elif action == "approve":
        decide_draft(session, user, p["prediction_id"], approve=True)
        said.append(_say(session, user, tt, "ack", "Sent. Thanks for checking.", at=now, status="done"))
    elif action == "reject":
        decide_draft(session, user, p["prediction_id"], approve=False, decision=value)
        said.append(_say(session, user, tt, "ack", f"Understood: {_label(value)}. I'll learn from that.", at=now, status="done"))
    elif action == "lesson":
        r = teaching.record_lesson(session, user, p["prediction_id"], value or "", note=note)
        said.append(_say(session, user, tt, "ack", r["effect"], at=now, status="done"))
    elif action == "answer":
        if not (value or "").strip():
            raise ConversationError("type an answer first")
        if p.get("type") == "why":
            from app.models import Lesson

            lesson = session.get(Lesson, p["lesson_id"])
            if lesson is not None:
                lesson.note = Redactor()(value)[:2000]
            said.append(_say(session, user, tt, "ack", "Got it. That's in my judgement notes now, and I'll look for it in similar cases.",
                             at=now, status="done"))
        else:
            from app.orientation.service import save_answers

            save_answers(session, user, p["team"], {p["key"]: Redactor()(value)})
            said.append(_say(session, user, tt, "ack", "Thanks, I've written that into my notes for the handbook.", at=now, status="done"))
    elif action == "confirm" and m.kind == "improvement":
        if user.role not in MENTOR_ROLES:
            raise PermissionError("only the mentor can change how Newt works")
        from app.learning import improve

        imp = session.get(Improvement, p["improvement_id"])
        try:
            if value == "yes":
                improve.promote(session, user, imp, keep_anyway=True)  # they've seen the cases it changes
                said.append(_say(session, user, tt, "ack", "Done, I'm using it from now on, and re-checking my recent answers with it.",
                                 at=now, status="done"))
            else:
                improve.reject(session, user, imp)
                said.append(_say(session, user, tt, "ack", "Dropped. I'll keep working the way I was.", at=now, status="done"))
        except improve.ImproveError as exc:
            said.append(_say(session, user, tt, "ack", f"I couldn't: {exc}", at=now, status="done"))
    elif action == "confirm" and p.get("type") == "initiative":
        from app.outcomes import insights

        insights.accept(session, user, tt, {k: v for k, v in p.items() if k not in ("answer", "type")}, value == "yes")
        said.append(_say(session, user, tt, "ack", (f"Great. Here's a draft for whoever owns that relationship to send: \"{p['draft']}\" "
                                                     "I'll track the rate every week and tell you what changed.") if value == "yes"
                         else "Understood, I'll leave that one.", at=now, status="done"))
    elif action == "confirm":
        if user.role not in MENTOR_ROLES:
            raise PermissionError("only the mentor can confirm how the team decides")
        if value == "yes":
            from app.learning import improve

            imp = improve.propose(session, tt, user, "add_rule", text=p["text"], signal="exception",
                                  targets=p.get("case_ids", []))
            said.append(_say(session, user, tt, "ack", "Thank you. I'm testing it on past cases first, then it becomes a rule.",
                             {"rule_id": imp.rule_id, "improvement_id": imp.id}, at=now, status="done"))
        else:
            said.append(_say(session, user, tt, "ack", "Understood, I won't treat that as a rule.", at=now, status="done"))
    elif action == "sign":
        try:
            if p["to"] in ("senior", "owner"):
                career.grant(session, user, tt, p.get("responsibility") or ("owner" if p["to"] == "owner" else "follow_ups"))
            else:
                engine.sign(session, tt, user, p["to"])
        except (PermissionError, engine.GraduationError, career.CareerError) as exc:
            raise ConversationError(str(exc)) from exc
        title = career.TITLES[career.rank(session, tt)]
        said.append(_say(session, user, tt, "ack", f"Thank you! I'm a {title.lower()} now and I won't let you down. "
                                                   "You'll see everything I do in the morning stand-up.",
                         {"mood": "graduated", "rank": career.rank(session, tt)}, at=now, status="done"))
    elif action in ("retry", "chase"):
        from app.execution import service as execution

        if action == "retry":
            if user.role not in MENTOR_ROLES:
                raise PermissionError("only the mentor can answer this")
            execution.retry(session, p["retry"])
            said.append(_say(session, user, tt, "ack", "Trying again now. I'll let you know how it goes.", at=now, status="done"))
        else:
            case = session.get(Case, p["case"]["id"])
            row = execution.chase(session, case) if case else None
            session.commit()
            said.append(_say(session, user, tt, "ack", "Chasing it now." if row is not None and row.status != "blocked"
                             else "I couldn't send a follow-up for this one; it's over to you.", at=now, status="done"))
    elif action == "feedback":
        p = {**p, "feedback": {"value": value, "note": Redactor()(note) if note else None, "at": now.isoformat()}}
        m.payload = p
        if value == "redo":
            result = assist.run_task(session, tt, p.get("request", ""), now, intern_name(session, tt), feedback=note)
            said.append(_say(session, user, tt, "delivery", result["summary"], {**result, "request": p.get("request", "")}, at=now))
        else:
            said.append(_say(session, user, tt, "ack", "Great, I'll keep doing it that way.", at=now, status="done"))
    else:
        raise ConversationError(f"unknown action {action!r}")

    if action != "feedback" and m.status == "open":
        m.status = "answered"
    m.answered_at = now
    m.payload = {**m.payload, "answer": {"action": action, "value": value}}
    session.commit()
    return [out(x) for x in [m, *said]]


def tick(session: Session, now: datetime | None = None) -> int:
    """Refresh every person's threads (the worker calls this now and then), so messages are waiting before anyone looks."""
    count = 0
    for user, tt in session.execute(select(User, TaskType).join(Agent, Agent.org_id == User.org_id)
                                    .join(Apprenticeship, Apprenticeship.agent_id == Agent.id)
                                    .join(TaskType, TaskType.apprenticeship_id == Apprenticeship.id)).all():
        refresh(session, user, tt, now)
        count += 1
    return count
