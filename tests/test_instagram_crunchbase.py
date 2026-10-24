"""Synthetic Instagram, Crunchbase, and country wording coverage."""

from build_graph import KINDS, ORG_PATHS, prepare, set_hidden
from facts import EVENT_LINES, LINES, ORDER, SRC, YOU_LINES, fact_catalog, fact_path, graph_rows, rotation
from normalize import COUNTRIES, GENERIC_IG_HASHTAGS, country, country_phrase, funding_stage, hashtags, instagram_handle, root_domain
import server


def crunchbase_edges(org_site, records):
    luma = [{"api_id": "u", "linkedin_handle": "/in/ada"}]
    linkedin = [{"linkedin_id": "ada", "current_company": {"name": "Acme", "company_id": "acme", "link": "https://linkedin.com/company/acme"}}]
    orgs = [{"input": {"url": "https://linkedin.com/company/acme"}, "name": "Acme", "website_simplified": org_site}]
    return prepare(luma, linkedin, orgs, crunchbase=records)[2]


def test_source_normalization():
    assert instagram_handle("https://www.instagram.com/Ada.Example/?hl=en") == "ada.example"
    assert instagram_handle("@ADA.Example") == "ada.example"
    assert hashtags("['#FYP', '#BuildInPublic', '#AI', '#buildinpublic']", GENERIC_IG_HASHTAGS) == ["buildinpublic"]
    assert root_domain("https://blog.example.co.uk/path") != root_domain("example.co.uk")
    assert root_domain("https://example.com") != root_domain("https://other.com")
    assert funding_stage("Pre Seed Round") == "Pre-Seed"
    assert funding_stage("Series A") == "Series A"
    assert funding_stage("None") is None
    assert funding_stage("Venture Round") is None
    assert country("ZZ") == ("ZZ", "ZZ")


def test_crunchbase_rejects_shared_hosting_and_cctld_tenants():
    for org_site, other_site in (("https://a.pages.dev", "https://b.pages.dev"),
                                 ("https://a.com.sg", "https://b.com.sg")):
        assert root_domain(org_site) != root_domain(other_site)
        edges = crunchbase_edges(org_site, [{"discovery_input": {"keyword": "Acme"}, "name": "Other Company", "website": other_site,
                                          "investors": [{"name": "Wrong Investor"}], "last_funding_type": "Seed"}])
        assert not edges["investor"] and not edges["funding_stage"]


def test_crunchbase_rejects_matching_name_with_conflicting_websites():
    edges = crunchbase_edges("https://acme.example", [{"discovery_input": {"keyword": "Acme"}, "name": "Acme", "website": "https://other.example",
                                                       "investors": [{"name": "Wrong Investor"}], "last_funding_type": "Seed"}])
    assert not edges["investor"] and not edges["funding_stage"]


def test_crunchbase_selects_one_ranked_record_per_company():
    records = [
        {"discovery_input": {"keyword": "Acme"}, "name": "Acme", "investors": [{"name": "Name Only"}], "last_funding_type": "Pre-Seed"},
        {"discovery_input": {"keyword": "Acme"}, "name": "Other Name", "website": "https://acme.example", "investors": [{"name": "Host Only"}], "last_funding_type": "Seed"},
        {"discovery_input": {"keyword": "Acme"}, "name": "Acme", "website": "https://www.acme.example/path", "investors": [{"name": "Selected Investor"}], "last_funding_type": "Series A"},
        {"discovery_input": {"keyword": "Acme"}, "name": "Acme", "website": "https://acme.example", "investors": [{"name": "Later Investor"}], "last_funding_type": "Series B"},
    ]
    edges = crunchbase_edges("acme.example", records)
    assert {edge["id"] for edge in edges["investor"]} == {"selected-investor"}
    assert [edge["id"] for edge in edges["funding_stage"]] == ["series-a"]


def test_investor_and_stage_count_only_current_employees():
    for kind, rel, label in (("investor", "BACKED_BY", "Investor"), ("funding_stage", "AT_STAGE", "Stage")):
        historical = [("former", rel, label, "sample", "Sample", False, False, False)]
        assert f"{kind}:sample" not in fact_catalog(historical)
        current = [(f"u{i}", rel, label, "sample", "Sample", False, False, True) for i in range(3)]
        fact = fact_catalog(historical + current)[f"{kind}:sample"]
        assert fact["n"] == 3 and fact["all_holders"] == {"u0", "u1", "u2"}
        assert "r.current=true" in fact["pattern"]

    class Result:
        result_set = []

    class Graph:
        def __init__(self):
            self.queries = []

        def ro_query(self, query):
            self.queries.append(query)
            return Result()

    graph = Graph()
    graph_rows(graph)
    assert all("WHERE r.current=true" in query for query in graph.queries if "RETURN p.id, 'BACKED_BY'" in query or "RETURN p.id, 'AT_STAGE'" in query)
    assert "WHERE r.current=true" not in next(query for query in graph.queries if "RETURN p.id, 'IN_INDUSTRY'" in query)
    assert all("WHERE b.current=true" in query for query in graph.queries if "<-[a:STUDIED_AT]" in query)


