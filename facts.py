"""Graph-backed fact patterns, eligibility, and rotation."""
from collections import defaultdict
import argparse
import math
import os

from build_graph import KINDS, ORG_PATHS
from normalize import COUNTRIES, GENERIC_HASHTAGS, country_phrase, entity_slug, slug

COMBO_PATHS = {
    "school_industry": ("IN_INDUSTRY", "Industry"),
    "school_stage": ("AT_STAGE", "Stage"),
    "school_investor": ("BACKED_BY", "Investor"),
}
COMBO_KINDS = {*COMBO_PATHS, "repo_lang"}
SEPARATE_HIDDEN_COMBOS = {*COMBO_KINDS, "school_company", "company_company"}
ORDER = ["school_industry", "school_stage", "school_investor", "repo_lang", "repo", "investor", "school", "language", "industry", "city", "gh_org", "hashtag", "ig_hashtag", "company", "tagged_company", "prog_lang", "school_company", "company_company", "volunteer", "funding_stage", "org_kind", "x_since", "gh_since", "founded_year", "cert", "cert_issuer", "cause", "company_country", "x_verified", "study_country", "country"]
PATH_KINDS = {"cert_issuer", *ORG_PATHS, "school_company", "company_company", *COMBO_KINDS}
COUNTRY_KINDS = {"country", "company_country", "study_country"}
WIDE_KINDS = {"school", "company", "repo", "investor", "tagged_company", "hashtag", "prog_lang", "industry", "city", "language", *COMBO_KINDS}
TIER_1 = {"school", "repo", "investor", "company", "tagged_company", "hashtag", "prog_lang", "industry", "city", "language", "ig_hashtag", "gh_org", "school_company", "company_company", *COMBO_KINDS}
TIER_2 = {"volunteer", "funding_stage", "org_kind", "x_since", "gh_since", "founded_year"}
ROTATION_CAPS = {"ig_hashtag": 6, **{kind: 2 for kind in TIER_2}, "cert": 3, "cert_issuer": 3, "cause": 1, "company_country": 1, "study_country": 0, "country": 0, "x_verified": 1}
EVENT_TAG_PARTS = ("week", "conf", "hack", "summit", "meetup", "opensource")
GENERIC_TAGS = GENERIC_HASHTAGS | {"ml", "business"}
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
    "school_industry": "people here studied at {a} and now work in {b}",
    "school_stage": "people here from {a} work at {b}-stage startups",
    "school_investor": "people here from {a} work at companies backed by {b}",
    "repo_lang": "people here contribute to {a} and write {b}",
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
    "school_industry": "You studied at {a} and now work in {b}",
    "school_stage": "You studied at {a} and work at a {b}-stage startup",
    "school_investor": "You studied at {a} and work at a company backed by {b}",
    "repo_lang": "You contribute to {a} and write {b}",
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
    "school_industry": "Someone from {a} who now works in {b}",
    "school_stage": "Someone from {a} who works at a {b}-stage startup",
    "school_investor": "Someone from {a} who works at a company backed by {b}",
    "repo_lang": "Someone who contributes to {a} and writes {b}",
}
SRC = {"school": "LinkedIn education", "company": "LinkedIn experience", "city": "LinkedIn location", "country": "LinkedIn location", "language": "LinkedIn languages", "cert": "LinkedIn certifications", "cert_issuer": "LinkedIn certifications", "volunteer": "LinkedIn volunteer experience", "cause": "LinkedIn volunteer experience", "school_company": "LinkedIn education + experience", "company_company": "LinkedIn experience", "industry": "LinkedIn company pages", "company_country": "LinkedIn company pages", "org_kind": "LinkedIn company pages", "founded_year": "LinkedIn company pages", "study_country": "LinkedIn school pages", "x_since": "X profile", "x_verified": "X profile", "hashtag": "LinkedIn posts", "tagged_company": "LinkedIn posts", "repo": "GitHub contributions", "gh_org": "GitHub organizations", "prog_lang": "GitHub repositories", "gh_since": "GitHub profile", "ig_hashtag": "Instagram hashtags", "investor": "Crunchbase investors", "funding_stage": "Crunchbase funding"}
SRC.update({"school_industry": "LinkedIn education + current company industry", "school_stage": "LinkedIn education + Crunchbase funding", "school_investor": "LinkedIn education + Crunchbase investors", "repo_lang": "GitHub contributions + repositories"})


