"""Newt by email: each message is an email to the person, and they answer by replying.

Replies go to a per-message address, newt+<message id>.<signature>@<inbound domain>; the signature is keyed with the
app secret, so only that email's recipient can answer that message. The inbound-parse webhook (any provider that
posts JSON) authenticates with a shared secret, and the reply must come from the person's own address. Quoted history
is stripped before anything is read; the rest is redacted like everything a person types to Newt.
"""

import hashlib
import hmac
import re
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

from sqlalchemy.orm import Session

from app.channels import ChannelError
from app.channels.cards import Card, plain_text
from app.config import get_settings
from app.models import Message, User

_ADDRESS = re.compile(r"newt\+([0-9a-f-]{36})\.([0-9a-f]{16})@", re.I)
_mailer: Callable[[EmailMessage], None] | None = None


def set_mailer(fn: Callable[[EmailMessage], None] | None) -> None:
    """Tests and the demo collect emails instead of sending them."""
    global _mailer
    _mailer = fn


def _sig(message_id: str) -> str:
    return hmac.new(get_settings().secret(), f"email-reply:{message_id}".encode(), hashlib.sha256).hexdigest()[:16]


def reply_address(message_id: str) -> str:
    return f"newt+{message_id}.{_sig(message_id)}@{get_settings().inbound_email_domain}"


def message_id_from(recipients: str) -> str | None:
    """The message an emailed reply answers, if its address is genuine."""
    for mid, sig in _ADDRESS.findall(recipients or ""):
        if hmac.compare_digest(_sig(mid.lower()), sig.lower()):
            return mid.lower()
    return None


def same_person(sender: str, user: User) -> bool:
    return parseaddr(sender or "")[1].lower() == (user.email or "").lower()


def _send(msg: EmailMessage) -> None:
    if _mailer is not None:
        _mailer(msg)
        return
    s = get_settings()
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise ChannelError(f"email: {type(exc).__name__}") from exc


class Email:
    name = "email"

    def _email(self, user: User, subject: str, body: str, reply_to: str | None = None) -> EmailMessage:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = get_settings().smtp_from, user.email, subject
        msg["Message-ID"] = make_msgid(domain=(get_settings().inbound_email_domain or "newt.local"))
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        return msg

    def deliver(self, session: Session, user: User, m: Message, card: Card) -> str:
        msg = self._email(user, card.title, plain_text(card), reply_address(m.id))
        _send(msg)
        return f"email:{msg['Message-ID']}"

    def answered(self, session: Session, user: User, m: Message, note: str) -> None:
        return None  # an email can't be changed once sent; Newt's answer arrives as its own email

    def say(self, session: Session, user: User, text: str, thread: str | None = None) -> None:
        _send(self._email(user, "Newt", text))