def test_complete_iso_country_names():
    assert len(COUNTRIES) == 249
    assert country("NG") == ("NG", "Nigeria")
    assert country("PE") == ("PE", "Peru")
    assert country("QA") == ("QA", "Qatar")
    assert country("ZZ") == ("ZZ", "ZZ")


def test_cayman_islands_takes_article_in_fact_lines():
    assert country("KY") == ("KY", "Cayman Islands")
    rows = [(f"u{i}", "LOCATED_IN", "Country", "KY", "KY", False, False) for i in range(3)]
    fact = fact_catalog(rows)["study_country:KY"]
    assert fact["line"] == "people here studied in the Cayman Islands"
    assert fact["line_you"] == "You studied in the Cayman Islands"
    assert fact["line_event"] == "Someone who studied in the Cayman Islands"


def test_prepare_instagram_and_verified_crunchbase():
    luma = [{"api_id": "u", "linkedin_handle": "/in/ada", "instagram_handle": "@Ada.Example"}]
    linkedin = [{"linkedin_id": "ada", "current_company": {"name": "Acme", "company_id": "acme", "link": "https://linkedin.com/company/acme"}}]
    orgs = [{"input": {"url": "https://linkedin.com/company/acme"}, "name": "Acme", "website_simplified": "acme.example", "country_code": "IT"}]
    instagram = [
        {"input": {"url": "https://www.instagram.com/ADA.EXAMPLE/"}, "post_hashtags": "['#Robotics', '#FYP', '#AI']"},
        {"input": {"url": "https://www.instagram.com/other/"}, "post_hashtags": ["#Wrong"]},
    ]
    crunchbase = [
        {"discovery_input": {"keyword": "Acme"}, "name": "Unrelated Name", "website": "https://www.acme.example/",
         "investors": [{"investor": {"value": "Y Combinator"}}, {"value": "North Capital"}],
         "funding_rounds_list": [{"title": "Pre Seed Round - Unrelated Name"}]},
        {"discovery_input": {"keyword": "Acme"}, "name": "Acme", "website": "https://different.example",
         "investors": [{"name": "Name Match Ventures"}], "last_funding_type": "Series A"},
        {"discovery_input": {"keyword": "Acme"}, "name": "Wrong Match", "website": "https://wrong.example",
         "investors": [{"investor": {"value": "Must Be Rejected"}}], "last_funding_type": "Seed"},
    ]
    _, entities, edges, _ = prepare(luma, linkedin, orgs, instagram=instagram, crunchbase=crunchbase)
    assert {edge["id"] for edge in edges["ig_hashtag"]} == {"robotics"}
    assert {edge["id"] for edge in edges["investor"]} == {"y-combinator", "north-capital"}
    assert {edge["source_id"] for edge in edges["investor"]} == {"acme"}
    assert {edge["id"] for edge in edges["funding_stage"]} == {"pre-seed"}
    assert {entity["name"] for entity in entities["Country"]} == {"Italy"}
    assert {entity["name"] for entity in entities["Hashtag"]} == {"robotics"}


def test_crunchbase_keyword_repr_and_null_stage():
    luma = [{"api_id": "u", "linkedin_handle": "/in/ada"}]
    linkedin = [{"linkedin_id": "ada", "current_company": {"name": "Acme", "company_id": "acme"}}]
    orgs = [{"input": {"url": "https://linkedin.com/company/acme"}, "name": "Acme"}]
    crunchbase = [{"discovery_input": {"keyword": "{'name': 'Acme'}"}, "name": "Acme", "investors": [{"investor": {"value": "Investor One"}}], "last_funding_type": None,
                   "funding_rounds_list": [{"title": "Seed Round - Acme"}]}]
    _, _, edges, _ = prepare(luma, linkedin, orgs, crunchbase=crunchbase)
    assert {edge["id"] for edge in edges["investor"]} == {"investor-one"}
    assert not edges["funding_stage"]


