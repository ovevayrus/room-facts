"""Graph-backed fact patterns, eligibility, and rotation."""
from collections import defaultdict
import os

from build_graph import KINDS, ORG_PATHS
from normalize import COUNTRIES, country_phrase, entity_slug, slug

ORDER = ["repo", "investor", "school", "language", "industry", "city", "gh_org", "hashtag", "ig_hashtag", "study_country", "company", "org_kind", "funding_stage", "x_since", "tagged_company", "prog_lang", "cause", "volunteer", "company_country", "founded_year", "country", "cert_issuer", "cert", "gh_since", "x_verified", "school_company", "company_company"]
PATH_KINDS = {"cert_issuer", *ORG_PATHS, "school_company", "company_company"}
COUNTRY_KINDS = {"country", "company_country", "study_country"}
LINES = {
    "school": "people here studied at {a}", "company": "people here have worked at {a}",
    "city": "people here live in {a}", "country": "people here are based in {a}",
    "language": "people here speak {a}", "cert": "people here hold the {a} certification",
    "cert_issuer": "people here have certifications from {a}",
    "volunteer": "people here have volunteered at {a}", "cause": "people here volunteer for {a}",
    "school_company": "people here went from {a} to {b}",
    "company_company": "people here have worked at both {a} and {b}",
    "industry": "people here work in {a}", "company_country": "people here work for companies headquartered in {a}",
    "org_kind": "people here work at {a}", "founded_year": "people here work at companies founded in {a}",
    "study_country": "people here studied in {a}", "x_since": "people here have been on X since {a}",
    "x_verified": "people here are verified on X", "hashtag": "people here posted #{a} on LinkedIn this year",
    "tagged_company": "people here tagged {a} in a LinkedIn post this year", "repo": "people here have contributed to {a} on GitHub",
    "gh_org": "people here are members of the {a} GitHub org", "prog_lang": "people here write {a} on GitHub",
    "gh_since": "people here joined GitHub before 2012",
    "ig_hashtag": "people here posted #{a} on Instagram",
    "investor": "people here work at companies backed by {a}",
    "funding_stage": "people here work at {a}-stage startups",
}
YOU_LINES = {
    "school": "You studied at {a}", "company": "You have worked at {a}",
    "city": "You live in {a}", "country": "You are based in {a}",
    "language": "You speak {a}", "cert": "You hold the {a} certification",
    "cert_issuer": "You have certifications from {a}",
    "volunteer": "You have volunteered at {a}", "cause": "You volunteer for {a}",
    "school_company": "You went from {a} to {b}",
    "company_company": "You have worked at both {a} and {b}",
    "industry": "You work in {a}", "company_country": "You work for a company headquartered in {a}",
    "org_kind": "You work at {a}", "founded_year": "You work at a company founded in {a}",
    "study_country": "You studied in {a}", "x_since": "You have been on X since {a}",
    "x_verified": "You are verified on X", "hashtag": "You posted #{a} on LinkedIn this year",
    "tagged_company": "You tagged {a} in a LinkedIn post this year", "repo": "You have contributed to {a} on GitHub",
    "gh_org": "You are a member of the {a} GitHub org", "prog_lang": "You write {a} on GitHub",
    "gh_since": "You joined GitHub before 2012",
    "ig_hashtag": "You posted #{a} on Instagram",
    "investor": "You work at a company backed by {a}",
    "funding_stage": "You work at a {a}-stage startup",
}
EVENT_LINES = {
    "school": "Someone who studied at {a}", "company": "Someone who has worked at {a}",
    "city": "Someone who lives in {a}", "country": "Someone who is based in {a}",
    "language": "Someone who speaks {a}", "cert": "Someone who holds the {a} certification",
    "cert_issuer": "Someone who has certifications from {a}",
    "volunteer": "Someone who has volunteered at {a}", "cause": "Someone who volunteers for {a}",
    "school_company": "Someone who went from {a} to {b}",
    "company_company": "Someone who has worked at both {a} and {b}",
    "industry": "Someone who works in {a}", "company_country": "Someone who works for a company headquartered in {a}",
    "org_kind": "Someone who works at {a}", "founded_year": "Someone who works at a company founded in {a}",
    "study_country": "Someone who studied in {a}", "x_since": "Someone who has been on X since {a}",
    "x_verified": "Someone who is verified on X", "hashtag": "Someone who posted #{a} on LinkedIn this year",
    "tagged_company": "Someone who tagged {a} in a LinkedIn post this year", "repo": "Someone who has contributed to {a} on GitHub",
    "gh_org": "Someone who is a member of the {a} GitHub org", "prog_lang": "Someone who writes {a} on GitHub",
    "gh_since": "Someone who joined GitHub before 2012",
    "ig_hashtag": "Someone who posted #{a} on Instagram",
    "investor": "Someone who works at a company backed by {a}",
    "funding_stage": "Someone who works at a {a}-stage startup",
}
SRC = {"school": "LinkedIn education", "company": "LinkedIn experience", "city": "LinkedIn location", "country": "LinkedIn location", "language": "LinkedIn languages", "cert": "LinkedIn certifications", "cert_issuer": "LinkedIn certifications", "volunteer": "LinkedIn volunteer experience", "cause": "LinkedIn volunteer experience", "school_company": "LinkedIn education + experience", "company_company": "LinkedIn experience", "industry": "LinkedIn company pages", "company_country": "LinkedIn company pages", "org_kind": "LinkedIn company pages", "founded_year": "LinkedIn company pages", "study_country": "LinkedIn school pages", "x_since": "X profile", "x_verified": "X profile", "hashtag": "LinkedIn posts", "tagged_company": "LinkedIn posts", "repo": "GitHub contributions", "gh_org": "GitHub organizations", "prog_lang": "GitHub repositories", "gh_since": "GitHub profile", "ig_hashtag": "Instagram hashtags", "investor": "Crunchbase investors", "funding_stage": "Crunchbase funding"}


