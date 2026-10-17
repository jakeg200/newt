"""A year of accounts-payable history with real structure: each invoice falls into a scenario
the mentor handles consistently, with ~5% of decisions going against the pattern (people aren't
perfectly consistent). Enough signal that a sensible agent scores well and a bad one doesn't."""

import csv
import io
import random
from datetime import datetime, timedelta, timezone

START = datetime(2025, 10, 1, 8, 0, tzinfo=timezone.utc)
SUPPLIERS = [("Northwind Logistics", "6300"), ("Contoso Facilities", "6200"), ("Fabrikam Software", "6100"),
             ("Tailspin Print", "6400"), ("Litware Office", "6400"), ("Adatum Consulting", "6200")]

SCENARIOS = [
    # (weight, decision, variance_reason, description template, supplier email or "")
    (40, "approve", "price", "Price variance of £{small} across {lines} lines, within the 2% tolerance", ""),
    (25, "query_supplier", "quantity", "Invoiced {a} units but the goods received note shows {b}",
     "Hello, invoice {inv} bills {a} units but we received {b}. Please send a credit note for the difference."),
    (12, "escalate", "missing_po", "No purchase order number quoted on the invoice", ""),
    (13, "escalate", "other", "Invoice total £{big} is above the £5,000 approval limit", ""),
    (10, "query_supplier", "duplicate", "Same amount and lines as invoice {prev} paid last month, possible duplicate",
     "Hello, invoice {inv} looks like a duplicate of {prev}, which we've already paid. Please confirm or cancel it."),
]


def ledger_rows(n: int = 360, seed: int = 11, noise: float = 0.05) -> list[dict[str, str]]:
    rng = random.Random(seed)
    weights = [s[0] for s in SCENARIOS]
    rows = []
    for i in range(n):
        _, decision, reason, template, email = rng.choices(SCENARIOS, weights)[0]
        supplier, gl = rng.choice(SUPPLIERS)
        inv = f"INV-{30000 + i}"
        a = rng.randint(10, 400)
        vals = {"small": f"{rng.uniform(1, 40):.2f}", "lines": rng.randint(1, 9), "a": a, "b": a - rng.randint(1, 9),
                "big": f"{rng.randint(5100, 24000):,}", "inv": inv, "prev": f"INV-{30000 + max(0, i - rng.randint(5, 40))}"}
        if rng.random() < noise:  # the mentor doesn't always follow the pattern
            decision = rng.choice([d for d in ("approve", "query_supplier", "escalate") if d != decision])
            email = "Hello, could you resend invoice {inv} with the purchase order number on it?" if decision == "query_supplier" else ""
        received = START + timedelta(hours=23 * i + rng.randint(0, 8))
        rows.append({
            "invoice_id": inv,
            "received": received.strftime("%Y-%m-%d %H:%M"),
            "supplier": f"{supplier} invoice {inv}",
            "description": template.format(**vals),
            "po": "" if reason == "missing_po" else f"PO-{70000 + i}",
            "outcome": decision,
            "decided": (received + timedelta(hours=rng.randint(1, 20))).strftime("%Y-%m-%d %H:%M"),
            "reason": reason,
            "gl": gl,
            "email_sent": email.format(**vals) if decision == "query_supplier" else "",
        })
    return rows


def ledger_csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


COLUMNS = {
    "item_ref": "invoice_id", "received_at": "received", "subject": "supplier",
    "inputs": {"invoice_text": "description", "po_record": "po"},
    "decision": "outcome", "acted_at": "decided",
    "fields": {"variance_reason": "reason", "gl_code": "gl"},
    "text_outputs": {"supplier_email": "email_sent"},
}
