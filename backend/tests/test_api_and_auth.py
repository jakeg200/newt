from fastapi import Depends
from sqlalchemy import select

from app.auth import require_role
from app.config import get_settings
from app.main import app
from app.models import User
from app.seed import seed


@app.get("/_test/manager-only")
def _manager_only(user: User = Depends(require_role("manager"))) -> dict:
    return {"ok": True}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_task_type_configs_endpoint(client):
    body = client.get("/task-type-configs").json()
    assert set(body) == {"invoice_mismatch", "repair_request"}


def test_requests_without_a_user_are_rejected(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"X-Dev-User": "nobody"}).status_code == 401


def test_dev_user_sees_their_org_task_types(client, session):
    seed(session)
    manager = session.scalar(select(User).where(User.role == "manager"))
    headers = {"X-Dev-User": manager.id}
    assert client.get("/me", headers=headers).json()["role"] == "manager"
    names = [t["name"] for t in client.get("/task-types", headers=headers).json()]
    assert names == ["Invoice mismatch under £5k", "Tenant repair request"]


def test_roles_are_enforced(client, session):
    seed(session)
    mentor = session.scalar(select(User).where(User.role == "mentor"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    assert client.get("/_test/manager-only", headers={"X-Dev-User": mentor.id}).status_code == 403
    assert client.get("/_test/manager-only", headers={"X-Dev-User": manager.id}).status_code == 200


def test_dev_header_refused_outside_dev(client, session, monkeypatch):
    seed(session)
    manager = session.scalar(select(User).where(User.role == "manager"))
    monkeypatch.setattr(get_settings(), "env", "production")
    resp = client.get("/me", headers={"X-Dev-User": manager.id})
    assert resp.status_code == 503  # no Supabase secret configured, and the dev header is ignored
