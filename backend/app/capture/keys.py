"""Match keys: what we keep so later actions can find their case, without keeping content.

Message ids, thread ids and addresses are stored only as keyed hashes. Reference tokens (invoice,
PO and ticket numbers) are kept as-is, but only after redaction, so a phone or card number can
never become a token.
"""

import hashlib
import hmac
import re

from app.capture.redact import strip_placeholders
from app.config import get_settings

# Has a digit; 4–24 characters of letters, digits, '-', '/' or '_'; not a plain short number or a date.
_TOKEN = re.compile(r"(?<![\w-])(?=[\w/-]*\d)[A-Za-z0-9][\w/-]{2,22}[A-Za-z0-9](?![\w-])")
_DATE = re.compile(r"^\d{1,4}[/-]\d{1,2}([/-]\d{1,4})?$")
_MONEY_OR_TIME = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?$|^\d{1,2}:\d{2}$")


def hkey(kind: str, value: str | None) -> str | None:
    if not value:
        return None
    normalised = value.strip().strip("<>").lower()
    return hmac.new(get_settings().secret(), f"{kind}:{normalised}".encode(), hashlib.sha256).hexdigest()[:24]


def ref_tokens(*texts: str | None) -> set[str]:
    """Reference-number-like tokens from already-redacted text."""
    tokens: set[str] = set()
    for text in texts:
        if not text:
            continue
        for m in _TOKEN.finditer(strip_placeholders(text)):
            tok = m.group(0).upper()
            if _DATE.match(tok) or _MONEY_OR_TIME.match(tok):
                continue
            if tok.isdigit() and len(tok) < 5:  # years, small quantities
                continue
            tokens.add(tok)
    return tokens