def interest_score(kind, n, total_holders, entity_id, stars=0, backed_companies=0):
    """Stable ranking within a count bucket; private metadata never enters public_fact."""
    score = 3 if kind in TIER_1 else 2 if kind in TIER_2 else 1
    if kind == "repo":
        try:
            stars = max(0, int(stars or 0))
        except (TypeError, ValueError, OverflowError):
            stars = 0
        score += math.log10(stars + 1)
    elif kind == "investor":
        score += backed_companies
    elif kind in {"school", "company", "tagged_company"}:
        score += math.log2(max(1, total_holders))
    elif kind in {"hashtag", "ig_hashtag"}:
        tag = str(entity_id).lower().replace("-", "")
        score += int(any(part in tag for part in EVENT_TAG_PARTS))
        score -= 2 * int(tag in GENERIC_TAGS)
    return score


def _graph_read_all(graph, query):
    """Collect one result row so the result cap cannot truncate a holder set.

    Each relationship family stays a single atomic read, including during a
    rebuild. Queries are fixed below; only their RETURN projection is wrapped.
    """
    match, projection = query.rsplit(" RETURN ", 1)
    result = graph.ro_query(f"{match} RETURN collect([{projection}])").result_set
    return result[0][0] if result else []


def graph_rows(graph):
    """Read all graph relationships, including hidden ones for personal review."""
    query = "MATCH (p:Person)-[r]->(x) RETURN p.id, type(r), labels(x)[0], x.id, x.name, r.hidden, p.opted_in, r.current, x.stars"
    issuer_query = "MATCH (p:Person)-[r:CERTIFIED]->(:Cert)-[:ISSUED_BY]->(i:Issuer) RETURN p.id, 'ISSUED_BY', 'Issuer', i.id, i.name, r.hidden, p.opted_in, null"
    rows = _graph_read_all(graph, query)
    rows += _graph_read_all(graph, issuer_query)
    for kind, (source_label, rel, target_label, _) in ORG_PATHS.items():
        first = "WORKED_AT" if source_label == "Company" else "STUDIED_AT"
        current_only = " WHERE r.current=true" if kind in {"investor", "funding_stage"} else ""
        path_query = f"MATCH (p:Person)-[r:{first}]->(s:{source_label})-[:{rel}]->(x:{target_label}){current_only} RETURN p.id, '{rel}', '{target_label}', x.id, x.name, r.hidden, p.opted_in, r.current, s.id"
        rows += _graph_read_all(graph, path_query)
    for investor_id, company_id in _graph_read_all(graph, "MATCH (c:Company)-[:BACKED_BY]->(i:Investor) RETURN i.id, c.id"):
        rows.append((None, "INVESTOR_BACKING", "", investor_id, "", False, False, False, company_id))
    for kind, (rel, label) in COMBO_PATHS.items():
        combo_query = (f"MATCH (s:School)<-[a:STUDIED_AT]-(p:Person)-[b:WORKED_AT]->(:Company)-[:{rel}]->(x:{label}) "
                       f"WHERE b.current=true RETURN p.id, s.id, s.name, x.id, x.name, a.hidden, b.hidden, p.opted_in")
        for pid, sid, school, tid, target, school_hidden, company_hidden, opted in _graph_read_all(graph, combo_query):
            rows.append((pid, f"COMBO_{kind}", label, (sid, tid), (school, target), bool(school_hidden or company_hidden), opted))
    return rows


def hidden_combos_from_optins(optins):
    """Per-fact suppressions that leave shared graph edges alone: hidden combos plus facts pending owner review."""
    return {pid: {fid for fid in state.get("hidden", []) if str(fid).partition(":")[0] in SEPARATE_HIDDEN_COMBOS} | set(state.get("pending", []))
            for pid, state in optins.items() if isinstance(state, dict)}


