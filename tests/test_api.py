from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from backend.catalog import PRODUCTS, CATALOG
from backend.main import create_app
from backend.db import database


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "test.db")


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        response = c.post("/api/auth/register", json={"email":"owner@example.test", "password":"a-long-test-password"})
        assert response.status_code == 201
        yield c


def create(client, slug="scope", payload=None):
    r = client.post(f"/api/products/{slug}/records", json={"title": f"Test {slug}", "payload": payload or deepcopy(CATALOG[slug]["sample"])})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("product", PRODUCTS, ids=lambda p:p["slug"])
def test_all_products_save_reopen_and_export(client, product):
    slug = product["slug"]
    row = create(client, slug)
    loaded = client.get(f"/api/records/{row['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["result"]["metrics"] == row["result"]["metrics"]
    exported = client.get(f"/api/records/{row['id']}/export")
    assert exported.status_code == 200
    assert exported.json()["record"]["payload"] == row["payload"]
    assert "attachment" in exported.headers["content-disposition"]
    assert client.get(f"/api/products/{slug}/scope").status_code == 200


def test_unauthenticated_access_is_rejected(app):
    with TestClient(app) as c:
        for path in ("/api/records", "/api/products", "/api/auth/me"):
            assert c.get(path).status_code == 401
        assert c.get("/api/health").status_code == 200


def test_cross_account_access_is_rejected(client):
    r = create(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email":"other@example.test", "password":"another-test-password"})
    assert client.get("/api/records").json() == []
    for suffix in ("", "/audit", "/export"):
        assert client.get(f"/api/records/{r['id']}{suffix}").status_code == 404
    assert client.put(f"/api/records/{r['id']}", json={"title":"take over", "payload":r["payload"], "version":1}).status_code == 404
    assert client.post(f"/api/records/{r['id']}/status", json={"status":"archived", "version":1}).status_code == 404


def test_update_requires_current_version_and_resets_review(client):
    p = deepcopy(CATALOG["scope"]["sample"]); p["decision"] = "Change required"
    r = create(client, payload=p)
    reviewed = client.post(f"/api/records/{r['id']}/status", json={"status":"reviewed", "version":1}).json()
    assert reviewed["version"] == 2
    assert client.put(f"/api/records/{r['id']}", json={"title":"stale", "payload":p, "version":1}).status_code == 409
    updated = client.put(f"/api/records/{r['id']}", json={"title":"Revision", "payload":p, "version":2})
    assert updated.status_code == 200
    assert updated.json()["status"] == "draft" and updated.json()["version"] == 3
    history = client.get(f"/api/records/{r['id']}/audit").json()
    assert [e["action"] for e in history] == ["updated", "reviewed", "created"]
    assert history[-1]["snapshot"]["title"] == "Test scope"


def test_backend_review_guards_cannot_be_bypassed(client):
    r = create(client)
    response = client.post(f"/api/records/{r['id']}/status", json={"status":"reviewed", "version":1})
    assert response.status_code == 422
    assert client.post(f"/api/records/{r['id']}/status", json={"status":"accepted", "version":1}).status_code == 409


def test_archive_is_reversible_and_read_only(client):
    r = create(client)
    assert client.post(f"/api/records/{r['id']}/status", json={"status":"archived", "version":1}).status_code == 200
    assert client.put(f"/api/records/{r['id']}", json={"title":"overwrite", "payload":r["payload"], "version":2}).status_code == 409
    assert client.post(f"/api/records/{r['id']}/status", json={"status":"draft", "version":2}).status_code == 200


def test_logout_revokes_session(client):
    cookie = client.cookies.get("doaide_session")
    client.post("/api/auth/logout")
    client.cookies.set("doaide_session", cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_origin_boundary(client):
    response = client.post("/api/products/scope/preview", json=CATALOG["scope"]["sample"], headers={"Origin":"https://malicious.example"})
    assert response.status_code == 403


def test_invalid_payload_returns_validation_error_not_server_failure(client):
    p = deepcopy(CATALOG["scope"]["sample"]); p["rate"] = "NaN"
    assert client.post("/api/products/scope/records", json={"title":"Bad", "payload":p}).status_code == 422
    assert client.post("/api/products/scope/records", json={"title":"  ", "payload":CATALOG["scope"]["sample"]}).status_code == 422


def test_records_survive_app_restart(tmp_path):
    path = tmp_path / "persistent.db"
    with TestClient(create_app(path)) as c:
        c.post("/api/auth/register", json={"email":"persist@example.test", "password":"persistent-test-password"})
        r = create(c, "renew")
    with TestClient(create_app(path)) as c:
        assert c.post("/api/auth/login", json={"email":"persist@example.test", "password":"persistent-test-password"}).status_code == 200
        assert c.get(f"/api/records/{r['id']}").json()["title"] == "Test renew"


def test_password_and_session_are_not_stored_in_plaintext(tmp_path):
    path = tmp_path / "auth.db"
    with TestClient(create_app(path)) as c:
        r = c.post("/api/auth/register", json={"email":"hash@example.test", "password":"sensitive-test-password"})
        token = c.cookies.get("doaide_session")
        assert "httponly" in r.headers["set-cookie"].lower()
        with database(path) as db:
            password = db.execute("SELECT password_hash FROM users").fetchone()[0]
            stored = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        assert "sensitive-test-password" not in password and password.startswith("scrypt$")
        assert token != stored and len(stored) == 64
