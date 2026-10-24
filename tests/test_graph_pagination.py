"""Relationship reads must survive the database's per-query result cap."""
from types import SimpleNamespace

import pytest

import facts


class CappedGraph:
    def __init__(self, family, rows, cap=10000):
        self.family = family
        self.rows = rows
        self.cap = cap

    def ro_query(self, query, params=None):
        if "MATCH (s:School)<-[a:STUDIED_AT]" in query:
            family = "combo" if "[:IN_INDUSTRY]" in query else None
        elif "RETURN i.id, c.id" in query:
            family = "backing"
        elif "'ISSUED_BY'" in query:
            family = "issuer"
        elif "RETURN p.id, 'IN_INDUSTRY'" in query:
            family = "path"
        elif "RETURN p.id, type(r)" in query:
            family = "direct"
        else:
            family = None
        rows = self.rows if family == self.family else []
        params = params or {}
        start = params.get("page_offset", 0)
        size = min(params.get("page_size", self.cap), self.cap)
        if params:
            assert "ORDER BY" in query
        return SimpleNamespace(result_set=rows[start:start + size])


def test_late_holders_and_hidden_edges_survive_ten_thousand_row_cap():
    rows = [(f"cap-{i}", "SPEAKS", "Language", "at-cap", "At Cap", False, False, False, None)
            for i in range(25)]
    rows += [(f"early-{i}", "SPEAKS", "Language", "common", "Common", False, False, False, None)
             for i in range(9975)]
    rows += [(f"late-{i}", "STUDIED_AT", "School", "rare-school", "Rare School", i == 3, False, False, None)
             for i in range(4)]
    rows.append(("late-cap", "SPEAKS", "Language", "at-cap", "At Cap", False, False, False, None))
    catalog = facts.fact_catalog(facts.graph_rows(CappedGraph("direct", rows)))
    rare = catalog["school:rare-school"]
    assert rare["n"] == 3 and rare["eligible"]
    assert rare["holders"] == {"late-0", "late-1", "late-2"}
    assert rare["hidden_holders"] == {"late-3"}
    assert not catalog["language:common"]["eligible"]
    assert catalog["language:at-cap"]["n"] == 26
    assert not catalog["language:at-cap"]["eligible"]
    assert "holders" not in facts.public_fact(rare)


@pytest.mark.parametrize("family", ["issuer", "path", "backing", "combo"])
@pytest.mark.parametrize("count", [4, 5])
def test_every_path_query_reads_all_pages(monkeypatch, family, count):
    monkeypatch.setattr(facts, "GRAPH_PAGE_SIZE", 2)
    if family == "combo":
        source = [(f"p{i}", "school", "School", "industry", "Industry", False, i == 4, False) for i in range(count)]
        expected = [(f"p{i}", "COMBO_school_industry", "Industry", ("school", "industry"), ("School", "Industry"), i == 4, False) for i in range(count)]
    elif family == "backing":
        source = [("fund", f"c{i}") for i in range(count)]
        expected = [(None, "INVESTOR_BACKING", "", "fund", "", False, False, False, f"c{i}") for i in range(count)]
    else:
        relation, label = ("ISSUED_BY", "Issuer") if family == "issuer" else ("IN_INDUSTRY", "Industry")
        source = [(f"p{i}", relation, label, "entity", "Entity", i == 4, False, False) for i in range(count)]
        expected = source
    assert facts.graph_rows(CappedGraph(family, source)) == expected
