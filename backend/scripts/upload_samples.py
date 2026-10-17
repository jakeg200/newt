"""Upload the sample accounts-payable policies to the synthetic org, as its mentor.

Run from backend/ with the API running:  python scripts/upload_samples.py
"""

import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"
TEAM = "invoice_mismatch"
SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "accounts_payable"


def main() -> None:
    users = httpx.get(f"{API}/dev/users").json()
    mentor = next(u for u in users if u["role"] == "mentor" and TEAM in u["email"])
    files = [("files", (p.name, p.read_bytes())) for p in sorted(SAMPLES.iterdir()) if p.is_file()]
    resp = httpx.post(f"{API}/orientation/sources", data={"team": TEAM}, files=files, headers={"X-Dev-User": mentor["id"]})
    resp.raise_for_status()
    for doc in resp.json():
        print(doc)


if __name__ == "__main__":
    sys.exit(main())
