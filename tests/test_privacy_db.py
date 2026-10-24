import json
from pathlib import Path
import socket

import pytest
from fastapi.testclient import TestClient

import build_graph
import server


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_app(monkeypatch, tmp_path):
    host = "localhost"
    port = 6379
    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except OSError:
        pytest.skip("FalkorDB at localhost:6379 is unreachable")
    graph_name = "roomfacts_test"
    monkeypatch.setenv("GRAPH", graph_name)
    temp_optins = tmp_path / "optins.json"
    monkeypatch.setattr(server, "OPTINS", temp_optins)
    monkeypatch.setattr(server, "load_optins", lambda: json.loads(temp_optins.read_text()) if temp_optins.exists() else {})
    monkeypatch.setattr(build_graph, "load_optins", lambda: json.loads(temp_optins.read_text()) if temp_optins.exists() else {})
    build_graph.rebuild(FIXTURES / "luma_sample.json", FIXTURES / "linkedin_sample.json", graph_name)
    server._cache["at"] = 0
    yield TestClient(server.app)
    try:
        build_graph.graph_client(graph_name).delete()
    except Exception:
        pass


def test_public_fact_privacy_and_people_gate(db_app):
    client = db_app
    facts = client.get("/api/facts").json()["facts"]
    assert facts
    assert all(f["n"] >= 3 for f in facts)
    fixture_names = {"Ada One", "Bela Two", "Ciro Three"}
    assert not any(name in json.dumps(facts) for name in fixture_names)
    for fact in facts:
        detail = client.get("/api/fact/" + fact["id"]).json()
        assert detail["n"] >= 3
        assert not any(name in json.dumps(detail) for name in fixture_names)
        assert client.get("/api/fact/" + fact["id"] + "/people").status_code == 403
    assert client.get("/api/fact/school:nyu").status_code == 404
    assert client.get("/api/events").json() == []


