"""Redaction before storage.

Personal identifiers become stable pseudonyms like "[EMAIL 3fa9c1]": the same value always gets
the same pseudonym (keyed by APP_SECRET), so the agent can still tell that a reply went to the
original sender, but the value itself is never stored. Invoice, PO and ticket numbers are kept,
because decisions and matching depend on them.
"""

import hashlib
import hmac
import re
from collections import Counter
from dataclasses import dataclass, field

from app.config import get_settings

PLACEHOLDER = re.compile(r"\[(?:EMAIL|IBAN|CARD|SORTCODE|ACCOUNT|NINO|PHONE) [0-9a-f]{6}\]")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total, alt = total + n, not alt
    return total % 10 == 0


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


# (kind, pattern, optional validator, normaliser). Order matters: earlier kinds win.
_RULES: list[tuple[str, re.Pattern[str], object, object]] = [
    ("EMAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), None, str.lower),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"), None, lambda v: v.replace(" ", "")),
    ("CARD", re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])"), lambda v: 13 <= len(_digits(v)) <= 19 and _luhn_ok(_digits(v)), _digits),
    ("SORTCODE", re.compile(r"(?<![\w-])\d{2}-\d{2}-\d{2}(?![\w-])"), None, _digits),
    ("ACCOUNT", re.compile(r"(?i)\b(?:account(?: number| no\.?)?|a/c)[:#]? ?(?P<v>\d{6,10})\b"), None, _digits),
    ("NINO", re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b"), None, lambda v: v.replace(" ", "").upper()),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+\d{1,3}[ .-]?(?:\(0\)[ .-]?)?\d(?:[ .-]?\d){7,11}|0[1-9](?:[ .-]?\d){8,9})(?![\w-])"), None, _digits),
]


def pseudonym(kind: str, normalised: str) -> str:
    digest = hmac.new(get_settings().secret(), f"{kind}:{normalised}".encode(), hashlib.sha256).hexdigest()
    return f"[{kind} {digest[:6]}]"


@dataclass
class Redactor:
    """Redacts text and counts what it removed (counts only, never values)."""

    counts: Counter[str] = field(default_factory=Counter)

    def __call__(self, text: str | None) -> str:
        if not text:
            return text or ""
        for kind, pattern, valid, normalise in _RULES:
            def repl(m: re.Match[str], kind: str = kind, valid=valid, normalise=normalise) -> str:
                # A rule with a "v" group redacts just that part (e.g. the digits after "account no").
                group = "v" if "v" in m.re.groupindex else 0
                value = m.group(group)
                if PLACEHOLDER.fullmatch(value) or (valid and not valid(value)):
                    return m.group(0)
                self.counts[kind] += 1
                start, end = m.start(group) - m.start(0), m.end(group) - m.start(0)
                whole = m.group(0)
                return whole[:start] + pseudonym(kind, normalise(value)) + whole[end:]

            text = pattern.sub(repl, text)
        return text

    def address(self, addr: str | None) -> str | None:
        """Pseudonym for an email address on its own (sender, recipient)."""
        if not addr:
            return None
        self.counts["EMAIL"] += 1
        return pseudonym("EMAIL", addr.strip().lower())


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER.sub(" ", text)
