"""A confirmation can review private facts, but cannot disclose other attendees."""
import hashlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import server
from facts import KINDS


def row(pid, rel, label, eid, name):
    return (pid, rel, label, eid, name, False, False, False)


@pytest.fixture
def review_app(monkeypatch):
    rows = [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    rows += [row(pid, "SPEAKS", "Language", "rare", "Rare Language") for pid in ("p0", "p1")]
    saved, mutations = {}, []

    class Graph:
        def query(self, query, params):
            mutations.append((query, params))

    def person(pid):
        if pid not in {item[0] for item in rows}:
            raise HTTPException(404, "Person not found")
        return {"id": pid, "name": "Synthetic attendee", "avatar": "", "linkedin": "", "opted_in": pid in saved}

    def apply_hidden(graph, pid, hidden):
        mutations.append(("apply_hidden", {"pid": pid, "hidden": set(hidden)}))
        for i, item in enumerate(rows):
            if item[0] == pid:
                fid = next((f"{kind}:{item[3]}" for kind, (rel, _) in KINDS.items() if rel == item[1]), "")
                rows[i] = (*item[:5], fid in hidden, *item[6:])

    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "graph_rows", lambda graph: rows)
    monkeypatch.setattr(server, "person_row", person)
    monkeypatch.setattr(server, "load_optins", lambda: saved)
    monkeypatch.setattr(server, "save_optins", lambda state: saved.update(state))
    monkeypatch.setattr(server, "apply_hidden", apply_hidden)
    monkeypatch.setattr(server, "_cache", {"at": 0.0, "catalog": {}, "facts": [], "generated_at": ""})
    monkeypatch.setattr(server, "_reviews", {})
    monkeypatch.setattr(server, "_review_hits", {})
    monkeypatch.setattr(server, "_events", [])
    return TestClient(server.app), rows, saved, mutations


def test_confirmation_reviews_every_fact_without_joining_or_revealing_people(review_app):
    client, _, saved, mutations = review_app
    public = client.get("/api/person/p0/facts").json()
    assert [f["fact_id"] for f in public] == ["school:uni"]
    response = client.post("/api/review-session", json={"person_id": "p0"})
    assert response.status_code == 200
    facts = {f["fact_id"]: f for f in response.json()["facts"]}
    assert set(facts) == {"school:uni", "language:rare"}
    assert facts["language:rare"]["n_if_eligible"] is None
    assert "rf_review" in client.cookies and "rf_token" not in client.cookies
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    assert saved == {} and mutations == []
    assert len(client.get("/api/person/p0/facts").json()) == 2
    # A review cookie is neither an opt-in nor permission to inspect another profile's rare facts.
    assert [f["fact_id"] for f in client.get("/api/person/p1/facts").json()] == ["school:uni"]
    for path in ("/api/me", "/api/connections"):
        assert client.get(path).status_code == 401
    assert client.get("/api/fact/school:uni/people").status_code == 403
    assert client.post("/api/me/facts", json={"show": ["language:rare"]}).status_code == 401
    assert client.post("/api/optout").status_code == 401
    anonymous = TestClient(server.app)
    assert [f["fact_id"] for f in anonymous.get("/api/person/p0/facts").json()] == ["school:uni"]


def test_final_selection_accepts_rare_facts_and_leaves_unseen_facts_pending(review_app):
    client, rows, saved, _ = review_app
    client.post("/api/review-session", json={"person_id": "p0"}).raise_for_status()
    rows.append(row("p0", "VOLUNTEERS_FOR", "Cause", "new", "New cause"))
    server.snapshot(force=True)
    assert "cause:new" not in {f["fact_id"] for f in client.get("/api/person/p0/facts").json()}
    response = client.post("/api/optin", json={"person_id": "p0", "show": ["language:rare"], "hide": ["school:uni"]})
    assert response.status_code == 200
    assert saved["p0"]["approved"] == ["language:rare"]
    assert saved["p0"]["hidden"] == [] and saved["p0"]["fact_hidden"] == ["school:uni"]
    assert saved["p0"]["pending"] == ["cause:new"]
    assert "rf_review" not in client.cookies and server._reviews == {}
    assert client.get("/api/me").status_code == 200
    catalog = server.snapshot(force=True)["catalog"]
    assert "p0" in catalog["language:rare"]["holders"]
    assert "p0" not in catalog["school:uni"]["holders"]
    assert "p0" not in catalog["cause:new"]["holders"]


def test_unchecked_reviewed_facts_are_hidden_even_when_hide_is_omitted(review_app):
    client, _, saved, _ = review_app
    client.post("/api/review-session", json={"person_id": "p0"}).raise_for_status()
    assert client.post("/api/optin", json={"person_id": "p0", "show": []}).status_code == 200
    assert saved["p0"]["approved"] == []
    assert saved["p0"]["hidden"] == [] and saved["p0"]["fact_hidden"] == ["language:rare", "school:uni"]


def test_invalid_or_changed_selection_does_not_consume_review(review_app):
    client, rows, saved, mutations = review_app
    client.post("/api/review-session", json={"person_id": "p0"}).raise_for_status()
    assert client.post("/api/optin", json={"person_id": "p1", "show": ["language:rare"]}).status_code == 401
    assert client.post("/api/optin", json={"person_id": "p0", "show": ["company:nope"]}).status_code == 422
    assert client.post("/api/optin", json={"person_id": "p0", "show": ["school:uni"], "hide": ["school:uni"]}).status_code == 422
    rows.append(row("p0", "VOLUNTEERS_FOR", "Cause", "new", "New cause"))
    assert client.post("/api/optin", json={"person_id": "p0", "show": ["cause:new"]}).status_code == 409
    assert saved == {} and mutations == [] and len(server._reviews) == 1
    assert client.post("/api/optin", json={"person_id": "p0", "show": ["school:uni"]}).status_code == 200


