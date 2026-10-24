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