def fact_catalog(rows, min_n=None, max_n=None, hidden_combos=None):
    min_n = max(3, int(min_n if min_n is not None else os.getenv("MIN_N", "3")))
    max_n = int(max_n if max_n is not None else os.getenv("MAX_N", "25"))
    hidden_combos = hidden_combos or {}
    by_kind = defaultdict(lambda: defaultdict(dict))
    investor_companies = defaultdict(set)
    for row in rows:
        pid, rel, label, eid, name, hidden, opted = row[:7]
        if rel == "INVESTOR_BACKING":
            investor_companies[eid].add(row[8])
            continue
        if rel.startswith("COMBO_"):
            kind = rel[6:]
            if kind in COMBO_PATHS:
                old = by_kind[kind][eid].get(pid)
                by_kind[kind][eid][pid] = {"name": name, "hidden": bool(hidden) and (old["hidden"] if old else True), "opted": bool(opted), "label": ("School", label)}
            continue
        current = bool(row[7]) if len(row) > 7 else False
        for kind, (expected_rel, expected_label) in KINDS.items():
            if rel == expected_rel and label == expected_label:
                by_kind[kind][eid][pid] = {"name": name, "hidden": bool(hidden), "opted": bool(opted), "label": label, "current": current, "stars": row[8] if len(row) > 8 else 0}
                break
        path_kind = "cert_issuer" if rel == "ISSUED_BY" and label == "Issuer" else next((k for k, v in ORG_PATHS.items() if rel == v[1] and label == v[2]), None)
        if path_kind and (path_kind not in {"investor", "funding_stage"} or current):
            old = by_kind[path_kind][eid].get(pid)
            by_kind[path_kind][eid][pid] = {"name": name, "hidden": bool(hidden) and (old["hidden"] if old else True), "opted": bool(opted), "label": label, "current": False}
            if path_kind == "investor" and len(row) > 8 and row[8] is not None:
                investor_companies[eid].add(row[8])

    catalog = {}

    def add(kind, ids, items, holders, all_holders, hidden_holders):
        fid = f"{kind}:{'>'.join(ids)}"
        names = [item["name"] for item in items]
        if kind in COUNTRY_KINDS:
            names[0] = COUNTRIES.get(str(names[0]).upper(), names[0])
        labels = [item["label"] for item in items]
        n = len(holders)
        eligible = min_n <= n <= min(max_n, 25 if kind in WIDE_KINDS else 12)
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
        elif kind in COMBO_PATHS:
            rel, label = COMBO_PATHS[kind]
            pattern = (f"MATCH (s:School {{id:$school}})<-[a:STUDIED_AT]-(p:Person)-[b:WORKED_AT]->(:Company)-[:{rel}]->(x:{label} {{id:$target}}) "
                       "WHERE a.hidden=false AND b.hidden=false AND b.current=true")
        elif kind == "repo_lang":
            pattern = "MATCH (r:Repo {id:$repo})<-[a:CONTRIBUTED_TO]-(p:Person)-[b:WRITES]->(l:ProgLang {id:$lang}) WHERE a.hidden=false AND b.hidden=false"
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
            "score": interest_score(kind, n, n, ids[0], items[0].get("stars", 0), len(investor_companies[ids[0]]) if kind == "investor" else 0),
        }

    for kind in [*KINDS, "cert_issuer", *ORG_PATHS]:
        for eid, holders in by_kind[kind].items():
            sample = next(iter(holders.values()))
            fid = f"{kind}:{eid}"
            visible = {p: value for p, value in holders.items() if not value["hidden"] and fid not in hidden_combos.get(p, ())}
            add(kind, [eid], [sample], visible, holders, set(holders) - set(visible))
    for kind in COMBO_PATHS:
        # Keep hidden, sub-threshold combos for personal review; add() enforces the public floor.
        parent_kind = {"school_industry": "industry", "school_stage": "funding_stage", "school_investor": "investor"}[kind]
        for (sid, tid), holders in by_kind[kind].items():
            fid = f"{kind}:{sid}>{tid}"
            visible = {p: value for p, value in holders.items() if not value["hidden"] and fid not in hidden_combos.get(p, ())}
            school_visible = {p for p, value in by_kind["school"][sid].items() if not value["hidden"]}
            target_visible = {p for p, value in by_kind[parent_kind][tid].items() if not value["hidden"]}
            if len(visible) >= min(len(school_visible), len(target_visible)):
                continue
            sample = next(iter(holders.values()))
            items = [{"name": sample["name"][0], "label": "School"}, {"name": sample["name"][1], "label": COMBO_PATHS[kind][1]}]
            add(kind, [sid, tid], items, visible, holders, set(holders) - set(visible))
    for rid, repo_holders in by_kind["repo"].items():
        for lid, lang_holders in by_kind["prog_lang"].items():
            shared = set(repo_holders) & set(lang_holders)
            fid = f"repo_lang:{rid}>{lid}"
            visible = {p: repo_holders[p] for p in shared if not repo_holders[p]["hidden"] and not lang_holders[p]["hidden"] and fid not in hidden_combos.get(p, ())}
            repo_visible = sum(not value["hidden"] for value in repo_holders.values())
            lang_visible = sum(not value["hidden"] for value in lang_holders.values())
            if not shared or len(visible) >= min(repo_visible, lang_visible):
                continue
            add("repo_lang", [rid, lid], [next(iter(repo_holders.values())), next(iter(lang_holders.values()))], visible, shared, shared - set(visible))
    for sid, school_holders in by_kind["school"].items():
        for cid, company_holders in by_kind["company"].items():
            shared = school_holders.keys() & company_holders.keys()
            if not shared:
                continue
            school_name = next(iter(school_holders.values()))["name"]
            company_name = next(iter(company_holders.values()))["name"]
            if sid == cid or slug(school_name) == slug(company_name) or entity_slug(school_name, "school") == entity_slug(company_name, "school"):
                continue
            fid = f"school_company:{sid}>{cid}"
            visible = {p: school_holders[p] for p in shared if not school_holders[p]["hidden"] and not company_holders[p]["hidden"] and fid not in hidden_combos.get(p, ())}
            hidden = shared - set(visible)
            add("school_company", [sid, cid], [next(iter(school_holders.values())), next(iter(company_holders.values()))], visible, shared, hidden)
    companies = sorted(by_kind["company"])
    for i, aid in enumerate(companies):
        for bid in companies[i + 1:]:
            a, b = by_kind["company"][aid], by_kind["company"][bid]
            shared = a.keys() & b.keys()
            if not shared:
                continue
            fid = f"company_company:{aid}>{bid}"
            visible = {p: a[p] for p in shared if not a[p]["hidden"] and not b[p]["hidden"] and fid not in hidden_combos.get(p, ())}
            add("company_company", [aid, bid], [next(iter(a.values())), next(iter(b.values()))], visible, shared, shared - set(visible))

    candidates = [f for f in catalog.values() if f["eligible"]]
    # Prefer specific tiers; only use path depth to break ties within a tier.
    candidates.sort(key=lambda f: (ROTATION_CAPS.get(f["kind"], 20) == 0,
                                   -(3 if f["kind"] in TIER_1 else 2 if f["kind"] in TIER_2 else 1),
                                   -int(f["kind"] in PATH_KINDS), ORDER.index(f["kind"]), f["id"]))
    seen = set()
    for fact in candidates:
        signature = frozenset(fact["holders"])
        if signature in seen:
            fact["eligible"] = False
        else:
            seen.add(signature)
    return catalog