def test_new_facts_paths_hiding_templates_and_cap():
    cases = [
        ("ig_hashtag", "POSTED_ON_IG", "Hashtag", "robotics", "robotics", "Instagram hashtags"),
        ("investor", "BACKED_BY", "Investor", "y-combinator", "Y Combinator", "Crunchbase investors"),
        ("funding_stage", "AT_STAGE", "Stage", "seed", "Seed", "Crunchbase funding"),
    ]
    for kind, rel, label, eid, name, source in cases:
        rows = [(f"{kind}-{i}", rel, label, eid, name, False, False, kind in {"investor", "funding_stage"}) for i in range(3)]
        fact = fact_catalog(rows)[f"{kind}:{eid}"]
        assert fact["eligible"] and fact["n"] == 3 and fact["src"] == source == SRC[kind]
        assert kind in LINES and kind in YOU_LINES and kind in EVENT_LINES and kind in ORDER
        assert rel in fact["pattern"] and rel in fact_path(fact)
        if kind == "investor":
            assert fact_path(fact) == ["You", "WORKED_AT", "a company", "BACKED_BY", "Y Combinator", "2 others"]
            assert fact["pattern"].count("->") == 2
        if kind == "funding_stage":
            assert fact["line"] == "people here work at Seed-stage startups"
        rows[0] = (rows[0][0], rel, label, eid, name, True, False, kind in {"investor", "funding_stage"})
        assert fact_catalog(rows)[f"{kind}:{eid}"]["n"] == 2

    class Graph:
        def __init__(self):
            self.calls = []

        def query(self, query, params):
            self.calls.append((query, params))

    graph = Graph()
    set_hidden(graph, "u", "investor:y-combinator")
    assert "WORKED_AT" in graph.calls[0][0] and "BACKED_BY" in graph.calls[0][0]
    assert "WHERE r.current=true" in graph.calls[0][0]
    assert graph.calls[0][1]["eid"] == "y-combinator"
    assert KINDS["ig_hashtag"] == ("POSTED_ON_IG", "Hashtag")
    assert ORG_PATHS["investor"][:3] == ("Company", "BACKED_BY", "Investor")

    fake = {}
    for kind in ("repo", "investor", "hashtag", "ig_hashtag", "org_kind", "funding_stage"):
        for i in range(10):
            fid = f"{kind}:{i}"
            fake[fid] = {"id": fid, "kind": kind, "n": 3, "eligible": True}
    selected = rotation(fake)
    assert {f["kind"] for f in selected[:4]} == {"repo", "investor", "hashtag", "ig_hashtag"}
    assert sum(f["kind"] == "ig_hashtag" for f in selected) == 6


def test_graph_rows_reads_investor_as_two_hop():
    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def __init__(self):
            self.queries = []

        def ro_query(self, query):
            self.queries.append(query)
            if "RETURN p.id, 'BACKED_BY'" in query:
                return Result([("u", "BACKED_BY", "Investor", "y-combinator", "Y Combinator", False, False, True)])
            return Result([])

    graph = Graph()
    rows = graph_rows(graph)
    assert len(rows) == 1
    assert "WORKED_AT" in next(query for query in graph.queries if "BACKED_BY" in query)
    assert fact_catalog(rows)["investor:y-combinator"]["all_holders"] == {"u"}


def test_server_uses_new_fact_lines_without_new_response_fields(monkeypatch):
    rows = [(f"u{i}", "BACKED_BY", "Investor", "y-combinator", "Y Combinator", False, False, True) for i in range(3)]
    catalog = fact_catalog(rows)
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid})
    detail = server.fact_detail("investor:y-combinator")
    assert set(detail) == {"id", "kind", "n", "opted_in", "line", "src", "pattern", "entities", "path"}
    assert detail["path"] == ["You", "WORKED_AT", "a company", "BACKED_BY", "Y Combinator", "2 others"]
    from fastapi import Request
    personal = server.person_facts("u0", Request({"type": "http", "headers": []}))
    assert personal == [{"fact_id": "investor:y-combinator", "kind": "investor", "line_you": "You work at a company backed by Y Combinator", "n_if_eligible": 3, "n": 3}]
    monkeypatch.setattr(server, "_events", [{"at": "2026-10-24T00:00:00+00:00", "text": catalog["investor:y-combinator"]["line_event"] + " just opted in", "fact_id": "investor:y-combinator"}])
    assert server.events()[0]["text"] == "Someone who works at a company backed by Y Combinator just opted in"


def test_country_names_and_articles_in_all_lines():
    expected = {"IT": "Italy", "GB": "United Kingdom", "AE": "United Arab Emirates", "NL": "Netherlands", "PH": "Philippines"}
    for code, name in expected.items():
        assert country(code) == (code, name)
        rows = [(f"u{i}", "LOCATED_IN", "Country", code, code, False, False) for i in range(3)]
        fact = fact_catalog(rows)[f"study_country:{code}"]
        phrase = country_phrase(name)
        assert fact["line"] == f"people here studied in {phrase}"
        assert fact["line_you"] == f"You studied in {phrase}"
        assert fact["line_event"] == f"Someone who studied in {phrase}"
        assert fact_path(fact)[4] == phrase
        assert fact["entities"][0]["name"] == name
    assert country("US") is None
    assert country_phrase("United States") == "the United States"
    assert country_phrase("United Kingdom") == "the United Kingdom"
    assert country_phrase("the United Kingdom") == "the United Kingdom"
    us_rows = [(f"u{i}", "BASED_IN", "Country", "US", "US", False, False) for i in range(3)]
    us_fact = fact_catalog(us_rows)["country:US"]
    assert us_fact["line"] == "people here are based in the United States"
    assert us_fact["line_you"] == "You are based in the United States"
    assert us_fact["line_event"] == "Someone who is based in the United States"
    for kind, rel, lead in (("country", "BASED_IN", "are based in"), ("company_country", "HQ_IN", "work for companies headquartered in")):
        rows = [(f"u{i}", rel, "Country", "GB", "United Kingdom", False, False) for i in range(3)]
        fact = fact_catalog(rows)[f"{kind}:GB"]
        assert fact["line"] == f"people here {lead} the United Kingdom"
        assert "the United Kingdom" in fact["line_you"]
        assert "the United Kingdom" in fact["line_event"]
