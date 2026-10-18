"""Synthetic accounts-payable work: a year of decided history, new live invoices, and how the
(fictional) mentor decides. Each invoice falls into a scenario the mentor handles consistently;
`noise` is the share of decisions that go against the pattern, because people aren't perfectly
consistent. All names, numbers and addresses are made up."""

import csv
import io
import random
import re
from datetime import datetime, timedelta, timezone

# The history always ends here, however many rows: decided history must be in the past, before any live
# item ("now"). Starting from a fixed date instead let long histories run into the future, where live
# cases became their "earlier" cases.
END = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
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

COLUMNS = {
    "item_ref": "invoice_id", "received_at": "received", "subject": "supplier",
    "inputs": {"invoice_text": "description", "po_record": "po"},
    "decision": "outcome", "acted_at": "decided",
    "fields": {"variance_reason": "reason", "gl_code": "gl"},
    "text_outputs": {"supplier_email": "email_sent"},
}


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
        if rng.random() < noise:
            decision = rng.choice([d for d in ("approve", "query_supplier", "escalate") if d != decision])
            email = "Hello, could you resend invoice {inv} with the purchase order number on it?" if decision == "query_supplier" else ""
        received = END - timedelta(hours=23 * (n - 1 - i)) + timedelta(hours=rng.randint(0, 8))
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


def mentor_answer(item: dict) -> dict:
    """What the demo mentor does with a new invoice, by pattern."""
    text = " ".join(str(v) for v in item["inputs"].values())
    if "units" in text:
        decision, reason = "query_supplier", "quantity"
    elif "purchase order" in text:
        decision, reason = "escalate", "missing_po"
    elif "approval limit" in text:
        decision, reason = "escalate", "other"
    elif "duplicate" in text:
        decision, reason = "query_supplier", "duplicate"
    else:
        decision, reason = "approve", "price"
    gl = next((code for name, code in SUPPLIERS if item.get("subject", "").startswith(name)), "6400")
    inv = (re.findall(r"INV-\d+", item.get("subject", "")) or ["INV-0"])[0]
    nums = re.findall(r"\d+", text)
    email = ""
    if reason == "quantity":
        email = f"Hello, invoice {inv} bills {nums[0]} units but we received {nums[1]}. Please send a credit note for the difference."
    elif reason == "duplicate":
        prev = re.search(r"INV-\d+", text).group(0)
        email = f"Hello, invoice {inv} looks like a duplicate of {prev}, which we've already paid. Please confirm or cancel it."
    return {"decision": decision, "fields": {"variance_reason": reason, "gl_code": gl}, "text_outputs": {"supplier_email": email}}


_counter = [0]


def number_from(n: int) -> None:
    """Number new live items from n on, so a new process doesn't reuse invoice numbers already sent."""
    _counter[0] = max(_counter[0], n)


def live_items(n: int, *, start: datetime | None = None, seed: int = 5, text: str | None = None,
               subject: str | None = None) -> list[dict]:
    """New supplier invoices arriving from now, in the history's patterns (or with fixed text)."""
    rng = random.Random(seed + _counter[0])
    start = start or datetime.now(timezone.utc)
    rows = ledger_rows(n, seed=seed + 100 + _counter[0], noise=0.0)
    items = []
    for i, r in enumerate(rows):
        _counter[0] += 1
        supplier = r["supplier"].split(" invoice ")[0]
        items.append({"ref": f"LIVE-{_counter[0]}-{rng.randint(1000, 9999)}", "received_at": (start + timedelta(minutes=i)).isoformat(),
                      "subject": subject or f"{supplier} invoice INV-{90000 + _counter[0]}",
                      "inputs": {"invoice_text": text or r["description"],
                                 "po_record": f"PO-{80000 + _counter[0]}" if r["po"] else ""},
                      "sender": f"billing{rng.randint(1, 5)}@{supplier.split()[0].lower()}.example"})
    return items


def mentor_actions(items: list[dict], at: datetime | None = None) -> list[dict]:
    """The demo mentor's real decisions on live items, as the source system would report them."""
    at = at or datetime.now(timezone.utc) + timedelta(hours=2)
    out = []
    for it in items:
        a = mentor_answer(it)
        out.append({"ref": f"{it['ref']}#done", "item_ref": it["ref"], "acted_at": at.isoformat(), "decision": a["decision"],
                    "fields": a["fields"], "text_outputs": {k: v for k, v in a["text_outputs"].items() if v}})
    return out


SUPPLIER_REPLY_DAYS = [1, 1, 2, 2, 4, 5, 6, None]  # how long suppliers take to answer a query (None: never)


def threads(n: int = 24, seed: int = 21) -> dict:
    """Past supplier queries as whole processes, for process replays: the invoice arrives, the mentor decides and writes
    to the supplier, the supplier answers in the same thread days later (or doesn't, and the mentor chases on day 3),
    and the mentor closes it. Some plain approvals in between. Everything ends before END, so it's all history."""
    rng = random.Random(seed)
    items, actions = [], []
    start = END - timedelta(days=45)
    for i in range(n):
        supplier, gl = rng.choice(SUPPLIERS)
        inv = f"INV-{20000 + i}"
        at = start + timedelta(hours=26 * i + rng.randint(0, 6))
        sender = f"billing@{supplier.split()[0].lower()}.example"
        thread = f"thread-{inv}"
        query = i % 3 != 2
        a = rng.randint(20, 300)
        text = f"Invoiced {a} units but the goods received note shows {a - rng.randint(1, 9)}" if query else \
            f"Price variance of £{rng.uniform(1, 30):.2f} across {rng.randint(1, 6)} lines, within the 2% tolerance"
        item = {"ref": f"{inv}-thread", "received_at": at.isoformat(), "subject": f"{supplier} invoice {inv}", "thread": thread,
                "sender": sender, "inputs": {"invoice_text": text, "po_record": f"PO-{60000 + i}"}}
        items.append(item)
        answer = mentor_answer(item)
        actions.append({"ref": f"{inv}#d", "item_ref": item["ref"], "acted_at": (at + timedelta(hours=1)).isoformat(),
                        "decision": answer["decision"], "fields": answer["fields"],
                        "text_outputs": {k: v for k, v in answer["text_outputs"].items() if v}})
        if not query:
            continue
        actions.append({"ref": f"{inv}#r", "item_ref": item["ref"], "acted_at": (at + timedelta(hours=2)).isoformat(),
                        "kind": "reply", "text": answer["text_outputs"]["supplier_email"]})
        days = rng.choice(SUPPLIER_REPLY_DAYS)
        if days is None or days > 3:  # nothing back by day 3: the mentor chases
            actions.append({"ref": f"{inv}#chase", "item_ref": item["ref"], "acted_at": (at + timedelta(days=3, hours=2)).isoformat(),
                            "kind": "reply", "text": f"Hello, just following up on invoice {inv}. Could you let us know where this stands?"})
        if days is not None:
            back = at + timedelta(days=days, hours=rng.randint(1, 6))
            items.append({"ref": f"{inv}-re", "received_at": back.isoformat(), "subject": f"Re: {supplier} invoice {inv}", "thread": thread,
                          "sender": sender, "inputs": {"invoice_text": "Apologies, we've issued a credit note for the difference.", "po_record": ""}})
            actions.append({"ref": f"{inv}#close", "item_ref": item["ref"], "acted_at": (back + timedelta(hours=3)).isoformat(),
                            "kind": "status", "status": "closed"})
    return {"items": items, "actions": actions, "backtest": True}
