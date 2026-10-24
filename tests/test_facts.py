from facts import fact_catalog, fact_path, graph_rows, public_fact, rotation
from build_graph import prepare, set_hidden


def test_eligibility_hidden_and_duplicate_path_preference():
    rows = []
    for pid in ("u1", "u2", "u3"):
        rows.extend([(pid, "STUDIED_AT", "School", "uc-berkeley", "UC Berkeley", False, False), (pid, "WORKED_AT", "Company", "stripe", "Stripe", False, False)])
    rows.append(("u4", "STUDIED_AT", "School", "nyu", "NYU", False, False))
    catalog = fact_catalog(rows)
    assert catalog["school_company:uc-berkeley>stripe"]["eligible"]
    assert not catalog["school:uc-berkeley"]["eligible"]
    assert not catalog["company:stripe"]["eligible"]
    assert not catalog["school:nyu"]["eligible"]
    assert len(rotation(catalog)) == 1
    assert "holders" not in public_fact(rotation(catalog)[0])
    rows[0] = ("u1", "STUDIED_AT", "School", "uc-berkeley", "UC Berkeley", True, False)
    hidden = fact_catalog(rows)
    assert hidden["school_company:uc-berkeley>stripe"]["n"] == 2
    assert not hidden["school_company:uc-berkeley>stripe"]["eligible"]


def test_above_maximum_is_not_public():
    rows = [(f"u{i}", "SPEAKS", "Language", "hindi", "Hindi", False, False) for i in range(26)]
    assert not fact_catalog(rows)["language:hindi"]["eligible"]


def row(pid, rel, label, eid, name, current=False, hidden=False):
    return (pid, rel, label, eid, name, hidden, False, current)


def test_minimum_and_kind_maximum():
    rows = []
    for eid, n in (("two", 2), ("three", 3), ("twelve", 12), ("thirteen", 13)):
        rows += [row(f"{eid}-{i}", "SPEAKS", "Language", eid, eid) for i in range(n)]
    catalog = fact_catalog(rows)
    assert [catalog[f"language:{eid}"]["eligible"] for eid in ("two", "three", "twelve", "thirteen")] == [False, True, True, True]


def test_current_and_past_company_lines_and_stealth():
    rows = [row(f"c{i}", "WORKED_AT", "Company", "mote", "Mote", True) for i in range(3)]
    rows += [row(f"s{i}", "WORKED_AT", "Company", "stealth", "a stealth startup", True) for i in range(3)]
    rows += [row(f"p{i}", "WORKED_AT", "Company", "past", "Past Co", i < 2) for i in range(3)]
    catalog = fact_catalog(rows)
    assert catalog["company:mote"]["line"] == "people here work at Mote"
    assert catalog["company:mote"]["line_you"] == "You work at Mote"
    assert catalog["company:mote"]["line_event"] == "Someone who works at Mote"
    assert catalog["company:stealth"]["line"] == "people here work at a stealth startup"
    assert catalog["company:past"]["line"] == "people here have worked at Past Co"
    assert catalog["company:past"]["line_event"] == "Someone who has worked at Past Co"


