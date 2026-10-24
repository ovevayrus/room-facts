import math

import pytest

from build_graph import set_hidden
from facts import COMBO_PATHS, EVENT_LINES, LINES, YOU_LINES, fact_catalog, fact_path, graph_rows, interest_score, public_fact, rotation


def row(pid, rel, label, eid, name, hidden=False, current=False, extra=None):
    return (pid, rel, label, eid, name, hidden, False, current, extra)


def test_kind_specific_maximum_and_absolute_privacy_floor(monkeypatch):
    rows = [row(f"school-{i}", "STUDIED_AT", "School", "uc", "UC Berkeley") for i in range(18)]
    rows += [row(f"cert-{i}", "CERTIFIED", "Cert", "cert", "A Certificate") for i in range(18)]
    rows += [row(f"small-{i}", "WRITES", "ProgLang", "rust", "Rust") for i in range(2)]
    catalog = fact_catalog(rows, min_n=1)
    assert catalog["school:uc"]["eligible"]
    assert not catalog["cert:cert"]["eligible"]
    assert not catalog["prog_lang:rust"]["eligible"]
    assert all(f["n"] >= 3 for f in rotation(catalog))
    monkeypatch.setenv("MAX_N", "10")
    assert not fact_catalog(rows)["school:uc"]["eligible"]


def test_stats_top_groups_also_keep_three_person_floor(monkeypatch):
    import server

    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def ro_query(self, query, params=None):
            if params is not None:
                assert params["min"] == 3
                return Result([])
            if "RETURN count(p), sum" in query:
                return Result([(10, 10, 0, 0)])
            return Result([(0,)])

    monkeypatch.setenv("MIN_N", "1")
    monkeypatch.setattr(server, "graph", lambda: Graph())
    assert server.stats()["top_schools"] == []


def test_rotation_spreads_counts_keeps_broad_facts_in_catalog():
    kinds = ("school", "repo", "investor", "company", "tagged_company", "hashtag", "prog_lang", "industry", "city", "language", "gh_org", "ig_hashtag", "volunteer", "funding_stage", "cert")
    sizes = (3, 18, 7, 4, 9, 17, 5, 12, 6, 3, 24, 8, 4, 14, 10)
    catalog = {f"{kind}:{i}": {"id": f"{kind}:{i}", "kind": kind, "n": n, "eligible": True}
               for i, (kind, n) in enumerate(zip(kinds, sizes))}
    for kind in ("country", "study_country"):
        catalog[f"{kind}:gb"] = {"id": f"{kind}:gb", "kind": kind, "n": 6, "eligible": True}
    chosen = rotation(catalog)
    assert len({"S" if f["n"] <= 5 else "M" if f["n"] <= 10 else "L" for f in chosen[:12]}) == 3
    assert all(a["n"] != b["n"] and a["kind"] != b["kind"] for a, b in zip(chosen[:12], chosen[1:12]))
    assert not {"country", "study_country"} & {f["kind"] for f in chosen}
    assert all(f"{kind}:gb" in catalog for kind in ("country", "study_country"))
    assert [f["id"] for f in chosen] == [f["id"] for f in rotation(dict(reversed(list(catalog.items()))))]


def test_country_kinds_are_available_off_rotation(monkeypatch):
    import server
    from fastapi import Request

    rows = [row(f"based-{i}", "BASED_IN", "Country", "GB", "United Kingdom") for i in range(3)]
    rows += [row(f"study-{i}", "LOCATED_IN", "Country", "FR", "France") for i in range(3)]
    catalog = fact_catalog(rows)
    for fid in ("country:GB", "study_country:FR"):
        assert catalog[fid]["eligible"]
        assert catalog[fid] not in rotation(catalog)
    monkeypatch.setattr(server, "snapshot", lambda force=False: {"catalog": catalog})
    monkeypatch.setattr(server, "person_row", lambda pid: {"id": pid})
    assert server.fact_detail("country:GB")["n"] == 3
    assert server.fact_detail("study_country:FR")["n"] == 3
    assert any(f["fact_id"] == "study_country:FR" for f in server.person_facts("study-0", Request({"type": "http", "headers": []})))


def test_interest_score_uses_metadata_and_stable_tiebreak():
    assert interest_score("repo", 3, 3, "repo", stars=99) == 5
    assert interest_score("investor", 3, 3, "fund", backed_companies=4) == 7
    assert interest_score("school", 8, 8, "school") == 6
    assert interest_score("hashtag", 3, 3, "sftechweek") == 4
    assert interest_score("hashtag", 3, 3, "ai") == 1
    assert math.isclose(interest_score("company", 3, 3, "co"), 3 + math.log2(3))
    repo_rows = [row(f"p{i}", "CONTRIBUTED_TO", "Repo", "org/repo", "Org/Repo", extra=99) for i in range(3)]
    assert fact_catalog(repo_rows)["repo:org/repo"]["score"] == 5
    investor_rows = [row(f"p{i}", "BACKED_BY", "Investor", "fund", "Fund", current=True, extra=f"co-{i % 2}") for i in range(3)]
    assert fact_catalog(investor_rows)["investor:fund"]["score"] == 5

    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def ro_query(self, query):
            if "RETURN i.id, c.id" in query:
                return Result([("fund", "co-0"), ("fund", "co-1"), ("fund", "co-2")])
            if "RETURN p.id, 'BACKED_BY'" in query:
                return Result(investor_rows)
            return Result([])

    assert fact_catalog(graph_rows(Graph()))["investor:fund"]["score"] == 6


