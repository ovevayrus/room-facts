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
    rows += [row(pid, "SPEAKS", "Language", "rare", "Rare Lang") for pid in ("p0", "p6")]
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
    catalog = fact_catalog([row(pid, "SPEAKS", "Language", "rare", "Rare Lang") for pid in ("p0", "p1")])
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
    response = client.post("/api/optin", json={"person_id": "p0", "hide": ["language:rare"]})
    assert response.status_code == 200
    assert saved["p0"]["hidden"] == ["language:rare"]


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


def optin_app(monkeypatch, rows, saved):
    class Graph:
        def query(self, query, params):
            pass

    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "graph_rows", lambda graph: rows)
    monkeypatch.setattr(server, "_cache", {"at": 0.0, "catalog": {}, "facts": [], "generated_at": ""})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid, "name": "", "avatar": "", "linkedin": "", "opted_in": pid in saved})
    monkeypatch.setattr(server, "load_optins", lambda: saved)
    monkeypatch.setattr(server, "save_optins", lambda state: saved.update(state))
    monkeypatch.setattr(server, "_events", [])
    return TestClient(server.app)


def test_reoptin_without_owner_cookie_keeps_saved_hides(monkeypatch):
    combo = "school_company:uni>co"
    rows = []
    for pid in ("p0", "p1", "p2", "p3"):
        rows += [row(pid, "STUDIED_AT", "School", "uni", "Example U"), row(pid, "WORKED_AT", "Company", "co", "Example Co")]
    rows += [row("school-only", "STUDIED_AT", "School", "uni", "Example U")]
    saved = {"p0": {"hidden": [combo], "pending": [], "tokens": [hashlib.sha256(b"own-token").hexdigest()]}}
    client = optin_app(monkeypatch, rows, saved)
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert combo in saved["p0"]["hidden"]
    assert "p0" not in server.snapshot(force=True)["catalog"][combo]["holders"]

    client.cookies.set("rf_token", "own-token")
    saved["p0"]["tokens"].append(hashlib.sha256(b"own-token").hexdigest())
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["hidden"] == []


