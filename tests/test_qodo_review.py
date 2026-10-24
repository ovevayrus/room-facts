import hashlib

import pytest
from fastapi.testclient import TestClient

import server
from build_graph import set_hidden
from facts import fact_catalog, hidden_combos_from_optins, rotation


def row(pid, rel, label, eid, name, *, hidden=False, current=False):
    return (pid, rel, label, eid, name, hidden, False, current)


def test_person_facts_public_subset_and_owner_cookie(monkeypatch):
    rows = [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    rows += [row(pid, "WORKED_AT", "Company", "co", "Example Co", hidden=pid == "p0") for pid in ("p0", "p3", "p4", "p5")]
    rows += [row(pid, "CERTIFIED", "Cert", "rare", "Rare Cert") for pid in ("p0", "p6")]
    catalog = fact_catalog(rows)
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid, "opted_in": True})
    states = {pid: {"tokens": [hashlib.sha256(token.encode()).hexdigest()]}
              for pid, token in (("p0", "own-token"), ("p1", "other-token"))}
    monkeypatch.setattr(server, "load_optins", lambda: states)
    client = TestClient(server.app)

    public = client.get("/api/person/p0/facts")
    assert public.status_code == 200
    assert [fact["fact_id"] for fact in public.json()] == ["school:uni"]
    assert all(fact["n_if_eligible"] is not None and fact["n_if_eligible"] >= 3 and "hidden" not in fact
               for fact in public.json())

    client.cookies.set("rf_token", "other-token")
    assert client.get("/api/person/p0/facts").json() == public.json()
    client.cookies.set("rf_token", "own-token")
    private = client.get("/api/person/p0/facts").json()
    assert len(private) > len(public.json())
    assert any(f["n_if_eligible"] is None for f in private)
    assert any(f["hidden"] for f in private)
    assert all("hidden" in f for f in private)


def test_optin_accepts_hides_not_shown_before_optin(monkeypatch):
    catalog = fact_catalog([row(pid, "CERTIFIED", "Cert", "rare", "Rare Cert") for pid in ("p0", "p1")])
    saved = {}

    class Graph:
        def query(self, query, params):
            pass

    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid, "name": "", "avatar": "", "linkedin": ""})
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "load_optins", lambda: saved)
    monkeypatch.setattr(server, "save_optins", lambda state: saved.update(state))
    monkeypatch.setattr(server, "_events", [])
    client = TestClient(server.app)
    assert client.get("/api/person/p0/facts").json() == []
    response = client.post("/api/optin", json={"person_id": "p0", "hide": ["cert:rare"]})
    assert response.status_code == 200
    assert saved["p0"]["hidden"] == ["cert:rare"]


def test_specific_school_beats_duplicate_study_country():
    rows = []
    for pid in ("p0", "p1", "p2"):
        rows += [row(pid, "STUDIED_AT", "School", "uni", "Example U"),
                 row(pid, "LOCATED_IN", "Country", "GB", "United Kingdom")]
    catalog = fact_catalog(rows)
    assert catalog["school:uni"]["eligible"]
    assert not catalog["study_country:GB"]["eligible"]
    assert "school:uni" in {fact["id"] for fact in rotation(catalog)}


@pytest.mark.parametrize("rel,label,kind", [
    ("HQ_IN", "Country", "company_country"),
    ("IS_A", "OrgKind", "org_kind"),
    ("FOUNDED_IN", "Year", "founded_year"),
    ("AT_STAGE", "Stage", "funding_stage"),
])
def test_specific_company_beats_duplicate_broad_path(rel, label, kind):
    rows = []
    for pid in ("p0", "p1", "p2"):
        rows += [row(pid, "WORKED_AT", "Company", "co", "Example Co", current=True),
                 row(pid, rel, label, "target", "Target", current=True)]
    catalog = fact_catalog(rows)
    assert catalog["company:co"]["eligible"]
    assert not catalog[f"{kind}:target"]["eligible"]


def test_hidden_school_industry_combo_preserves_plain_facts(monkeypatch):
    fid = "school_industry:uni>robotics"
    rows = []
    for pid in ("p0", "p1", "p2"):
        rows += [row(pid, "STUDIED_AT", "School", "uni", "Example U"),
                 row(pid, "IN_INDUSTRY", "Industry", "robotics", "Robotics"),
                 (pid, "COMBO_school_industry", "Industry", ("uni", "robotics"), ("Example U", "Robotics"), False, False)]
    rows += [row("school-only", "STUDIED_AT", "School", "uni", "Example U"),
             row("industry-only", "IN_INDUSTRY", "Industry", "robotics", "Robotics")]
    optins = {"p0": {"hidden": [fid]}}
    catalog = fact_catalog(rows, hidden_combos=hidden_combos_from_optins(optins))
    for parent in ("school:uni", "industry:robotics"):
        assert catalog[parent]["eligible"] and catalog[parent]["n"] == 4
        assert "p0" in catalog[parent]["holders"]
        assert "p0" not in catalog[parent]["hidden_holders"]
    combo = catalog[fid]
    assert combo["n"] == 2 and not combo["eligible"]
    assert "p0" in combo["hidden_holders"] and "p0" in combo["all_holders"]

    monkeypatch.setattr(server, "graph", lambda: object())
    monkeypatch.setattr(server, "graph_rows", lambda graph: rows)
    monkeypatch.setattr(server, "load_optins", lambda: optins)
    monkeypatch.setattr(server, "_cache", {"at": 0.0, "catalog": {}, "facts": [], "generated_at": ""})
    live = server.snapshot(force=True)["catalog"]
    assert live[fid]["n"] == 2 and live["school:uni"]["n"] == live["industry:robotics"]["n"] == 4

    class Graph:
        def query(self, query, params):
            raise AssertionError("combo hiding must not change graph edges")

    set_hidden(Graph(), "p0", fid)