def rotation(catalog):
    def score(fact):
        return fact.get("score", interest_score(fact["kind"], fact["n"], fact["n"], fact["id"].partition(":")[2]))

    groups = {}
    for kind in ORDER:
        values = sorted((f for f in catalog.values() if f["eligible"] and 3 <= f["n"] <= 25 and f["kind"] == kind), key=lambda f: (-score(f), f["id"]))
        groups[kind] = values[:ROTATION_CAPS.get(kind, 20)]
    buckets = {"S": [], "M": [], "L": []}
    for values in groups.values():
        for fact in values:
            bucket = "S" if fact["n"] <= 5 else "M" if fact["n"] <= 10 else "L"
            buckets[bucket].append(fact)
    for values in buckets.values():
        values.sort(key=lambda f: (-score(f), f["id"]))
    result = []
    cycle = ("S", "L", "M", "S", "M", "L")
    while any(buckets.values()):
        wanted = cycle[len(result) % len(cycle)]
        bucket_order = ("S", "L", "M")
        index = bucket_order.index(wanted)
        order = bucket_order[index:] + bucket_order[:index]
        recent = {f["kind"] for f in result[-3:]}
        previous = result[-1] if result else None
        chosen = None
        # Exhaust the stated constraints before relaxing them when no such fact remains.
        for guard in (lambda f: f["kind"] not in recent and (not previous or f["n"] != previous["n"]),
                      lambda f: f["kind"] not in recent,
                      lambda f: not previous or f["n"] != previous["n"],
                      lambda f: not previous or f["kind"] != previous["kind"],
                      lambda f: True):
            for bucket in order:
                chosen = next((f for f in buckets[bucket] if guard(f)), None)
                if chosen:
                    buckets[bucket].remove(chosen)
                    break
            if chosen:
                break
        result.append(chosen)
    return result


def public_fact(fact):
    return {key: fact[key] for key in ("id", "kind", "n", "opted_in", "line", "src", "pattern", "entities")}


def eligible_facts(graph):
    from build_graph import load_optins

    return [public_fact(f) for f in rotation(fact_catalog(graph_rows(graph), hidden_combos=hidden_combos_from_optins(load_optins())))]


def fact_path(fact):
    entities = fact["entities"]
    if fact["kind"] in COMBO_PATHS:
        rel, _ = COMBO_PATHS[fact["kind"]]
        return ["You", "STUDIED_AT", entities[0]["name"], "WORKED_AT", "a current company", rel, entities[1]["name"], f"{max(fact['n'] - 1, 0)} others"]
    if fact["kind"] == "repo_lang":
        return ["You", "CONTRIBUTED_TO", entities[0]["name"], "WRITES", entities[1]["name"], f"{max(fact['n'] - 1, 0)} others"]
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


if __name__ == "__main__":
    from build_graph import graph_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", nargs="?", const=12, type=int, metavar="N")
    args = parser.parse_args()
    if args.preview is None:
        parser.error("use --preview [N]")
    for fact in eligible_facts(graph_client())[:max(0, args.preview)]:
        print(f"{fact['n']} | {fact['line']} | {fact['kind']}")
