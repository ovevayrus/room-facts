from types import SimpleNamespace

import assist


class FakeGraph:
    def __init__(self, people):
        self.people = people

    def ro_query(self, query, params=None):
        ids = set((params or {}).get("ids", []))
        return SimpleNamespace(result_set=[row for row in self.people if row[0] in ids])


def fact(fid, kind, holders, line_you, *names):
    return {"id": fid, "kind": kind, "holders": set(holders), "n": len(holders), "line_you": line_you,
            "entities": [{"label": "", "name": name} for name in names]}


def test_connections_cover_every_catalog_kind_without_naming_the_other_company():
    catalog = {
        "cert_issuer:aws": fact("cert_issuer:aws", "cert_issuer", {"me", "ada"}, "You have certifications from AWS", "AWS"),
        "industry:fintech": fact("industry:fintech", "industry", {"me", "bela", "ciro"}, "You work in Fintech", "Fintech"),
        "funding_stage:seed": fact("funding_stage:seed", "funding_stage", {"me", "bela"}, "You work at a Seed-stage startup", "Seed"),
        "school:nyu": fact("school:nyu", "school", {"ciro", "dee"}, "You studied at NYU", "NYU"),
    }
    graph = FakeGraph([("ada", "Ada One", "", "ada-one"), ("bela", "Bela Two", "", "bela-two")])  # ciro hasn't opted in
    people = assist.connections(graph, "me", catalog)
    assert [p["name"] for p in people] == ["Bela Two", "Ada One"]
    bela, ada = people
    assert [s["line"] for s in bela["shared"]] == ["You both work at a Seed-stage startup", "You both work in Fintech"]
    assert bela["shared"][0]["path"] == ["You", "WORKED_AT", "a company", "AT_STAGE", "Seed", "Bela"]
    assert ada["shared"][0] == {"line": "You both have certifications from AWS", "path": ["You", "CERTIFIED", "a certification", "ISSUED_BY", "AWS", "Ada"]}
    assert assist.connections(graph, "dee", catalog) == []


def test_both_line_grammar():
    assert assist.both_line("You have worked at Stripe") == "You've both worked at Stripe"
    assert assist.both_line("You have certifications from LinkedIn") == "You both have certifications from LinkedIn"
    assert assist.both_line("You are based in Singapore") == "You're both based in Singapore"
    assert assist.both_line("You live in Oakland") == "You both live in Oakland"