def test_expired_review_requires_confirmation_again_without_mutation(review_app, monkeypatch):
    client, _, saved, mutations = review_app
    client.post("/api/review-session", json={"person_id": "p0"}).raise_for_status()
    monkeypatch.setattr(server, "REVIEW_TTL", -1)
    assert [f["fact_id"] for f in client.get("/api/person/p0/facts").json()] == ["school:uni"]
    response = client.post("/api/optin", json={"person_id": "p0", "show": ["school:uni"]})
    assert response.status_code == 401 and "review" in response.json()["detail"]
    assert saved == {} and mutations == []


def test_cookieless_review_preserves_hides_old_tokens_and_timestamp(review_app):
    client, _, saved, _ = review_app
    old_digest = hashlib.sha256(b"old-device").hexdigest()
    saved["p0"] = {"hidden": ["language:rare"], "approved": ["school:uni"], "pending": [],
                   "tokens": [old_digest], "opted_in_at": "2026-10-24T00:00:00+00:00", "seeded": True}
    facts = client.post("/api/review-session", json={"person_id": "p0"}).json()["facts"]
    assert next(f for f in facts if f["fact_id"] == "language:rare")["locked_hidden"]
    # Even a manually modified selection cannot restore a prior hide without the owner's cookie.
    assert client.post("/api/optin", json={"person_id": "p0", "show": ["language:rare", "school:uni"]}).status_code == 200
    assert saved["p0"]["hidden"] == ["language:rare"] and saved["p0"]["approved"] == ["school:uni"]
    assert old_digest in saved["p0"]["tokens"] and len(saved["p0"]["tokens"]) == 2
    assert saved["p0"]["opted_in_at"] == "2026-10-24T00:00:00+00:00" and saved["p0"]["seeded"]
    old_device = TestClient(server.app)
    old_device.cookies.set("rf_token", "old-device")
    assert old_device.get("/api/me").status_code == 200
    assert old_device.post("/api/optin", json={"person_id": "p0", "show": ["language:rare", "school:uni"]}).status_code == 200
    assert saved["p0"]["hidden"] == []


def test_review_sessions_are_bounded_and_https_cookie_is_secure(review_app, monkeypatch):
    _, _, saved, mutations = review_app
    monkeypatch.setattr(server, "REVIEW_LIMIT", 2)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    clients = [TestClient(server.app, base_url="https://example.test") for _ in range(3)]
    for client in clients[:2]:
        response = client.post("/api/review-session", json={"person_id": "p0"})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
    assert clients[2].post("/api/review-session", json={"person_id": "p0"}).status_code == 429
    assert len(server._reviews) == 2
    assert saved == {} and mutations == []
    assert clients[0].post("/api/optin", json={"person_id": "p0", "show": []}).status_code == 200


def test_repeated_reviews_use_cache_and_rate_limit_before_graph_reads(review_app, monkeypatch):
    client, _, saved, mutations = review_app
    calls = []
    original = server.graph_rows
    monkeypatch.setattr(server, "graph_rows", lambda graph: (calls.append(1), original(graph))[1])
    for _ in range(60):
        assert client.post("/api/review-session", json={"person_id": "p0"}).status_code == 200
    assert len(calls) == 1
    assert client.post("/api/review-session", json={"person_id": "p0"}).status_code == 429
    assert len(calls) == 1 and saved == {} and mutations == []


def test_device_limit_preserves_existing_sessions_and_owner_reuses_cookie(review_app, monkeypatch):
    client, _, saved, mutations = review_app
    monkeypatch.setattr(server, "MAX_DEVICE_TOKENS", 1)
    assert client.post("/api/optin", json={"person_id": "p0"}).status_code == 200
    original_tokens = list(saved["p0"]["tokens"])
    assert client.post("/api/optin", json={"person_id": "p0"}).status_code == 200
    assert saved["p0"]["tokens"] == original_tokens
    before = len(mutations)
    client.cookies.clear()
    assert client.post("/api/optin", json={"person_id": "p0"}).status_code == 429
    assert saved["p0"]["tokens"] == original_tokens and len(mutations) == before


def test_connected_review_captures_only_facts_with_other_opted_holders(review_app):
    client, rows, saved, mutations = review_app
    rows[:] = [(*item[:6], item[0] == 'p1', *item[7:]) for item in rows]
    rows.append(row('p0', 'WORKED_AT', 'Company', 'solo', 'Solo Company'))
    response = client.post('/api/review-session', json={'person_id': 'p0', 'connections_only': True})
    response.raise_for_status()
    facts = response.json()['facts']
    assert {f['fact_id'] for f in facts} == {'school:uni', 'language:rare'}
    assert all(f['connection_count'] == 1 for f in facts)
    assert saved == {} and mutations == []
    # The invisible solo employer and school/employer path were not declined by the person.
    client.post('/api/optin', json={'person_id': 'p0', 'show': ['school:uni', 'language:rare']}).raise_for_status()
    assert saved['p0']['fact_hidden'] == []
    assert {'company:solo', 'school_company:uni>solo'} <= set(saved['p0']['pending'])
