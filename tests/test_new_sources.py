"""Small synthetic records for the four ready enrichment sources."""
from build_graph import KINDS, ORG_PATHS, prepare, set_hidden
from facts import EVENT_LINES, LINES, ORDER, SRC, YOU_LINES, fact_catalog, fact_path, rotation
from normalize import hashtags, linkedin_org_slug, x_handle
import server
from fastapi.testclient import TestClient
import json
import build_graph
import facts


def test_prepare_all_new_sources():
    luma = [{"api_id": "u", "linkedin_handle": "/in/ada", "twitter_handle": "@AdaX"}]
    linkedin = [{"linkedin_id": "ada", "education": [{"title": "School A", "url": "https://linkedin.com/school/school-a"}],
                 "current_company": {"name": "Acme", "company_id": "acme", "link": "https://linkedin.com/company/acme"}}]
    orgs = [
        {"input": {"url": "https://linkedin.com/company/acme"}, "industries": "Robotics", "country_code": "GB", "company_size": "10,001+ employees", "organization_type": "Public Company", "founded": 2010},
        {"input": {"url": "https://linkedin.com/school/school-a"}, "country_code": "IN"},
        {"error": "bad", "input": {"url": "https://linkedin.com/company/acme"}, "industries": "Wrong"},
    ]
    x_profiles = [{"input": {"url": "https://x.com/ADAX"}, "date_joined": "2007-01-01", "is_verified": True}]
    posts = [{"user_id": "ada", "date_posted": "2026-02-01", "hashtags": "['#Robotics', '#AI']",
              "tagged_companies": [{"name": "Acme", "link": "https://linkedin.com/company/acme"}]}]
    github = {"u": {"match": "trusted", "createdAt": "2010-01-01", "repositoriesContributedTo": {"nodes": [{"nameWithOwner": "Owner/Repo", "stargazerCount": 42}]},
                     "organizations": {"nodes": [{"login": "OrgX", "name": "Org X"}]},
                     "repositories": {"nodes": [{"name": "one", "primaryLanguage": {"name": "Rust"}}, {"name": "two", "primaryLanguage": {"name": "Rust"}}, {"name": "fork", "isFork": True, "primaryLanguage": {"name": "Go"}}]}}}
    people, entities, edges, matched = prepare(luma, linkedin, orgs, x_profiles, posts, github)
    assert matched == 1 and people[0]["github_matched"]
    expected = {"industry": "robotics", "company_country": "GB", "org_kind": "giant", "founded_year": "2010", "study_country": "IN",
                "x_since": "pre2009", "x_verified": "x_verified", "hashtag": "robotics", "tagged_company": "acme",
                "repo": "owner/repo", "gh_org": "orgx", "prog_lang": "rust", "gh_since": "pre2012"}
    for kind, eid in expected.items():
        assert eid in {edge["id"] for edge in edges[kind]}, kind
    assert {edge["id"] for edge in edges["hashtag"]} == {"robotics"}
    assert {edge["id"] for edge in edges["prog_lang"]} == {"rust"}
    assert entities["Repo"][0]["stars"] == 42
    assert any(edge["id"] == "public" for edge in edges["org_kind"])


def test_all_new_kinds_catalog_paths_and_hiding():
    paths = {kind: (info[1], info[2]) for kind, info in ORG_PATHS.items()}
    direct = {kind: KINDS[kind] for kind in ("x_since", "x_verified", "hashtag", "tagged_company", "repo", "gh_org", "prog_lang", "gh_since")}
    for kind, (rel, label) in {**paths, **direct}.items():
        eid = "pre2009" if kind == "x_since" else "pre2012" if kind == "gh_since" else "sample"
        rows = [(f"{kind}-{i}", rel, label, eid, "Sample", False, False, False) for i in range(3)]
        fact = fact_catalog(rows)[f"{kind}:{eid}"]
        assert fact["n"] == 3 and fact["eligible"] and fact["src"] == SRC[kind]
        assert fact["line"] and fact["line_you"] and fact["line_event"]
        assert kind in LINES and kind in YOU_LINES and kind in EVENT_LINES
        assert kind in ORDER
        assert rel in fact["pattern"]
        path = fact_path(fact)
        assert rel in path
        if kind in paths:
            assert len(path) == 6 and ("WORKED_AT" in path or "STUDIED_AT" in path)
            assert fact["pattern"].count("->") == 2
        rows[0] = (rows[0][0], rel, label, eid, "Sample", True, False, False)
        assert fact_catalog(rows)[f"{kind}:{eid}"]["n"] == 2