def test_unlisted_facts_stay_pending_until_owner_approves(monkeypatch):
    rows = [row(pid, "SPEAKS", "Language", "rare", "Rare Lang") for pid in ("p0", "p1")]
    rows += [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    saved = {}
    client = optin_app(monkeypatch, rows, saved)
    assert [f["fact_id"] for f in client.get("/api/person/p0/facts").json()] == ["school:uni"]
    assert client.post("/api/me/facts", json={"show": ["language:rare"]}).status_code == 401
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["pending"] == ["language:rare"]

    rows += [row("p3", "SPEAKS", "Language", "rare", "Rare Lang")]
    rare = server.snapshot(force=True)["catalog"]["language:rare"]
    assert rare["n"] == 2 and "p0" not in rare["holders"] and not rare["eligible"]
    private = {f["fact_id"]: f for f in client.get("/api/person/p0/facts").json()}
    assert private["language:rare"]["pending"] and not private["language:rare"]["hidden"]
    assert not private["school:uni"]["pending"]

    assert client.post("/api/me/facts", json={"show": ["language:rare"], "hide": ["language:rare"]}).status_code == 422
    assert client.post("/api/me/facts", json={"show": ["company:nope"]}).status_code == 422
    reviewed = {f["fact_id"]: f for f in client.post("/api/me/facts", json={"show": ["language:rare"], "hide": ["school:uni"]}).json()}
    assert saved["p0"]["pending"] == [] and saved["p0"]["hidden"] == ["school:uni"]
    assert not reviewed["language:rare"]["pending"]
    rare = server.snapshot(force=True)["catalog"]["language:rare"]
    assert rare["n"] == 3 and rare["eligible"] and "p0" in rare["holders"]


def test_cookieless_reoptin_keeps_approvals(monkeypatch):
    rows = [row(pid, "SPEAKS", "Language", "rare", "Rare Lang") for pid in ("p0", "p1")]
    saved = {}
    client = optin_app(monkeypatch, rows, saved)
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["pending"] == ["language:rare"]
    assert client.post("/api/me/facts", json={"show": ["language:rare"]}).status_code == 200
    assert saved["p0"]["approved"] == ["language:rare"]
    client.cookies.clear()
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["pending"] == [] and saved["p0"]["approved"] == ["language:rare"]
    assert "p0" in server.snapshot(force=True)["catalog"]["language:rare"]["holders"]


def test_stats_exclude_pending_holders(monkeypatch):
    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def ro_query(self, query, params=None):
            return Result([(3, 3, 1, 0)])

    rows = [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    rows += [row(pid, "WORKED_AT", "Company", "co", "Example Co") for pid in ("p0", "p1", "p2")]
    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "graph_rows", lambda graph: rows)
    monkeypatch.setattr(server, "load_optins", lambda: {"p0": {"pending": ["school:uni"]}})
    monkeypatch.setattr(server, "_cache", {"at": 0.0, "catalog": {}, "facts": [], "generated_at": ""})
    stats = server.stats()
    assert stats["top_schools"] == []
    assert stats["top_companies"] == [{"name": "Example Co", "count": 3}]


@pytest.mark.parametrize("owner", [False, True])
def test_certifications_never_listed_and_stay_pending(monkeypatch, owner):
    rows = [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    rows += [row(pid, "CERTIFIED", "Cert", "aws", "AWS Cloud Practitioner") for pid in ("p0", "p1", "p3")]
    rows += [row(pid, "ISSUED_BY", "Issuer", "amazon", "Amazon Web Services") for pid in ("p0", "p2", "p3", "p4")]
    token = hashlib.sha256(b"own-token").hexdigest()
    saved = {"p0": {"hidden": [], "pending": [], "tokens": [token]}} if owner else {}
    client = optin_app(monkeypatch, rows, saved)
    if owner:
        client.cookies.set("rf_token", "own-token")
    catalog = server.snapshot(force=True)["catalog"]
    assert catalog["cert:aws"]["eligible"] and catalog["cert_issuer:amazon"]["eligible"]
    assert [f["fact_id"] for f in client.get("/api/person/p0/facts").json()] == ["school:uni"]
    response = client.post("/api/optin", json={"person_id": "p0", "hide": []})
    assert response.status_code == 200
    assert saved["p0"]["pending"] == ["cert:aws", "cert_issuer:amazon"] and saved["p0"]["approved"] == ["school:uni"]
    catalog = server.snapshot(force=True)["catalog"]
    assert "p0" not in catalog["cert:aws"]["holders"] and "p0" in catalog["school:uni"]["holders"]
    client.cookies.clear()
    client.cookies.set("rf_token", response.cookies["rf_token"])
    private = client.get("/api/person/p0/facts").json()
    assert [(f["fact_id"], f["pending"]) for f in private] == [("school:uni", False)]


def test_certifications_cannot_be_approved_or_kept_approved(monkeypatch):
    rows = [row(pid, "STUDIED_AT", "School", "uni", "Example U") for pid in ("p0", "p1", "p2")]
    rows += [row(pid, "CERTIFIED", "Cert", "aws", "AWS Cloud Practitioner") for pid in ("p0", "p1", "p3")]
    rows = [(*r[:6], r[0] == "p0", *r[7:]) for r in rows]  # p0 opted in before this change
    token = hashlib.sha256(b"own-token").hexdigest()
    saved = {"p0": {"hidden": [], "approved": ["cert:aws", "school:uni"], "tokens": [token]}}
    client = optin_app(monkeypatch, rows, saved)
    catalog = server.snapshot(force=True)["catalog"]
    assert "p0" not in catalog["cert:aws"]["holders"] and catalog["cert:aws"]["n"] == 2 and not catalog["cert:aws"]["eligible"]
    assert "p0" in catalog["school:uni"]["holders"]

    client.cookies.set("rf_token", "own-token")
    assert client.post("/api/me/facts", json={"show": ["cert:aws"]}).status_code == 422
    client.cookies.clear()
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["approved"] == ["school:uni"]


def test_broad_checklist_facts_are_approved_at_optin(monkeypatch):
    rows = [row(f"x{i}", "LIVES_IN", "City", "sf", "San Francisco") for i in range(30)] + [row("p0", "LIVES_IN", "City", "sf", "San Francisco")]
    saved = {}
    client = optin_app(monkeypatch, rows, saved)
    assert [f["fact_id"] for f in client.get("/api/person/p0/facts").json()] == ["city:sf"]
    assert client.post("/api/optin", json={"person_id": "p0", "hide": []}).status_code == 200
    assert saved["p0"]["approved"] == ["city:sf"] and saved["p0"]["pending"] == []
    assert "p0" in server.snapshot(force=True)["catalog"]["city:sf"]["holders"]
