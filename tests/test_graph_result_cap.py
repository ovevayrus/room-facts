"""Holder reads must survive the database's outer result-row cap."""
from types import SimpleNamespace

import pytest

import facts


class CappedGraph:
    def __init__(self, family, rows, cap=10000):
        self.family, self.rows, self.cap = family, rows, cap
        self.calls = []

    def ro_query(self, query):
        self.calls.append(query)
        if "MATCH (s:School)<-[a:STUDIED_AT]" in query:
            family = "combo" if "[:IN_INDUSTRY]" in query else None
        elif "i.id, c.id" in query:
            family = "backing"
        elif "'ISSUED_BY'" in query:
            family = "issuer"
        elif "'IN_INDUSTRY'" in query:
            family = "path"
        elif "type(r), labels(x)[0]" in query:
            family = "direct"
        else:
            family = None
        rows = self.rows if family == self.family else []
        result = [[rows]] if "RETURN collect([" in query else rows
        return SimpleNamespace(result_set=result[:self.cap])


def test_late_holders_hidden_edges_and_over_cap_counts_are_complete():
    rows = [(f"cap-{i}", "SPEAKS", "Language", "at-cap", "At Cap", False, False, False, None)
            for i in range(25)]
    rows += [(f"early-{i}", "SPEAKS", "Language", "common", "Common", False, False, False, None)
             for i in range(9975)]
    rows += [(f"late-{i}", "STUDIED_AT", "School", "rare-school", "Rare School", i == 3, False, False, None)
             for i in range(4)]
    rows.append(("late-cap", "SPEAKS", "Language", "at-cap", "At Cap", False, False, False, None))
    graph = CappedGraph("direct", rows)
    catalog = facts.fact_catalog(facts.graph_rows(graph))
    rare = catalog["school:rare-school"]
    assert rare["n"] == 3 and rare["eligible"]
    assert rare["holders"] == {"late-0", "late-1", "late-2"}
    assert rare["hidden_holders"] == {"late-3"}
    assert catalog["language:at-cap"]["n"] == 26
    assert not catalog["language:at-cap"]["eligible"]
    assert "holders" not in facts.public_fact(rare)
    assert sum("type(r), labels(x)[0]" in q for q in graph.calls) == 1


@pytest.mark.parametrize("family", ["issuer", "path", "backing", "combo"])
@pytest.mark.parametrize("count", [0, 5])
def test_every_path_query_unpacks_its_atomic_collection(family, count):
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
    graph = CappedGraph(family, source, cap=1)
    assert facts.graph_rows(graph) == expected
    assert all("RETURN collect([" in q for q in graph.calls)
