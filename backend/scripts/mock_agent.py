"""A stand-in vendor agent for demos: verifies our signature, then decides invoice mismatches by
simple rules. Register it on the Backtest screen with endpoint http://localhost:8100/predict,
then start it with the signing secret you were shown:

    set MOCK_AGENT_SECRET=whsec_...
    python -m uvicorn scripts.mock_agent:app --port 8100     (from backend/)
"""

import hashlib
import hmac
import json
import os

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Mock vendor agent")
SECRET = os.environ.get("MOCK_AGENT_SECRET", "")


@app.post("/predict")
async def predict(request: Request) -> dict:
    body = await request.body()
    expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not SECRET or not hmac.compare_digest(expected, request.headers.get("X-Agent-Onboarding-Signature", "")):
        raise HTTPException(401, "bad signature")
    case = json.loads(body)
    text = " ".join(str(v) for v in case["item"]["inputs"].values()).lower()
    if "units" in text or "quantity" in text:
        decision, reason = "query_supplier", "quantity"
    elif "duplicate" in text:
        decision, reason = "query_supplier", "duplicate"
    elif "purchase order" in text:
        decision, reason = "escalate", "missing_po"
    elif "limit" in text:
        decision, reason = "escalate", "other"
    else:
        decision, reason = "approve", "price"
    decision = decision if decision in case["task_type"]["decision"] else case["task_type"]["decision"][0]
    return {"decision": decision, "fields": {"variance_reason": reason}, "text_outputs": {},
            "rationale": "Keyword rules (mock vendor agent).", "missing_info": [], "self_reported_confidence": 0.7}
