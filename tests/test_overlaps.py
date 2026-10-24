import hashlib

from fastapi.testclient import TestClient

import server
from build_graph import prepare
from facts import fact_catalog
from normalize import field_names


def row(pid, rel, label, eid, name, *, hidden=False, opted=False):
    return (pid, rel, label, eid, name, hidden, opted, False)


def test_field_of_study_becomes_a_fact():
    assert field_names("Data Science & Analytics, statistics/Data Science and Analytics") == ["Data Science and Analytics", "Statistics"]
    assert field_names("B.S.") == [] and field_names(None) == []
    luma = [{"api_id": f"u{i}", "first_name": "A", "last_name": str(i), "linkedin_handle": f"/in/a-{i}"} for i in range(3)]
    linkedin = [{"linkedin_id": f"a-{i}", "education": [{"title": f"School {i}", "field": "Data Science"}]} for i in range(3)]
    people, entities, edges, matched = prepare(luma, linkedin)
    assert sorted(e["pid"] for e in edges["field"]) == ["u0", "u1", "u2"] and {e["id"] for e in edges["field"]} == {"data-science"}
    fact = fact_catalog([row(f"u{i}", "STUDIED_FIELD", "Field", "data-science", "Data Science") for i in range(3)])["field:data-science"]
    assert fact["eligible"] and fact["line"] == "people here studied Data Science" and fact["line_you"] == "You studied Data Science"


def overlap_app(monkeypatch, rows, opted, tokens):
    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def ro_query(self, query, params=None):
            assert "p.opted_in=true" in query
            return Result([(pid, pid.upper(), "", pid) for pid in params["ids"] if pid in opted])

    rows = [(*r[:6], r[0] in opted, *r[7:]) for r in rows]
    catalog = fact_catalog(rows)
    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid, "name": pid.upper(), "avatar": "", "linkedin": "", "opted_in": pid in opted})
    monkeypatch.setattr(server, "load_optins", lambda: {pid: {"tokens": [hashlib.sha256(token.encode()).hexdigest()]} for pid, token in tokens.items()})
    return TestClient(server.app), catalog


def test_overlaps_include_broad_facts_for_opted_in_people_only(monkeypatch):
    rows = [row(f"x{i}", "LIVES_IN", "City", "sf", "San Francisco") for i in range(40)]
    rows += [row(pid, "LIVES_IN", "City", "sf", "San Francisco", hidden=pid == "p3") for pid in ("p0", "p1", "p2", "p3")]
    rows += [row(pid, "STUDIED_FIELD", "Field", "data-science", "Data Science") for pid in ("p0", "p1", "p4")]
    rows += [row(pid, "SPEAKS", "Language", "tamil", "Tamil") for pid in ("p0", "p1")]
    client, catalog = overlap_app(monkeypatch, rows, opted={"p0", "p1", "p3"}, tokens={"p0": "t0"})
    assert not catalog["city:sf"]["eligible"] and catalog["city:sf"]["n"] == 43
    assert client.get("/api/me/overlaps").status_code == 401

    public = {f["fact_id"]: f for f in client.get("/api/person/p0/facts").json()}
    assert set(public) == {"city:sf", "field:data-science"} and public["city:sf"]["n"] == 43 and public["city:sf"]["n_if_eligible"] is None

    client.cookies.set("rf_token", "t0")
    people = client.get("/api/me/overlaps").json()["people"]
    assert [p["name"] for p in people] == ["P1"]  # p2 and p4 never opted in; p3 hid their city
    assert people[0]["shared"] == [{"fact_id": "field:data-science", "line": "You both studied Data Science", "n": 3},
                                   {"fact_id": "city:sf", "line": "You both live in San Francisco", "n": 43}]
    assert "tamil" not in str(people)  # a 2-person fact never shows