def test_optin_hidden_edge_and_token(db_app):
    client = db_app
    response = client.post("/api/optin", json={"person_id": "u1", "hide": ["school:uc-berkeley"]})
    assert response.status_code == 200
    assert client.get("/api/me").json()["id"] == "u1"
    assert client.get("/api/fact/school_company:uc-berkeley>stripe").status_code == 404
    assert client.post("/api/optout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_people_only_opted_in_coholders(db_app):
    client = db_app
    fid = "school_company:uc-berkeley>stripe"
    assert client.post("/api/optin", json={"person_id": "u1", "hide": []}).status_code == 200
    private = client.get("/api/fact/" + fid + "/people")
    assert private.status_code == 200
    assert private.json() == {"people": [], "hidden_count": 2}
    assert client.post("/api/optin", json={"person_id": "u2", "hide": []}).status_code == 200
    private = client.get("/api/fact/" + fid + "/people")
    assert private.status_code == 200
    assert [p["name"] for p in private.json()["people"]] == ["Ada One"]
    assert private.json()["hidden_count"] == 1
    assert client.post("/api/optin", json={"person_id": "u12", "hide": []}).status_code == 200
    assert client.get("/api/fact/" + fid + "/people").status_code == 403


def test_reoptin_without_cookie_keeps_hidden_edge(db_app):
    client = db_app
    assert client.post("/api/optin", json={"person_id": "u1", "hide": ["school:uc-berkeley"]}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/optin", json={"person_id": "u1", "hide": []}).status_code == 200
    assert client.get("/api/fact/school_company:uc-berkeley>stripe").status_code == 404
    assert "school:uc-berkeley" in json.loads(server.OPTINS.read_text())["u1"]["hidden"]


def opt_in_and_review(client, pid, hide=()):
    """Opt in, then approve every pending fact as the phone page's "Review your facts" does."""
    assert client.post("/api/optin", json={"person_id": pid, "hide": list(hide)}).status_code == 200
    pending = [f["fact_id"] for f in client.get(f"/api/person/{pid}/facts").json() if f.get("pending")]
    if pending:
        assert client.post("/api/me/facts", json={"hide": [], "show": pending}).status_code == 200


def test_connections_only_opted_in_people_sharing_a_visible_fact(db_app):
    client = db_app
    assert client.get("/api/connections").status_code == 401
    opt_in_and_review(client, "u1")
    assert client.get("/api/connections").json() == {"people": []}
    opt_in_and_review(client, "u2")
    people = client.get("/api/connections").json()["people"]
    assert [p["name"] for p in people] == ["Ada One"]
    assert "You've both worked at Stripe" in [s["line"] for s in people[0]["shared"]]
    assert people[0]["more"] >= 1
    assert "Ciro Three" not in json.dumps(people)
    opt_in_and_review(client, "u3")
    people = client.get("/api/connections").json()["people"]
    assert [p["name"] for p in people] == ["Ada One", "Bela Two"]
    assert "Stripe" in json.dumps(people)
    assert client.post("/api/optin", json={"person_id": "u3", "hide": ["company:stripe"]}).status_code == 200
    assert "Stripe" not in json.dumps(client.get("/api/connections").json())
    opt_in_and_review(client, "u12")
    assert client.get("/api/connections").json() == {"people": []}


def test_fuzzy_name_search_without_openai(db_app, monkeypatch):
    import assist
    monkeypatch.setattr(assist, "env", lambda name: "")
    client = db_app
    rows = client.get("/api/people/search", params={"q": "Bella Twoo", "fuzzy": 1}).json()
    assert rows and rows[0]["name"] == "Bela Two" and rows[0]["suggested"] is True
    assert client.get("/api/people/search", params={"q": "zzzzqqq", "fuzzy": 1}).json() == []


def test_connections_skip_facts_pending_review(db_app):
    client = db_app
    opt_in_and_review(client, "u2")
    opt_in_and_review(client, "u1")
    assert "Stripe" in json.dumps(client.get("/api/connections").json())
    saved = json.loads(server.OPTINS.read_text())
    stripe = {f["id"] for f in server.snapshot(force=True)["catalog"].values() if "u2" in f["all_holders"] and "stripe" in f["id"]}
    assert "company:stripe" in stripe
    saved["u2"]["pending"] = sorted(set(saved["u2"].get("pending", [])) | stripe)
    server.OPTINS.write_text(json.dumps(saved))
    server._cache["at"] = 0
    assert "Stripe" not in json.dumps(client.get("/api/connections").json())


def test_fuzzy_search_is_rate_limited_per_client(db_app, monkeypatch):
    import assist
    monkeypatch.setattr(assist, "env", lambda name: "")
    monkeypatch.setattr(server, "_fuzzy_hits", {})
    monkeypatch.setattr(server, "_lookups", {})
    client = db_app
    codes = [client.get("/api/people/search", params={"q": f"name{i:02d}", "fuzzy": 1}).status_code for i in range(13)]
    assert codes[:12] == [200] * 12 and codes[12] == 429
    other = client.get("/api/people/search", params={"q": "name99", "fuzzy": 1}, headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200


def test_connections_see_hides_written_by_another_process(db_app):
    client = db_app
    opt_in_and_review(client, "u2")
    opt_in_and_review(client, "u1")
    assert "Stripe" in json.dumps(client.get("/api/connections").json())
    # Another server process hides Stripe for u2: it edits the graph and optins.json, not this cache.
    saved = json.loads(server.OPTINS.read_text())
    stripe = {f["id"] for f in server.snapshot()["catalog"].values() if "u2" in f["all_holders"] and "stripe" in f["id"]}
    saved["u2"]["hidden"] = sorted(set(saved["u2"].get("hidden", [])) | stripe)
    for fid in stripe:
        build_graph.set_hidden(build_graph.graph_client(), "u2", fid)
    server.OPTINS.write_text(json.dumps(saved))
    assert "Stripe" not in json.dumps(client.get("/api/connections").json())
