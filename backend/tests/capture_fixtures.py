"""A synthetic accounts-payable mailbox: 20 supplier invoices and the mentor's actions on them.

Every item has exactly one true mentor action, delivered with different evidence:
  - replies with In-Reply-To and References            (12)
  - forwards to the finance manager with References    (4)
  - emails with no threading headers that only mention
    the invoice number in the subject                   (4)
plus two decoys that must stay unmatched: an unrelated email, and one that mentions a PO number
two invoices share. Bodies carry phone numbers, bank details and signatures that must never be
stored raw.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

MENTOR = "sarah.k@synthetic.test"
FINANCE_MANAGER = "finance.manager@synthetic.test"
START = datetime(2026, 3, 2, 8, 30, tzinfo=timezone.utc)
SUPPLIERS = [
    ("Northwind Logistics", "billing@northwind.example"),
    ("Contoso Facilities", "accounts@contoso.example"),
    ("Fabrikam Software", "ar@fabrikam.example"),
    ("Tailspin Print", "invoices@tailspin.example"),
    ("Litware Office", "finance@litware.example"),
]
# Unique sentences and personal data: none of these may appear in logs or raw in the database.
SENTINEL = "Please find attached our invoice for goods delivered"
PII = ["07700 900123", "20-45-77", "41234567", "GB33BUKB20201555555555", "jo.bloggs@northwind.example"]


@dataclass
class Fixture:
    files: list[tuple[str, bytes]]
    item_ids: list[str]  # Message-IDs of the 20 items
    expected: dict[str, str]  # action Message-ID -> item Message-ID it acts on
    decoys: list[str]  # action Message-IDs that must stay unmatched
    expected_decisions: dict[str, str]  # item Message-ID -> decision


def _msg(mid: str, sender: str, to: list[str], at: datetime, subject: str, body: str,
         in_reply_to: str | None = None, references: list[str] | None = None) -> bytes:
    m = EmailMessage()
    m["Message-ID"] = mid
    m["From"] = sender
    m["To"] = ", ".join(to)
    m["Date"] = format_datetime(at)
    m["Subject"] = subject
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if references:
        m["References"] = " ".join(references)
    m.set_content(body)
    return m.as_bytes()


def build_mailbox() -> Fixture:
    files: list[tuple[str, bytes]] = []
    items: list[str] = []
    expected: dict[str, str] = {}
    decisions: dict[str, str] = {}

    for n in range(20):
        supplier, address = SUPPLIERS[n % len(SUPPLIERS)]
        inv, po = f"INV-{1001 + n}", f"PO-{7700 + n}"
        if n in (17, 18):
            po = "PO-7799"  # two invoices share a PO: a decoy mentions only this
        mid = f"<inv{n}@{address.split('@')[1]}>"
        at = START + timedelta(hours=9 * n)
        body = (
            f"Hello,\n\n{SENTINEL}. Invoice {inv} against {po} for £{1200 + 37 * n}.00.\n"
            f"Bank details have not changed: sort code 20-45-77, account number 41234567, "
            f"IBAN GB33BUKB20201555555555.\n\nKind regards,\nJo Bloggs\njo.bloggs@northwind.example | 07700 900123\n"
        )
        files.append((f"item_{n:02d}.eml", _msg(mid, address, [MENTOR], at, f"Invoice {inv} ({supplier})", body)))
        items.append(mid)

        act_at = at + timedelta(hours=2, minutes=n)
        act_id = f"<act{n}@synthetic.test>"
        quoted = "\n\nOn Mon, someone wrote:\n> " + SENTINEL
        if n < 12:  # reply to the supplier, proper headers
            raw = _msg(act_id, MENTOR, [address], act_at, f"Re: Invoice {inv} ({supplier})",
                       f"Hi, the quantity on {inv} doesn't match the goods received note. Please send a credit note."
                       + quoted, in_reply_to=mid, references=[mid])
            decisions[mid] = "query_supplier"
        elif n < 16:  # forward to the finance manager, References kept
            raw = _msg(act_id, MENTOR, [FINANCE_MANAGER], act_at, f"Fwd: Invoice {inv} ({supplier})",
                       f"Over my limit, please approve {inv}.\n\n---------- Forwarded message ----------\nFrom: {address}\n{SENTINEL}",
                       references=[mid])
            decisions[mid] = "escalate"
        else:  # no threading headers; only the invoice number links it
            to = [address] if n % 2 == 0 else [FINANCE_MANAGER]
            raw = _msg(act_id, MENTOR, to, act_at, f"About invoice {inv}", f"Following up on {inv}, see below.")
            decisions[mid] = "query_supplier" if n % 2 == 0 else "escalate"
        files.append((f"action_{n:02d}.eml", raw))
        expected[act_id] = mid

    decoys = ["<decoy1@synthetic.test>", "<decoy2@synthetic.test>"]
    late = START + timedelta(days=12)
    files.append(("decoy_1.eml", _msg(decoys[0], MENTOR, ["colleague@synthetic.test"], late, "Lunch on Friday?", "Are you free at 1?")))
    files.append(("decoy_2.eml", _msg(decoys[1], MENTOR, [FINANCE_MANAGER], late, "Question on PO-7799", "Which invoice is this PO for?")))
    files.append(("item_00_again.eml", files[0][1]))  # the same message uploaded twice
    return Fixture(files, items, expected, decoys, decisions)


def build_csv(rows: int = 20) -> bytes:
    lines = ["invoice_id,received,supplier,description,po,outcome,decided,reason,gl,email_sent"]
    outcomes = ["Approved", "Queried", "Escalated"]
    for n in range(rows):
        at = START + timedelta(hours=5 * n)
        outcome = outcomes[n % 3]
        email = f"\"Please send a credit note for INV-{2001 + n}, call me on 07700 900123\"" if outcome == "Queried" else ""
        lines.append(
            f"INV-{2001 + n},{at:%d/%m/%Y %H:%M},Supplier {n % 4},\"Invoice INV-{2001 + n}, 3 lines\",PO-{8800 + n},"
            f"{outcome},{(at + timedelta(hours=3)):%Y-%m-%d %H:%M},price,6400,{email}"
        )
    return ("\n".join(lines) + "\n").encode()


CSV_COLUMNS = {
    "item_ref": "invoice_id",
    "received_at": "received",
    "subject": "supplier",
    "inputs": {"invoice_text": "description", "po_record": "po"},
    "decision": "outcome",
    "decision_map": {"Approved": "approve", "Queried": "query_supplier", "Escalated": "escalate"},
    "acted_at": "decided",
    "fields": {"variance_reason": "reason", "gl_code": "gl"},
    "text_outputs": {"supplier_email": "email_sent"},
}
