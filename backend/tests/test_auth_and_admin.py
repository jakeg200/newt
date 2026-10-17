"""Production sign-in (Supabase JWTs) and provisioning."""

import time

import jwt
import pytest
from sqlalchemy import select

from app import admin
from app.config import get_settings
from app.models import Agent, Org, TaskType, User
from app.task_types import load_task_type

SECRET = "test-jwt-secret-with-enough-length-for-hs256"


def token(email: str, *, secret: str = SECRET, exp: int | None = None, aud: str = "authenticated") -> str:
    now = int(time.time())
    return jwt.encode({"sub": "user-1", "email": email, "aud": aud, "iat": now, "exp": exp or now + 3600}, secret, algorithm="HS256")


@pytest.fixture
def production(monkeypatch, session):
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "app_secret", "a-real-secret-for-tests")
    monkeypatch.setattr(s, "supabase_jwt_secret", SECRET)
    org = admin.create_org(session, "Acme Ltd")
    admin.add_user(session, "Acme Ltd", "Sarah@Acme.com", "Sarah K", "mentor")
    admin.add_user(session, "Acme Ltd", "morgan@acme.com", "Morgan", "manager")
    return org


def test_valid_token_signs_in(client, production):
    me = client.get("/me", headers={"Authorization": f"Bearer {token('sarah@acme.com')}"}).json()
    assert me["email"] == "sarah@acme.com" and me["role"] == "mentor" and me["org"] == "Acme Ltd" and me["synthetic"] is False


@pytest.mark.parametrize(
    ("tok", "code"),
    [
        (lambda: token("sarah@acme.com", exp=int(time.time()) - 10), 401),
        (lambda: token("sarah@acme.com", secret="someone-elses-secret-also-long-enough"), 401),
        (lambda: token("sarah@acme.com", aud="anon"), 401),
        (lambda: token("stranger@elsewhere.com"), 403),
        (lambda: "not-a-jwt", 401),
    ],
)
def test_bad_tokens_are_refused(client, production, tok, code):
    assert client.get("/me", headers={"Authorization": f"Bearer {tok()}"}).status_code == code


def test_dev_header_and_dev_users_are_off_in_production(client, production, session):
    sarah = session.scalar(select(User).where(User.email == "sarah@acme.com"))
    assert client.get("/me", headers={"X-Dev-User": sarah.id}).status_code == 401
    assert client.get("/dev/users").status_code == 404


def test_roles_still_apply(client, production, session):
    tt = admin.add_team(session, "Acme Ltd", "accounts_payable", "sarah@acme.com",
                        load_task_type(get_settings().task_types_dir / "invoice_mismatch.json"))
    manager = {"Authorization": f"Bearer {token('morgan@acme.com')}"}
    assert client.get(f"/teaching/queue?task_type_id={tt.id}", headers=manager).status_code == 403
    assert client.get("/manager/dashboard", headers=manager).status_code == 200


def test_admin_provisioning(session):
    admin.create_org(session, "Beta Co")
    with pytest.raises(admin.AdminError, match="already exists"):
        admin.create_org(session, "Beta Co")
    org = session.scalar(select(Org).where(Org.name == "Beta Co"))
    assert session.scalar(select(Agent).where(Agent.org_id == org.id)).kind == "built_in"
    admin.add_user(session, "Beta Co", "m@beta.co", "M", "mentor")
    with pytest.raises(admin.AdminError, match="role"):
        admin.add_user(session, "Beta Co", "x@beta.co", "X", "owner")
    with pytest.raises(admin.AdminError, match="isn't a mentor"):
        admin.add_team(session, "Beta Co", "ap", "nobody@beta.co", load_task_type(get_settings().task_types_dir / "invoice_mismatch.json"))
    tt = admin.add_team(session, "Beta Co", "ap", "m@beta.co", load_task_type(get_settings().task_types_dir / "invoice_mismatch.json"))
    assert session.get(TaskType, tt.id).status == "shadow"