@pytest.mark.parametrize("kind,parent_rel,label,parent_kind,expected", [
    ("school_industry", "IN_INDUSTRY", "Industry", "industry", "people here studied at Example U and now work in Robotics"),
    ("school_stage", "AT_STAGE", "Stage", "funding_stage", "people here from Example U work at Seed-stage startups"),
    ("school_investor", "BACKED_BY", "Investor", "investor", "people here from Example U work at companies backed by North Fund"),
])
def test_school_combos_require_smaller_than_both_parents(kind, parent_rel, label, parent_kind, expected):
    target = {"Industry": "Robotics", "Stage": "Seed", "Investor": "North Fund"}[label]
    rows = []
    for i in range(3):
        pid = f"p{i}"
        rows += [row(pid, "STUDIED_AT", "School", "example-u", "Example U"),
                 row(pid, parent_rel, label, "target", target, current=True),
                 (pid, f"COMBO_{kind}", label, ("example-u", "target"), ("Example U", target), False, False)]
    rows += [row("school-only", "STUDIED_AT", "School", "example-u", "Example U"),
             row("target-only", parent_rel, label, "target", target, current=True)]
    catalog = fact_catalog(rows)
    combo = catalog[f"{kind}:example-u>target"]
    assert combo["eligible"] and combo["n"] == 3
    assert combo["line"] == expected
    assert combo["line_you"].startswith("You studied at Example U")
    assert combo["line_event"].startswith("Someone from Example U")
    assert kind in LINES and kind in YOU_LINES and kind in EVENT_LINES
    assert all(hop in fact_path(combo) for hop in ("STUDIED_AT", "WORKED_AT", parent_rel))
    assert "b.current=true" in combo["pattern"]
    assert set(public_fact(combo)) == {"id", "kind", "n", "opted_in", "line", "src", "pattern", "entities"}
    assert f"{parent_kind}:target" in catalog
    assert f"{kind}:example-u>target" not in fact_catalog(rows[:-2])
    hidden = list(rows)
    hidden[2] = ("p0", f"COMBO_{kind}", label, ("example-u", "target"), ("Example U", target), True, False)
    hidden_combo = fact_catalog(hidden)[f"{kind}:example-u>target"]
    assert hidden_combo["n"] == 2 and not hidden_combo["eligible"] and "p0" in hidden_combo["hidden_holders"]


def test_repo_lang_combo_requires_both_parents_to_be_larger():
    rows = []
    for i in range(3):
        rows += [row(f"p{i}", "CONTRIBUTED_TO", "Repo", "org/repo", "Org/Repo"),
                 row(f"p{i}", "WRITES", "ProgLang", "rust", "Rust")]
    rows += [row("repo-only", "CONTRIBUTED_TO", "Repo", "org/repo", "Org/Repo"),
             row("lang-only", "WRITES", "ProgLang", "rust", "Rust")]
    combo = fact_catalog(rows)["repo_lang:org/repo>rust"]
    assert combo["eligible"] and combo["n"] == 3
    assert combo["line"] == "people here contribute to Org/Repo and write Rust"
    assert combo["line_you"] == "You contribute to Org/Repo and write Rust"
    assert combo["line_event"] == "Someone who contributes to Org/Repo and writes Rust"
    assert fact_path(combo) == ["You", "CONTRIBUTED_TO", "Org/Repo", "WRITES", "Rust", "2 others"]
    assert "repo_lang:org/repo>rust" not in fact_catalog(rows[:-2])
    hidden = list(rows)
    hidden[0] = row("p0", "CONTRIBUTED_TO", "Repo", "org/repo", "Org/Repo", hidden=True)
    hidden_combo = fact_catalog(hidden)["repo_lang:org/repo>rust"]
    assert hidden_combo["n"] == 2 and not hidden_combo["eligible"] and "p0" in hidden_combo["hidden_holders"]


def test_graph_reads_current_combo_paths_without_hiding_constituent_edges():
    class Result:
        def __init__(self, rows):
            self.result_set = rows

    class Graph:
        def __init__(self):
            self.reads = []
            self.writes = []

        def ro_query(self, query):
            self.reads.append(query)
            if "<-[a:STUDIED_AT]" in query and "IN_INDUSTRY" in query:
                return Result([("p", "example-u", "Example U", "robotics", "Robotics", False, False, False)])
            return Result([])

        def query(self, query, params):
            self.writes.append((query, params))

    graph = Graph()
    rows = graph_rows(graph)
    assert ("p", "COMBO_school_industry", "Industry", ("example-u", "robotics"), ("Example U", "Robotics"), False, False) in rows
    assert len([q for q in graph.reads if "<-[a:STUDIED_AT]" in q]) == len(COMBO_PATHS)
    assert all("WHERE b.current=true" in q for q in graph.reads if "<-[a:STUDIED_AT]" in q)
    set_hidden(graph, "p", "school_industry:example-u>robotics")
    set_hidden(graph, "p", "repo_lang:org/repo>rust")
    assert graph.writes == []
