"""Gmail, read-only and scoped to one label.

The mentor labels the threads that belong to the task (or a Gmail filter does). We read every
message in those threads, including the mentor's own replies in Sent, so their actions can be
matched to the items. Nothing outside the label is ever requested.
"""

import base64
from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.capture.sources.email_source import emails_to_batch, parse_email
from app.capture.types import Batch

API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailError(RuntimeError):
    pass


def auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
        }
    )


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str, http: httpx.Client | None = None) -> str:
    http = http or httpx.Client(timeout=30)
    resp = http.post(
        TOKEN_URL,
        data={"code": code, "client_id": client_id, "client_secret": client_secret,
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
    )
    if resp.status_code != 200:
        raise GmailError(f"Google rejected the sign-in ({resp.status_code})")
    body = resp.json()
    if SCOPE not in body.get("scope", "").split():
        raise GmailError("Gmail read-only access wasn't granted")
    if "refresh_token" not in body:
        raise GmailError("Google didn't return a refresh token; remove the app's access and connect again")
    return body["refresh_token"]


class GmailClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, http: httpx.Client | None = None) -> None:
        self._creds = {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}
        self._http = http or httpx.Client(timeout=30)
        self._access: str | None = None

    def _token(self) -> str:
        if self._access is None:
            resp = self._http.post(TOKEN_URL, data={**self._creds, "grant_type": "refresh_token"})
            if resp.status_code != 200:
                raise GmailError(f"Gmail access was refused ({resp.status_code}); reconnect the mailbox")
            self._access = resp.json()["access_token"]
        return self._access

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._http.get(f"{API}{path}", params=params, headers={"Authorization": f"Bearer {self._token()}"})
        if resp.status_code == 401:
            self._access = None
            resp = self._http.get(f"{API}{path}", params=params, headers={"Authorization": f"Bearer {self._token()}"})
        if resp.status_code != 200:
            raise GmailError(f"Gmail API error {resp.status_code}")
        return resp.json()

    def label_id(self, name: str) -> str:
        for label in self._get("/labels").get("labels", []):
            if label["name"].lower() == name.lower():
                return label["id"]
        raise GmailError(f"no Gmail label named {name!r}")

    def thread_ids(self, label_id: str, after: datetime | None = None, limit: int = 2000) -> list[str]:
        ids: list[str] = []
        params: dict = {"labelIds": label_id, "maxResults": 500}
        if after:
            params["q"] = f"after:{int(after.timestamp())}"
        while len(ids) < limit:
            page = self._get("/threads", params)
            ids += [t["id"] for t in page.get("threads", [])]
            if "nextPageToken" not in page:
                break
            params["pageToken"] = page["nextPageToken"]
        return ids[:limit]

    def thread_raw_messages(self, thread_id: str) -> list[bytes]:
        thread = self._get(f"/threads/{thread_id}", {"format": "minimal"})
        raws = []
        for m in thread.get("messages", []):
            raw = self._get(f"/messages/{m['id']}", {"format": "raw"})["raw"]
            raws.append(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return raws


def fetch_batch(
    client: GmailClient, label: str, mentor_addresses: list[str], body_input: str, after: datetime | None = None
) -> Batch:
    errors: list[str] = []
    emails = []
    for thread_id in client.thread_ids(client.label_id(label), after):
        for n, raw in enumerate(client.thread_raw_messages(thread_id), start=1):
            try:
                emails.append(parse_email(raw, thread_ref=f"gmail:{thread_id}"))
            except ValueError as exc:
                errors.append(f"thread {thread_id} message {n}: {exc}")
    batch = emails_to_batch(emails, mentor_addresses, body_input)
    batch.errors = errors
    return batch
