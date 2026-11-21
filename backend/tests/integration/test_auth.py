"""Keys, scopes and the rule that an agent can propose but never decide."""

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from invoiceguard.api import deps, ratelimit
from invoiceguard.api.main import app
from invoiceguard.config import settings

pytestmark = pytest.mark.usefixtures("clean_db")

ADMIN = {"X-API-Key": "key-root"}
REVIEWER = {"X-API-Key": "key-asha"}


class MemoryCounter:
    def __init__(self):
        self.counts = {}

    def incr(self, key, ttl_seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", "key-asha:asha,key-root:root")
    monkeypatch.setattr(settings, "admin_users", "root")
    monkeypatch.setattr(ratelimit, "counter", MemoryCounter())

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[deps.get_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_agent(client, name="claude-desktop", scopes=("read", "propose")):
    response = client.post(
        "/principals", headers=ADMIN, json={"name": name, "kind": "agent", "scopes": list(scopes)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


def test_me_reports_name_kind_and_scopes(client):
    body = client.get("/me", headers=REVIEWER).json()
    assert body["name"] == "asha" and body["kind"] == "human"
    assert set(body["scopes"]) == {"read", "submit", "review", "post"}
    assert "admin" in client.get("/me", headers=ADMIN).json()["scopes"]


def test_no_key_and_wrong_key_are_401(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/me", headers=bearer("ig_made_up")).status_code == 401


def test_only_admins_manage_principals(client):
    body = {"name": "bot", "kind": "agent", "scopes": ["read"]}
    assert client.post("/principals", headers=REVIEWER, json=body).status_code == 403
    assert client.get("/principals", headers=REVIEWER).status_code == 403
    assert client.get("/principals").status_code == 401


def test_an_issued_key_is_shown_once_and_stored_only_as_a_hash(client, session_factory):
    created = make_agent(client)
    assert created["key"].startswith("ig_") and created["key_prefix"] == created["key"][:8]
    listed = client.get("/principals", headers=ADMIN).json()
    assert [p["name"] for p in listed] == ["claude-desktop"]
    assert "key" not in listed[0]
    with session_factory() as session:
        stored = session.execute(sa.text("SELECT key_hash FROM principals")).scalar_one()
    assert stored != created["key"] and created["key"] not in stored


def test_an_agent_key_works_as_a_bearer_token_and_as_an_api_key(client):
    key = make_agent(client)["key"]
    assert client.get("/invoices", headers=bearer(key)).status_code == 200
    assert client.get("/invoices", headers={"X-API-Key": key}).status_code == 200
    me = client.get("/me", headers=bearer(key)).json()
    assert me["name"] == "claude-desktop" and me["kind"] == "agent"
    assert set(me["scopes"]) == {"read", "propose"}


def test_an_agent_can_never_approve_reject_edit_or_replay(client):
    key = make_agent(client, scopes=("read", "propose", "submit", "post"))["key"]
    someone = uuid.uuid4()
    body = {"expected_version": 1, "reason": "looks fine"}
    for path in ("approve", "reject", "edit", "replay"):
        response = client.post(f"/invoices/{someone}/{path}", headers=bearer(key), json=body)
        assert response.status_code == 403, path


def test_an_agent_key_cannot_be_issued_review_or_admin_scope(client):
    for scope in ("review", "admin"):
        response = client.post(
            "/principals",
            headers=ADMIN,
            json={"name": f"bad-{scope}", "kind": "agent", "scopes": ["read", scope]},
        )
        assert response.status_code == 422


def test_a_read_only_key_cannot_submit_or_post(client):
    key = make_agent(client, scopes=("read",))["key"]
    assert client.post("/invoices", headers=bearer(key), json={}).status_code == 403
    assert client.post(f"/invoices/{uuid.uuid4()}/post", headers=bearer(key)).status_code == 403
    upload = client.post("/documents", headers=bearer(key), files={"file": ("a.pdf", b"x")})
    assert upload.status_code == 403


def test_disabling_a_principal_stops_its_key_at_once(client):
    created = make_agent(client)
    assert client.get("/invoices", headers=bearer(created["key"])).status_code == 200
    assert client.post(f"/principals/{created['id']}/disable", headers=ADMIN).status_code == 200
    assert client.get("/invoices", headers=bearer(created["key"])).status_code == 401


def test_duplicate_names_unknown_scopes_and_unknown_packs_are_refused(client):
    make_agent(client)
    again = {"name": "claude-desktop", "kind": "agent", "scopes": ["read"]}
    assert client.post("/principals", headers=ADMIN, json=again).status_code == 409
    assert client.post(
        "/principals", headers=ADMIN, json={"name": "x1", "kind": "agent", "scopes": ["fly"]}
    ).status_code == 422
    assert client.post(
        "/principals", headers=ADMIN,
        json={"name": "x2", "kind": "agent", "scopes": ["read"], "packs": ["payroll"]},
    ).status_code == 422


def test_creating_and_disabling_are_in_the_audit_log(client, session_factory):
    created = make_agent(client)
    client.post(f"/principals/{created['id']}/disable", headers=ADMIN)
    with session_factory() as session:
        events = session.execute(
            sa.text("SELECT event_type, actor FROM audit_events ORDER BY id")
        ).all()
    assert [tuple(e) for e in events] == [
        ("principal.created", "root"),
        ("principal.disabled", "root"),
    ]


def test_an_agent_cannot_use_a_human_only_route_even_with_every_agent_scope(client):
    key = make_agent(client, scopes=("read", "submit", "propose", "post"))["key"]
    assert client.get("/principals", headers=bearer(key)).status_code == 403
