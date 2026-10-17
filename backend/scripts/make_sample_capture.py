"""Write the synthetic AP mailbox (.eml files) and ledger export (.csv) used by the M2 tests to
samples/, so the Capture screen can be demoed by uploading real files.

Run from backend/:  python scripts/make_sample_capture.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.backtest_fixtures import COLUMNS as HISTORY_COLUMNS, ledger_csv, ledger_rows  # noqa: E402
from tests.capture_fixtures import CSV_COLUMNS, MENTOR, build_csv, build_mailbox  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "samples" / "capture"


def main() -> None:
    mailbox = OUT / "ap_mailbox"
    mailbox.mkdir(parents=True, exist_ok=True)
    for name, data in build_mailbox().files:
        if not name.endswith("_again.eml"):
            (mailbox / name).write_bytes(data)
    (OUT / "ap_ledger.csv").write_bytes(build_csv())
    (OUT / "ap_ledger_columns.json").write_text(json.dumps(CSV_COLUMNS, indent=2), encoding="utf-8")
    (OUT / "ap_history_360.csv").write_bytes(ledger_csv(ledger_rows()))
    (OUT / "ap_history_columns.json").write_text(json.dumps(HISTORY_COLUMNS, indent=2), encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Capture samples\n\n"
        f"- `ap_mailbox/`: 20 supplier invoices and the mentor's replies and forwards. Mentor address: `{MENTOR}`.\n"
        "- `ap_ledger.csv` with `ap_ledger_columns.json`: 20 rows with decisions, for a CSV connection.\n"
        "- `ap_history_360.csv` with `ap_history_columns.json`: a year of decided invoices with real patterns "
        "(and ~5% exceptions), for a 300-case backtest.\n\n"
        "All names, addresses, phone numbers and bank details are fictional.\n",
        encoding="utf-8",
    )
    print(f"wrote samples to {OUT}")


if __name__ == "__main__":
    main()
