"""A stand-in for Slack, for demos: it answers Newt's calls to the Slack Web API and shows the DMs Newt sends, with
working buttons and a reply box. Taps and replies go back to Newt signed, exactly as Slack would send them.

    cd backend
    set MOCK_SLACK_SIGNING_SECRET=demo-signing
    .venv\\Scripts\\python -m uvicorn scripts.mock_chat:app --port 8300

Run the API with SLACK_API_URL=http://127.0.0.1:8300/api and SLACK_SIGNING_SECRET=demo-signing, connect the org with
`SLACK_BOT_TOKEN=xoxb-demo python -m app.admin connect-slack "Demo Co" T-DEMO`, choose Slack in Setup, and open
http://localhost:8300.
"""

import hashlib
import hmac
import html
import json
import os
import time
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Mock Slack")
NEWT_API = os.environ.get("NEWT_API_URL", "http://127.0.0.1:8000")
SECRET = os.environ.get("MOCK_SLACK_SIGNING_SECRET", "demo-signing")
TEAM = os.environ.get("MOCK_SLACK_TEAM", "T-DEMO")
STATE: dict = {"messages": [], "users": {}}  # ts -> message; email -> user id


def _signed_post(path: str, body: bytes, content_type: str) -> None:
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(SECRET.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    try:
        httpx.post(f"{NEWT_API}{path}", content=body, timeout=30,
                   headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig, "Content-Type": content_type})
    except httpx.HTTPError:
        pass


@app.post("/api/{method}")
async def web_api(method: str, request: Request) -> dict:
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if method == "users.lookupByEmail":
        uid = STATE["users"].setdefault(body.get("email", ""), f"U{len(STATE['users']) + 1:04d}")
        return {"ok": True, "user": {"id": uid}}
    if method == "conversations.open":
        return {"ok": True, "channel": {"id": f"D-{body.get('users')}"}}
    if method == "chat.postMessage":
        ts = f"{time.time():.6f}"
        STATE["messages"].append({"ts": ts, "channel": body.get("channel"), "text": body.get("text", ""), "blocks": body.get("blocks"),
                                  "thread": body.get("thread_ts")})
        return {"ok": True, "ts": ts}
    if method == "chat.update":
        for m in STATE["messages"]:
            if m["ts"] == body.get("ts"):
                m["blocks"], m["text"] = body.get("blocks"), body.get("text", m["text"])
        return {"ok": True}
    return {"ok": False, "error": "unknown_method"}


def _render(m: dict) -> str:
    parts = []
    for b in m.get("blocks") or [{"type": "section", "text": {"text": m["text"]}}]:
        if b["type"] == "section":
            text = html.escape(b["text"]["text"]).replace("\n", "<br>")
            parts.append(f"<p>{text.replace('*', '')}</p>")
        elif b["type"] == "actions":
            buttons = "".join(
                f"<form method=post action=/tap style='display:inline'><input type=hidden name=value value='{html.escape(e['value'])}'>"
                f"<input type=hidden name=channel value='{m['channel']}'>"
                f"<button class='{e.get('style', '')}'>{html.escape(e['text']['text'])}</button></form>" for e in b["elements"])
            parts.append(f"<div class=actions>{buttons}</div>")
        elif b["type"] == "context":
            parts.append(f"<small>{html.escape(b['elements'][0]['text'])}</small>")
    reply = (f"<form method=post action=/say class=reply><input type=hidden name=channel value='{m['channel']}'>"
             f"<input type=hidden name=thread value='{m['ts']}'><input name=text placeholder='Reply in thread'><button>Send</button></form>")
    who = "Newt" if not m.get("from_me") else "You"
    return f"<div class='msg {'me' if m.get('from_me') else ''}'><b>{who}</b>{''.join(parts)}{'' if m.get('from_me') else reply}</div>"


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    msgs = "".join(_render(m) for m in STATE["messages"]) or "<p class=empty>No messages yet. Choose Slack in Newt's Setup.</p>"
    channel = next((m["channel"] for m in reversed(STATE["messages"]) if not m.get("from_me")), "")
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mock Slack</title><meta http-equiv=refresh content=10>
<style>body{{font:15px system-ui;background:#f8f8f8;margin:0}}header{{background:#3f0e40;color:#fff;padding:12px 16px;font-weight:700}}
main{{max-width:640px;margin:0 auto;padding:16px}}.msg{{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:12px;margin:10px 0}}
.msg.me{{background:#eef6ff}}button{{margin:6px 6px 0 0;padding:6px 12px;border-radius:6px;border:1px solid #ccc;background:#fff;cursor:pointer}}
button.primary{{background:#007a5a;color:#fff;border-color:#007a5a}}small{{color:#666;display:block;margin-top:6px}}
.reply{{margin-top:8px;display:flex;gap:6px}}.reply input{{flex:1;padding:6px;border:1px solid #ccc;border-radius:6px}}
.empty{{color:#777}}</style>
<header>#newt · direct messages (mock Slack)</header><main>{msgs}
<form method=post action=/say class=reply><input type=hidden name=channel value='{channel}'><input name=text placeholder='Message Newt'><button>Send</button></form></main>"""


def _user_of(channel: str) -> str:
    return channel.removeprefix("D-")


@app.post("/tap")
def tap(value: str = Form(...), channel: str = Form(...)) -> RedirectResponse:
    payload = {"type": "block_actions", "team": {"id": TEAM}, "user": {"id": _user_of(channel)}, "actions": [{"value": value}]}
    _signed_post("/channels/slack/interactivity", urlencode({"payload": json.dumps(payload)}).encode(), "application/x-www-form-urlencoded")
    return RedirectResponse("/", status_code=303)


@app.post("/say")
def say(text: str = Form(...), channel: str = Form(""), thread: str = Form("")) -> RedirectResponse:
    if channel and text.strip():
        STATE["messages"].append({"ts": f"{time.time():.6f}", "channel": channel, "text": text, "from_me": True})
        event = {"type": "message", "channel_type": "im", "channel": channel, "user": _user_of(channel), "text": text,
                 **({"thread_ts": thread} if thread else {})}
        _signed_post("/channels/slack/events", json.dumps({"type": "event_callback", "team_id": TEAM, "event": event}).encode(),
                     "application/json")
    return RedirectResponse("/", status_code=303)
