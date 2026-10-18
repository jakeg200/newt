"""Role packs: the library of roles a Newt can be hired for, validated with their task types, and hiring one."""

import json

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.execution import routines
from app.models import Apprenticeship, TaskType, User
from app.seed import seed
from app.task_types import load_role_packs


def test_packs_load_and_validate():
    s = get_settings()
    packs = load_role_packs(s.roles_dir, s.task_types_dir)
    assert {"accounts_payable_exceptions", "property_repairs"} <= set(packs)
    pack, config = packs["accounts_payable_exceptions"]
    assert pack.routines["query_supplier"].follow_up_days == 3 and "lookup_record" in config.tools


def test_a_pack_with_bad_routines_is_refused(tmp_path):
    s = get_settings()
    (tmp_path / "bad.json").write_text(json.dumps({"id": "bad", "title": "Bad", "tagline": "", "description": "", "team": "x",
                                                   "task_type": "invoice_mismatch.json", "routines": {"approve": {"steps": ["send_money"]}}}))
    with pytest.raises(ValueError):
        load_role_packs(tmp_path, s.task_types_dir)


def test_hiring_a_newt_from_the_library(client, session):
    seed(session)
    manager = session.scalar(select(User).where(User.role == "manager"))
    mentor = session.scalar(select(User).where(User.role == "mentor"))
    h, m = {"X-Dev-User": manager.id}, {"X-Dev-User": mentor.id}
    library = client.get("/role-packs", headers=m).json()
    assert any(p["id"] == "property_repairs" and p["tools"] for p in library)
    assert client.post("/role-packs/property_repairs/hire", json={"team": "lettings"}, headers=m).status_code == 403
    assert client.post("/role-packs/nope/hire", json={}, headers=h).status_code == 404
    r = client.post("/role-packs/property_repairs/hire", json={"team": "lettings"}, headers=h)
    assert r.status_code == 201, r.text
    tt = session.get(TaskType, r.json()["task_type_id"])
    assert session.get(Apprenticeship, tt.apprenticeship_id).team == "lettings"
    proposed = routines.proposed(session, tt)
    assert proposed["ask_for_details"]["from_pack"] and proposed["ask_for_details"]["follow_up_days"] == 2
    assert client.post("/role-packs/property_repairs/hire", json={"team": "lettings"}, headers=h).status_code == 400  # already hired
