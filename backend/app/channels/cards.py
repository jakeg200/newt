"""What a message looks like outside the app: its text, its buttons, and whether it wants a typed answer.

One mapping from message kinds to the same reply actions the web app uses (`colleague.service.reply`), so a tap in
Slack, Teams or an email reply does exactly what the same tap does in the app. Buttons carry only the message id, the
action and an option name: never case content.
"""

from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.models import Message


@dataclass(frozen=True)
class Button:
    label: str
    action: str
    value: str | None = None
    primary: bool = False


@dataclass
class Card:
    message_id: str
    title: str
    body: str
    buttons: list[Button] = field(default_factory=list)
    wants_text: str | None = None  # the reply action a typed answer becomes ("answer"), if any
    link: str = ""


def _label(option: str) -> str:
    return option.replace("_", " ").capitalize()


TITLES = {"question": "A question", "draft": "Ready for your OK", "handback": "Over to you", "followup": "No reply yet",
          "promotion": "A request", "initiative": "An idea", "improvement": "A change to how I work", "standup": "Stand-up",
          "weekly": "This week", "delivery": "Done", "ack": "", "chat": ""}


def buttons(m: Message) -> tuple[list[Button], str | None]:
    """The buttons for an open message, and the action a typed answer maps to."""
    p: dict[str, Any] = m.payload or {}
    if m.status != "open":
        return [], None
    if m.kind == "question":
        kind = p.get("type")
        if kind == "exception":
            return [Button("Yes, that's our rule", "confirm", "yes", True), Button("Not really", "confirm", "no")], None
        if kind in ("bank", "why"):
            return [Button("Not now", "dismiss")], "answer"
        action = "decide" if kind == "case" else "lesson"
        return [*(Button(_label(o), action, o) for o in p.get("options", [])), Button("Not now", "dismiss")], None
    if m.kind == "handback":
        out = [Button("Try again", "retry", primary=True)] if p.get("retry") else []
        return out + [Button(f"I'll {_label(o).lower()}" if p.get("retry") else _label(o), "decide", o) for o in p.get("options", [])], None
    if m.kind == "draft":
        return [Button("Approve", "approve", primary=True), *(Button(_label(o), "reject", o) for o in p.get("options", [])
                                                              if o != p.get("decision"))], None
    if m.kind == "followup":
        return [Button("Chase it", "chase", primary=True), Button("Leave it", "dismiss")], None
    if m.kind == "promotion":
        return [Button("Sign", "sign", primary=True), Button("Not yet", "dismiss")], None
    if m.kind == "initiative":
        return [Button("Take it on", "confirm", "yes", True), Button("Not now", "confirm", "no")], None
    if m.kind == "improvement":
        return [Button("Use it", "confirm", "yes", True), Button("Drop it", "confirm", "no")], None
    return [], None


def card_for(m: Message, intern: str = "Newt") -> Card:
    b, text = buttons(m)
    title = TITLES.get(m.kind, "")
    return Card(m.id, f"{intern}: {title}" if title else intern, m.body, b, text,
                f"{get_settings().web_url}/?message={m.id}")


def plain_text(card: Card) -> str:
    """The card as an email body: numbered choices to reply with, and the link."""
    lines = [card.body, ""]
    if card.buttons:
        lines.append("Reply with the number of your choice:")
        lines += [f"  {i}. {b.label}" for i, b in enumerate(card.buttons, start=1)]
        lines.append("")
    if card.wants_text:
        lines += ["Or just reply with your answer.", ""]
    lines.append(f"Open it in Newt: {card.link}")
    return "\n".join(lines)


def choice_from_text(card: Card, text: str) -> Button | None:
    """An emailed reply of '2' or 'Approve' picks that button."""
    first = text.strip().splitlines()[0].strip().rstrip(".").lower() if text.strip() else ""
    if first.isdigit() and 1 <= int(first) <= len(card.buttons):
        return card.buttons[int(first) - 1]
    return next((b for b in card.buttons if b.label.lower() == first), None)
