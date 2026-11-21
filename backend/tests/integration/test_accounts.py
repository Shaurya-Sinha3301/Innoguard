"""Accounts: email and password sign-in, sessions, and keys a person generates for themselves."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from invoiceguard.api import deps, ratelimit
from invoiceguard.api.main import app
from invoiceguard.config import settings
from invoiceguard.db import models as m

pytestmark = pytest.mark.usefixtures("clean_db")

PASSWORD = "correct horse battery"


class MemoryCounter:
    def __init__(self):
        self.counts = {}

    def incr(self, key, ttl_seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", "key-env:env-reviewer")
    monkeypatch.setattr(settings, "admin_users", "")
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "signup_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 100)
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


def signup(client, name="Asha", email=None, password=PASSWORD):
    email = email or f"{name.lower()}@example.com"
    return client.post("/auth/signup", json={"email": email, "name": name, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_the_first_account_is_the_administrator_and_gets_a_session(client):
    r = signup(client, "Asha")
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("igs_") and body["user"]["is_admin"] is True
    me = client.get("/me", headers=bearer(body["token"])).json()
    assert me["name"] == "Asha" and me["account"] is True and "admin" in me["scopes"]


def test_later_accounts_are_reviewers_not_administrators(client):
    signup(client, "Asha")
    second = signup(client, "Ravi").json()
    assert second["user"]["is_admin"] is False
    me = client.get("/me", headers=bearer(second["token"])).json()
    assert set(me["scopes"]) == {"read", "submit", "review", "post"}


def test_admin_emails_decide_who_is_an_administrator(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    first = signup(client, "Asha").json()
    boss = signup(client, "Boss", email="boss@example.com").json()
    assert first["user"]["is_admin"] is False and boss["user"]["is_admin"] is True


def test_the_password_is_never_stored(client, session_factory):
    signup(client, "Asha")
    with session_factory() as session:
        stored = session.scalar(sa.select(m.User.password_hash))
    assert stored.startswith("scrypt$") and PASSWORD not in stored


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"email": "a@example.com", "name": "Asha", "password": "short"}, 422),
        ({"email": "not-an-email", "name": "Asha", "password": PASSWORD}, 422),
        ({"email": "a@example.com", "name": "!", "password": PASSWORD}, 422),
    ],
)
def test_bad_signups_are_refused(client, payload, status):
    assert client.post("/auth/signup", json=payload).status_code == status


def test_an_email_or_name_cannot_be_registered_twice(client):
    signup(client, "Asha")
    assert signup(client, "Asha", email="other@example.com").status_code == 409
    assert signup(client, "ASHA", email="third@example.com").status_code == 409
    assert signup(client, "Someone", email="asha@example.com").status_code == 409


def test_signup_can_be_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    assert signup(client, "Asha").status_code == 403


def test_login_works_and_a_wrong_password_looks_like_an_unknown_email(client):
    signup(client, "Asha")
    ok = client.post("/auth/login", json={"email": "ASHA@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["token"].startswith("igs_")
    wrong = client.post("/auth/login", json={"email": "asha@example.com", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "who@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_a_session_works_as_a_bearer_token_and_as_the_old_header(client):
    token = signup(client, "Asha").json()["token"]
    assert client.get("/invoices", headers=bearer(token)).status_code == 200
    assert client.get("/invoices", headers={"X-API-Key": token}).status_code == 200


def test_logging_out_ends_the_session(client):
    token = signup(client, "Asha").json()["token"]
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_an_expired_session_is_refused(client, session_factory):
    token = signup(client, "Asha").json()["token"]
    with session_factory() as session:
        session.execute(
            sa.update(m.UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_a_disabled_account_cannot_log_in_and_its_session_stops(client):
    admin = signup(client, "Asha").json()
    ravi = signup(client, "Ravi").json()
    r = client.post(f"/users/{ravi['user']['id']}/disable", headers=bearer(admin["token"]))
    assert r.status_code == 200
    assert client.get("/me", headers=bearer(ravi["token"])).status_code == 401
    login = client.post("/auth/login", json={"email": "ravi@example.com", "password": PASSWORD})
    assert login.status_code == 401
    client.post(f"/users/{ravi['user']['id']}/enable", headers=bearer(admin["token"]))
    assert client.get("/me", headers=bearer(ravi["token"])).status_code == 200


def test_only_administrators_manage_users_and_never_disable_themselves(client):
    admin = signup(client, "Asha").json()
    ravi = signup(client, "Ravi").json()
    assert client.get("/users", headers=bearer(ravi["token"])).status_code == 403
    assert len(client.get("/users", headers=bearer(admin["token"])).json()) == 2
    own = client.post(f"/users/{admin['user']['id']}/disable", headers=bearer(admin["token"]))
    assert own.status_code == 409


def test_guessing_passwords_is_throttled(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 3)
    signup(client, "Asha")
    statuses = [
        client.post(
            "/auth/login", json={"email": "asha@example.com", "password": "bad"}
        ).status_code
        for _ in range(5)
    ]
    assert 429 in statuses


# ------------------------------------------------------------------ my API keys


def make_key(client, token, label="claude", scopes=("read", "propose"), **extra):
    return client.post(
        "/me/keys", headers=bearer(token), json={"label": label, "scopes": list(scopes), **extra}
    )


def test_a_person_generates_a_key_and_it_works_for_an_agent(client):
    token = signup(client, "Asha").json()["token"]
    created = make_key(client, token)
    assert created.status_code == 201
    key = created.json()["key"]
    assert key.startswith("ig_") and created.json()["name"] == "Asha / claude"
    me = client.get("/me", headers=bearer(key)).json()
    assert me["kind"] == "agent" and set(me["scopes"]) == {"read", "propose"}
    listed = client.get("/me/keys", headers=bearer(token)).json()
    assert [k["name"] for k in listed] == ["Asha / claude"] and "key" not in listed[0]


def test_a_generated_key_can_never_decide_or_administer(client):
    token = signup(client, "Asha").json()["token"]
    for scope in ("review", "admin"):
        assert make_key(client, token, scopes=("read", scope)).status_code == 422


def test_a_key_cannot_exceed_the_person_who_made_it(client, monkeypatch):
    monkeypatch.setattr(settings, "signup_scopes", "read")
    signup(client, "Asha")  # the administrator, with the default scopes
    ravi = signup(client, "Ravi").json()["token"]
    assert make_key(client, ravi, scopes=("read", "post")).status_code == 422
    assert make_key(client, ravi, scopes=("read", "propose")).status_code == 201


def test_people_only_see_and_disable_their_own_keys(client):
    asha = signup(client, "Asha").json()["token"]
    ravi = signup(client, "Ravi").json()["token"]
    mine = make_key(client, asha).json()
    assert client.get("/me/keys", headers=bearer(ravi)).json() == []
    other = client.post(f"/me/keys/{mine['id']}/disable", headers=bearer(ravi))
    assert other.status_code == 404
    assert client.post(f"/me/keys/{mine['id']}/disable", headers=bearer(asha)).status_code == 200
    assert client.get("/me", headers=bearer(mine["key"])).status_code == 401


def test_a_persons_keys_stop_working_when_their_account_is_disabled(client):
    admin = signup(client, "Asha").json()["token"]
    ravi = signup(client, "Ravi").json()
    key = make_key(client, ravi["token"]).json()["key"]
    assert client.get("/invoices", headers=bearer(key)).status_code == 200
    client.post(f"/users/{ravi['user']['id']}/disable", headers=bearer(admin))
    assert client.get("/invoices", headers=bearer(key)).status_code == 401


def test_a_key_cannot_manage_keys_and_neither_can_a_shared_env_key(client):
    token = signup(client, "Asha").json()["token"]
    key = make_key(client, token).json()["key"]
    assert client.get("/me/keys", headers=bearer(key)).status_code == 403
    assert make_key(client, key).status_code == 403
    assert client.get("/me/keys", headers={"X-API-Key": "key-env"}).status_code == 403


def test_a_label_can_be_used_once_per_person(client):
    token = signup(client, "Asha").json()["token"]
    assert make_key(client, token).status_code == 201
    assert make_key(client, token).status_code == 409


def test_the_old_shared_keys_still_work(client):
    assert client.get("/me", headers={"X-API-Key": "key-env"}).json()["name"] == "env-reviewer"


def test_creating_an_account_and_a_key_is_audited(client, session_factory):
    token = signup(client, "Asha").json()["token"]
    make_key(client, token)
    with session_factory() as session:
        events = session.scalars(sa.select(m.AuditEvent.event_type).order_by(m.AuditEvent.id)).all()
    assert events == ["account.created", "principal.created"]
