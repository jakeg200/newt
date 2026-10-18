"""A stand-in for a firm's own system (or a Zapier/Make/n8n flow), for demos.

It receives Newt's signed actions, checks the signature, records them, and finishes them: at once ("done"), or later
via the signed callback ("accepted"). It can be told to fail some, to show Newt handing work back.

    cd backend
    .venv\\Scripts\\python -m uvicorn scripts.mock_system:app --port 8200

In Newt: Setup → Where Newt does the work → URL http://localhost:8200/hook. Then paste the signing secret Newt shows
into http://localhost:8200 (the form), so this system can check Newt's signature and sign its confirmations.
"""

import hashlib
import hmac
import json
import random
import threading
import time
from datetime import datetime

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI(title="Mock company system")
STATE: dict = {"secret": "", "fail": 0.0, "mode": "done", "received": []}


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(STATE["secret"].encode(), body, hashlib.sha256).hexdigest()


def _confirm_later(callback_url: str, ok: bool) -> None:
    time.sleep(2)
    body = json.dumps({"status": "done" if ok else "failed", "ref": f"SYS-{random.randint(1000, 9999)}",
                       "detail": "" if ok else "supplier record locked"}).encode()
    try:
        httpx.post(callback_url, content=body, headers={"Content-Type": "application/json", "X-Newt-Signature": _sign(body)}, timeout=10)
    except httpx.HTTPError:
        pass


@app.post("/hook")
async def hook(request: Request) -> JSONResponse:
    raw = await request.body()
    signed = bool(STATE["secret"]) and hmac.compare_digest(_sign(raw), request.headers.get("X-Newt-Signature", ""))
    action = json.loads(raw or b"{}")
    ok = random.random() >= STATE["fail"]
    STATE["received"].insert(0, {"at": datetime.now().strftime("%H:%M:%S"), "signed": signed, "ok": ok, "action": action.get("action"),
                                 "item": action.get("item_ref"), "params": action.get("params"), "test": action.get("test", False)})
    if STATE["secret"] and not signed:
        return JSONResponse({"status": "failed", "detail": "signature didn't match"}, status_code=401)
    if action.get("test"):
        return JSONResponse({"status": "done", "ref": "TEST"})
    if STATE["mode"] == "accepted" and action.get("callback_url"):
        threading.Thread(target=_confirm_later, args=(action["callback_url"], ok), daemon=True).start()
        return JSONResponse({"status": "accepted"}, status_code=202)
    if not ok:
        return JSONResponse({"status": "failed", "detail": "supplier record locked"}, status_code=200)
    return JSONResponse({"status": "done", "ref": f"SYS-{random.randint(1000, 9999)}"})


@app.post("/config")
def config(secret: str = Form(""), fail: float = Form(0.0), mode: str = Form("done")) -> RedirectResponse:
    STATE.update(secret=secret.strip(), fail=max(0.0, min(1.0, fail)), mode=mode if mode in ("done", "accepted") else "done")
    return RedirectResponse("/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    rows = "".join(
        f"<tr><td>{r['at']}</td><td>{'✓' if r['signed'] else '✗'}</td><td>{r['action']}</td><td>{r['item'] or ''}</td>"
        f"<td>{'done' if r['ok'] else 'FAILED'}</td><td><code>{json.dumps(r['params'])[:140]}</code></td></tr>" for r in STATE["received"][:50])
    return f"""<!doctype html><meta charset=utf-8><title>Mock company system</title>
<style>body{{font:14px system-ui;margin:24px;background:#f8f4ee}}table{{border-collapse:collapse;width:100%;background:#fff}}
td,th{{border-bottom:1px solid #eee;padding:6px 8px;text-align:left}}input,select{{padding:4px}}</style>
<h1>Mock company system</h1><p>Receives Newt's actions at <code>/hook</code>.</p>
<form method=post action=/config>Signing secret <input name=secret size=50 value="{STATE['secret']}">
Fail share <input name=fail size=4 value="{STATE['fail']}"> Mode <select name=mode>
<option {'selected' if STATE['mode'] == 'done' else ''}>done</option><option {'selected' if STATE['mode'] == 'accepted' else ''}>accepted</option></select>
<button>Save</button></form><h2>Received</h2><table><tr><th>At</th><th>Signed</th><th>Action</th><th>Item</th><th>Result</th><th>Params</th></tr>{rows}</table>"""