def graph_rows(graph):
    """One read of graph relationships, including hidden ones for personal review."""
    query = "MATCH (p:Person)-[r]->(x) RETURN p.id, type(r), labels(x)[0], x.id, x.name, r.hidden, p.opted_in, r.current"
    issuer_query = "MATCH (p:Person)-[r:CERTIFIED]->(:Cert)-[:ISSUED_BY]->(i:Issuer) RETURN p.id, 'ISSUED_BY', 'Issuer', i.id, i.name, r.hidden, p.opted_in, null"
    rows = graph.ro_query(query).result_set + graph.ro_query(issuer_query).result_set
    for kind, (source_label, rel, target_label, _) in ORG_PATHS.items():
        first = "WORKED_AT" if source_label == "Company" else "STUDIED_AT"
        current_only = " WHERE r.current=true" if kind in {"investor", "funding_stage"} else ""
        path_query = f"MATCH (p:Person)-[r:{first}]->(:{source_label})-[:{rel}]->(x:{target_label}){current_only} RETURN p.id, '{rel}', '{target_label}', x.id, x.name, r.hidden, p.opted_in, r.current"
        rows += graph.ro_query(path_query).result_set
    return rows


def fact_catalog(rows, min_n=None, max_n=None):
    min_n = int(min_n if min_n is not None else os.getenv("MIN_N", "3"))
    max_n = int(max_n if max_n is not None else os.getenv("MAX_N", "12"))
    by_kind = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        pid, rel, label, eid, name, hidden, opted = row[:7]
        current = bool(row[7]) if len(row) > 7 else False
        for kind, (expected_rel, expected_label) in KINDS.items():
            if rel == expected_rel and label == expected_label:
                by_kind[kind][eid][pid] = {"name": name, "hidden": bool(hidden), "opted": bool(opted), "label": label, "current": current}
                break
        path_kind = "cert_issuer" if rel == "ISSUED_BY" and label == "Issuer" else next((k for k, v in ORG_PATHS.items() if rel == v[1] and label == v[2]), None)
        if path_kind and (path_kind not in {"investor", "funding_stage"} or current):
            old = by_kind[path_kind][eid].get(pid)
            by_kind[path_kind][eid][pid] = {"name": name, "hidden": bool(hidden) and (old["hidden"] if old else True), "opted": bool(opted), "label": label, "current": False}

    catalog = {}

    def add(kind, ids, items, holders, all_holders, hidden_holders):
        fid = f"{kind}:{'>'.join(ids)}"
        names = [item["name"] for item in items]
        if kind in COUNTRY_KINDS:
            names[0] = COUNTRIES.get(str(names[0]).upper(), names[0])
        labels = [item["label"] for item in items]
        n = len(holders)
        eligible = min_n <= n <= max_n
        if kind == "cert_issuer":
            pattern = "MATCH (p:Person)-[r:CERTIFIED]->(c:Cert)-[:ISSUED_BY]->(i:Issuer {id:$id}) WHERE r.hidden=false"
        elif kind in ORG_PATHS:
            source_label, rel, target_label, _ = ORG_PATHS[kind]
            first = "WORKED_AT" if source_label == "Company" else "STUDIED_AT"
            current_only = " AND r.current=true" if kind in {"investor", "funding_stage"} else ""
            pattern = f"MATCH (p:Person)-[r:{first}]->(s:{source_label})-[:{rel}]->(x:{target_label} {{id:$id}}) WHERE r.hidden=false{current_only}"
        elif kind in KINDS:
            rel, label = KINDS[kind]
            pattern = f"MATCH (p:Person)-[r:{rel}]->(x:{label} {{id:$id}}) WHERE r.hidden=false"
        elif kind == "school_company":
            pattern = "MATCH (s:School {id:$school})<-[a:STUDIED_AT]-(p:Person)-[b:WORKED_AT]->(c:Company {id:$company}) WHERE a.hidden=false AND b.hidden=false"
        else:
            pattern = "MATCH (a:Company {id:$a})<-[r1:WORKED_AT]-(p:Person)-[r2:WORKED_AT]->(b:Company {id:$b}) WHERE a.id < b.id AND r1.hidden=false AND r2.hidden=false"
        is_current = kind == "company" and bool(holders) and all(v["current"] for v in holders.values())
        is_yc = kind == "school" and ids[0] == "y-combinator"
        line = ("people here work at {a}" if is_current else "people here went through {a}" if is_yc else LINES[kind])
        you_line = ("You work at {a}" if is_current else "You went through {a}" if is_yc else YOU_LINES[kind])
        event_line = ("Someone who works at {a}" if is_current else "Someone who went through {a}" if is_yc else EVENT_LINES[kind])
        if kind == "x_since" and ids[0] == "pre2009":
            line, you_line, event_line = "people here joined Twitter before 2009", "You joined Twitter before 2009", "Someone who joined Twitter before 2009"
        if kind == "founded_year" and ids[0] == "2026":
            line, you_line, event_line = "people here work at companies founded this year", "You work at a company founded this year", "Someone who works at a company founded this year"
        if kind == "org_kind" and ids[0] == "government":
            line, you_line, event_line = "people here work for {a}", "You work for {a}", "Someone who works for {a}"
        article_name = names[0]
        if article_name.lower().startswith("the ") and any("the {a}" in template.lower() for template in (line, you_line, event_line)):
            article_name = article_name[4:]
        if kind in COUNTRY_KINDS:
            article_name = country_phrase(article_name)
        catalog[fid] = {
            "id": fid, "kind": kind, "n": n, "opted_in": sum(1 for p in holders if holders[p]["opted"]),
            "line": line.format(a=article_name, b=names[-1]), "src": SRC[kind],
            "pattern": pattern, "entities": [{"label": label, "name": name} for label, name in zip(labels, names)],
            "holders": set(holders), "all_holders": set(all_holders), "hidden_holders": set(hidden_holders),
            "line_you": you_line.format(a=article_name, b=names[-1]),
            "line_event": event_line.format(a=article_name, b=names[-1]), "eligible": eligible,
        }

    for kind in [*KINDS, "cert_issuer", *ORG_PATHS]:
        for eid, holders in by_kind[kind].items():
            sample = next(iter(holders.values()))
            visible = {p: value for p, value in holders.items() if not value["hidden"]}
            add(kind, [eid], [sample], visible, holders, set(holders) - set(visible))
    for sid, school_holders in by_kind["school"].items():
        for cid, company_holders in by_kind["company"].items():
            school_name = next(iter(school_holders.values()))["name"]
            company_name = next(iter(company_holders.values()))["name"]
            if sid == cid or slug(school_name) == slug(company_name) or entity_slug(school_name, "school") == entity_slug(company_name, "school"):
                continue
            shared = set(school_holders) & set(company_holders)
            if not shared:
                continue
            visible = {p: school_holders[p] for p in shared if not school_holders[p]["hidden"] and not company_holders[p]["hidden"]}
            hidden = shared - set(visible)
            add("school_company", [sid, cid], [next(iter(school_holders.values())), next(iter(company_holders.values()))], visible, shared, hidden)
    companies = sorted(by_kind["company"])
    for i, aid in enumerate(companies):
        for bid in companies[i + 1:]:
            a, b = by_kind["company"][aid], by_kind["company"][bid]
            shared = set(a) & set(b)
            if not shared:
                continue
            visible = {p: a[p] for p in shared if not a[p]["hidden"] and not b[p]["hidden"]}
            add("company_company", [aid, bid], [next(iter(a.values())), next(iter(b.values()))], visible, shared, shared - set(visible))

    candidates = [f for f in catalog.values() if f["eligible"]]
    # A path wins over a single fact for an identical holder set.
    candidates.sort(key=lambda f: (-int(f["kind"] in PATH_KINDS), ORDER.index(f["kind"]), f["id"]))
    seen = set()
    for fact in candidates:
        signature = frozenset(fact["holders"])
        if signature in seen:
            fact["eligible"] = False
        else:
            seen.add(signature)
    return catalog