def test_issuer_two_hop_fact_and_hidden_certification():
    luma = [{"api_id": "u", "linkedin_handle": "/in/u"}]
    linkedin = [{"linkedin_id": "u", "certifications": [{"title": "AI Course", "subtitle": "Hugging Face"}]}]
    _, entities, edges, _ = prepare(luma, linkedin)
    assert entities["Issuer"] == [{"id": "hugging-face", "name": "Hugging Face"}]
    assert edges["cert_issuer"] == [{"cert_id": "ai-course", "id": "hugging-face"}]
    _, _, split_edges, _ = prepare(
        [{"api_id": "u0", "linkedin_handle": "/in/u0"}, {"api_id": "u1", "linkedin_handle": "/in/u1"}],
        [{"linkedin_id": "u0", "certifications": [{"title": "Shared Title", "subtitle": "Issuer One"}]},
         {"linkedin_id": "u1", "certifications": [{"title": "Shared Title", "subtitle": "Issuer Two"}]}],
    )
    assert {e["id"] for e in split_edges["cert"]} == {"shared-title--issuer-one", "shared-title--issuer-two"}
    assert {e["cert_id"] for e in split_edges["cert_issuer"]} == {"shared-title--issuer-one", "shared-title--issuer-two"}
    rows = [row(f"u{i}", "ISSUED_BY", "Issuer", "hugging-face", "Hugging Face") for i in range(3)]
    catalog = fact_catalog(rows)
    issuer = catalog["cert_issuer:hugging-face"]
    assert issuer["eligible"] and issuer["src"] == "LinkedIn certifications"
    assert "CERTIFIED" in issuer["pattern"] and "ISSUED_BY" in issuer["pattern"]
    assert issuer["line"] == "people here have certifications from Hugging Face"
    assert fact_path(issuer) == ["You", "CERTIFIED", "a certification", "ISSUED_BY", "Hugging Face", "2 others"]
    duplicate_rows = rows + [row(f"u{i}", "CERTIFIED", "Cert", "ai-course", "AI Course") for i in range(3)]
    duplicate_catalog = fact_catalog(duplicate_rows)
    assert duplicate_catalog["cert_issuer:hugging-face"]["eligible"]
    assert not duplicate_catalog["cert:ai-course"]["eligible"]
    rows[0] = row("u0", "ISSUED_BY", "Issuer", "hugging-face", "Hugging Face", hidden=True)
    assert fact_catalog(rows)["cert_issuer:hugging-face"]["n"] == 2

    class Graph:
        def __init__(self):
            self.calls = []

        def query(self, query, params):
            self.calls.append((query, params))

    graph = Graph()
    set_hidden(graph, "u0", "cert_issuer:hugging-face")
    assert "ISSUED_BY" in graph.calls[0][0]
    assert graph.calls[0][1] == {"pid": "u0", "eid": "hugging-face", "hidden": True}


def test_rebuild_creates_issuer_relationship_and_graph_rows_reads_it(tmp_path, monkeypatch):
    import json
    import build_graph
    import facts

    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def __init__(self):
            self.calls = []

        def delete(self):
            pass

        def query(self, query, params=None):
            self.calls.append((query, params))

        def ro_query(self, query):
            if "ISSUED_BY" in query:
                return Result([row(f"u{i}", "ISSUED_BY", "Issuer", "hugging-face", "Hugging Face") for i in range(3)])
            return Result([])

    graph = Graph()
    luma_path, linkedin_path = tmp_path / "luma.json", tmp_path / "linkedin.json"
    luma_path.write_text(json.dumps([{"api_id": "u0", "linkedin_handle": "/in/u0"}]))
    linkedin_path.write_text(json.dumps([{"linkedin_id": "u0", "certifications": [{"title": "AI Course", "subtitle": "Hugging Face"}]}]))
    monkeypatch.setattr(build_graph, "graph_client", lambda name: graph)
    monkeypatch.setattr(build_graph, "load_optins", lambda: {})
    monkeypatch.setattr(facts, "eligible_facts", lambda g: [])
    build_graph.rebuild(luma_path, linkedin_path, "test")
    assert any("CREATE INDEX FOR (x:Issuer)" in query for query, _ in graph.calls)
    assert any("MERGE (c)-[:ISSUED_BY]->(i)" in query for query, _ in graph.calls)
    assert fact_catalog(graph_rows(graph))["cert_issuer:hugging-face"]["n"] == 3