def test_sjsu_self_pair_cert_article_and_rotation_caps():
    rows = []
    for i in range(3):
        pid = f"u{i}"
        rows.extend([(pid, "STUDIED_AT", "School", "sjsu-school", "San José State University", False, False),
                     (pid, "WORKED_AT", "Company", "sjsu-company", "San Jose State University", False, False),
                     (pid, "CERTIFIED", "Cert", "toolbox", "The Data Scientist's Toolbox", False, False)])
    catalog = fact_catalog(rows)
    assert "school_company:sjsu-school>sjsu-company" not in catalog
    cert = catalog["cert:toolbox"]
    assert cert["line"] == "people here hold the Data Scientist's Toolbox certification"
    assert cert["line_you"] == "You hold the Data Scientist's Toolbox certification"
    assert cert["line_event"] == "Someone who holds the Data Scientist's Toolbox certification"
    assert cert["entities"][0]["name"] == "The Data Scientist's Toolbox"
    org_rows = [(f"org-{i}", "MEMBER_OF", "GitHubOrg", "foundation", "The Foundation", False, False) for i in range(3)]
    assert fact_catalog(org_rows)["gh_org:foundation"]["line"] == "people here are members of the Foundation GitHub org"
    fake = {}
    for kind, cap in (("cert", 12), ("cert_issuer", 10), ("hashtag", 15), ("repo", 20)):
        for i in range(cap + 2):
            fid = f"{kind}:{i:02}"
            fake[fid] = {"id": fid, "kind": kind, "n": 3, "eligible": True}
    selected = rotation(fake)
    for kind, cap in (("cert", 12), ("cert_issuer", 10), ("hashtag", 15), ("repo", 20)):
        assert sum(f["kind"] == kind for f in selected) == cap
    assert [f["kind"] for f in selected[:4]] == ["repo", "hashtag", "cert_issuer", "cert"]


def test_new_normalization_and_path_hide():
    assert linkedin_org_slug("https://linkedin.com/company/ACME?x=1", "company") == "acme"
    assert x_handle("https://x.com/ADAX/") == "adax"
    assert hashtags("['#AI', '#BuildInPublic', '#buildinpublic']") == ["buildinpublic"]
    class Graph:
        def __init__(self):
            self.calls = []
        def query(self, q, params):
            self.calls.append((q, params))
    graph = Graph()
    for kind in ORG_PATHS:
        set_hidden(graph, "u", f"{kind}:sample")
    assert len(graph.calls) == len(ORG_PATHS)
    assert all("SET r.hidden=$hidden" in q for q, _ in graph.calls)


def test_stats_casts_all_counts(monkeypatch):
    class Result:
        def __init__(self, rows):
            self.result_set = rows
    class Graph:
        def ro_query(self, query, params=None):
            if "RETURN count(p), sum" in query:
                return Result([(6.0, 5.0, 2.0, 4.0)])
            if "RETURN count(DISTINCT x)" in query:
                return Result([(3.0,)])
            return Result([("Acme", 3.0)])
    monkeypatch.setattr(server, "graph", lambda: Graph())
    result = server.stats()
    assert result["github_matched"] == 4
    assert all(type(value) is int for key, value in result.items() if key not in {"top_schools", "top_companies"})
    assert all(type(item["count"]) is int for key in ("top_schools", "top_companies") for item in result[key])


def test_repo_fact_id_with_slash_routes(monkeypatch):
    rows = [(f"u{i}", "CONTRIBUTED_TO", "Repo", "owner/repo", "Owner/Repo", False, False) for i in range(3)]
    catalog = fact_catalog(rows)
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    client = TestClient(server.app)
    assert client.get("/api/fact/repo:owner/repo").status_code == 200
    assert client.get("/api/fact/repo:owner/repo/people").status_code == 403


def test_rebuild_skips_each_missing_new_source(tmp_path, monkeypatch, capsys):
    luma = tmp_path / "luma.json"
    linkedin = tmp_path / "linkedin.json"
    luma.write_text(json.dumps([{"api_id": "u"}]))
    linkedin.write_text("[]")
    class Graph:
        def delete(self):
            pass
        def query(self, query, params=None):
            pass
    monkeypatch.setattr(build_graph, "graph_client", lambda name: Graph())
    monkeypatch.setattr(build_graph, "load_optins", lambda: {})
    monkeypatch.setattr(facts, "eligible_facts", lambda graph: [])
    paths = [tmp_path / f"{name}.json" for name in ("orgs", "x", "posts", "github", "instagram", "crunchbase")]
    build_graph.rebuild(luma, linkedin, "test", *paths)
    output = capsys.readouterr().out
    assert all(f"Skipping {path.name}: file missing." in output for path in paths)