def rotation(catalog):
    groups = {}
    for kind in ORDER:
        values = sorted((f for f in catalog.values() if f["eligible"] and f["kind"] == kind), key=lambda f: (f["n"], f["id"]))
        groups[kind] = values[:{"cert": 12, "cert_issuer": 10, "hashtag": 15, "ig_hashtag": 8}.get(kind, 20)]
    result = []
    while any(groups.values()):
        for kind in ORDER:
            if groups[kind]:
                result.append(groups[kind].pop(0))
    return result


def public_fact(fact):
    return {key: fact[key] for key in ("id", "kind", "n", "opted_in", "line", "src", "pattern", "entities")}


def eligible_facts(graph):
    return [public_fact(f) for f in rotation(fact_catalog(graph_rows(graph)))]


def fact_path(fact):
    entities = fact["entities"]
    if fact["kind"] == "cert_issuer":
        return ["You", "CERTIFIED", "a certification", "ISSUED_BY", entities[0]["name"], f"{max(fact['n'] - 1, 0)} others"]
    if fact["kind"] in ORG_PATHS:
        source_label, rel, _, _ = ORG_PATHS[fact["kind"]]
        first = "WORKED_AT" if source_label == "Company" else "STUDIED_AT"
        name = country_phrase(entities[0]["name"]) if fact["kind"] in COUNTRY_KINDS else entities[0]["name"]
        return ["You", first, f"a {source_label.lower()}", rel, name, f"{max(fact['n'] - 1, 0)} others"]
    if len(entities) == 2:
        rels = ["STUDIED_AT", "WORKED_AT"] if fact["kind"] == "school_company" else ["WORKED_AT", "WORKED_AT"]
        return ["You", rels[0], entities[0]["name"], rels[1], entities[1]["name"], f"{max(fact['n'] - 1, 0)} others"]
    rel = KINDS[fact["kind"]][0]
    name = country_phrase(entities[0]["name"]) if fact["kind"] in COUNTRY_KINDS else entities[0]["name"]
    return ["You", rel, name, rel, f"{max(fact['n'] - 1, 0)} others"]