def test_rotation_caps_leave_catalog_facts_available(monkeypatch):
    import server
    rows = []
    for kind, rel, label, count in (("cert", "CERTIFIED", "Cert", 14), ("cert_issuer", "ISSUED_BY", "Issuer", 12), ("language", "SPEAKS", "Language", 2)):
        for index in range(count):
            n = 3 + index % 3
            rows += [row(f"{kind}-{index}-{i}", rel, label, f"{kind}-{index:02}", f"{kind} {index}") for i in range(n)]
    catalog = fact_catalog(rows)
    ids = [f["id"] for f in rotation(catalog)]
    assert sum(fid.startswith("cert:") for fid in ids) == 3
    assert sum(fid.startswith("cert_issuer:") for fid in ids) == 3
    assert [f["kind"] for f in rotation(catalog)[:3]] == ["language", "cert", "cert_issuer"]
    left_out = catalog["cert:cert-08"]
    assert left_out["eligible"] and left_out not in rotation(catalog)
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid})
    assert server.fact_detail(left_out["id"])["id"] == left_out["id"]
    assert any(f["fact_id"] == left_out["id"] for f in server.person_facts("cert-8-0"))
    monkeypatch.setattr(server, "_events", [{"at": "2026-10-24T00:00:00+00:00", "text": "A capped fact", "fact_id": left_out["id"]}])
    assert server.events() == [{"at": "2026-10-24T00:00:00+00:00", "text": "A capped fact"}]


def test_event_and_you_grammar_all_kinds():
    cases = [
        ("school", "STUDIED_AT", "School", "y-combinator", "Y Combinator", "went through Y Combinator", "went through Y Combinator"),
        ("city", "LIVES_IN", "City", "london-gb", "London", "lives in London", "live in London"),
        ("country", "BASED_IN", "Country", "GB", "United Kingdom", "is based in the United Kingdom", "are based in the United Kingdom"),
        ("language", "SPEAKS", "Language", "sanskrit", "Sanskrit", "speaks Sanskrit", "speak Sanskrit"),
        ("cert", "CERTIFIED", "Cert", "ai", "AI", "holds the AI certification", "hold the AI certification"),
        ("cert_issuer", "ISSUED_BY", "Issuer", "linux", "The Linux Foundation", "has certifications from The Linux Foundation", "have certifications from The Linux Foundation"),
        ("volunteer", "VOLUNTEERED_AT", "Org", "shelter", "Shelter", "has volunteered at Shelter", "have volunteered at Shelter"),
        ("cause", "VOLUNTEERS_FOR", "Cause", "animal-welfare", "Animal Welfare", "volunteers for Animal Welfare", "volunteer for Animal Welfare"),
    ]
    for kind, rel, label, eid, name, event, you in cases:
        rows = [row(f"{kind}-{i}", rel, label, eid, name) for i in range(3)]
        fact = fact_catalog(rows)[f"{kind}:{eid}"]
        if eid == "y-combinator":
            assert fact["line"] == "people here went through Y Combinator"
        assert fact["line_event"] == "Someone who " + event
        assert fact["line_you"] == "You " + you
        assert rotation({fact["id"]: fact}) == ([] if kind == "country" else [fact])
    rows = []
    for i in range(3):
        rows += [row(f"path-{i}", "STUDIED_AT", "School", "nyu", "NYU"), row(f"path-{i}", "WORKED_AT", "Company", "mote", "Mote")]
        rows += [row(f"both-{i}", "WORKED_AT", "Company", "alpha", "Alpha"), row(f"both-{i}", "WORKED_AT", "Company", "beta", "Beta")]
    catalog = fact_catalog(rows)
    assert catalog["school_company:nyu>mote"]["line_event"] == "Someone who went from NYU to Mote"
    assert catalog["school_company:nyu>mote"]["line_you"] == "You went from NYU to Mote"
    assert catalog["company_company:alpha>beta"]["line_event"] == "Someone who has worked at both Alpha and Beta"
    assert catalog["company_company:alpha>beta"]["line_you"] == "You have worked at both Alpha and Beta"


def test_optin_event_uses_third_person_line(monkeypatch):
    from fastapi import Response
    import server

    class Graph:
        def query(self, query, params):
            pass

    catalog = fact_catalog([row(f"u{i}", "SPEAKS", "Language", "hindi", "Hindi") for i in range(3)])
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid, "name": "", "avatar": "", "linkedin": ""})
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "graph", lambda: Graph())
    monkeypatch.setattr(server, "load_optins", lambda: {})
    monkeypatch.setattr(server, "save_optins", lambda data: None)
    monkeypatch.setattr(server, "_events", [])
    server.optin(server.OptInBody(person_id="u0"), Response())
    assert server._events[0]["text"] == "Someone who speaks Hindi just opted in"
