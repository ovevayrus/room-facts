"""Rebuild Room Facts in FalkorDB from Luma and LinkedIn JSON."""
import argparse
import ast
from collections import Counter, defaultdict
import json
import os
from pathlib import Path

from falkordb import FalkorDB

from normalize import GENERIC_IG_HASHTAGS, city_id, city_name, country, display_name, entity_slug, funding_stage, hashtags, instagram_handle, language_name, linkedin_org_slug, linkedin_slug, root_domain, slug, x_handle

ROOT = Path(__file__).resolve().parent
OPTINS = ROOT / "data" / "optins.json"
KINDS = {
    "school": ("STUDIED_AT", "School"), "company": ("WORKED_AT", "Company"),
    "city": ("LIVES_IN", "City"), "country": ("BASED_IN", "Country"),
    "language": ("SPEAKS", "Language"), "cert": ("CERTIFIED", "Cert"),
    "volunteer": ("VOLUNTEERED_AT", "Org"), "cause": ("VOLUNTEERS_FOR", "Cause"),
    "x_since": ("ON_X_SINCE", "Year"), "x_verified": ("HAS_BADGE", "Badge"),
    "hashtag": ("POSTED_ABOUT", "Hashtag"), "tagged_company": ("TAGGED", "Company"),
    "repo": ("CONTRIBUTED_TO", "Repo"), "gh_org": ("MEMBER_OF", "GitHubOrg"),
    "prog_lang": ("WRITES", "ProgLang"), "gh_since": ("ON_GITHUB_SINCE", "Year"),
    "ig_hashtag": ("POSTED_ON_IG", "Hashtag"),
}
ORG_PATHS = {
    "industry": ("Company", "IN_INDUSTRY", "Industry", "company"),
    "company_country": ("Company", "HQ_IN", "Country", "company"),
    "org_kind": ("Company", "IS_A", "OrgKind", "company"),
    "founded_year": ("Company", "FOUNDED_IN", "Year", "company"),
    "study_country": ("School", "LOCATED_IN", "Country", "school"),
    "investor": ("Company", "BACKED_BY", "Investor", "company"),
    "funding_stage": ("Company", "AT_STAGE", "Stage", "company"),
}


def graph_client(name=None):
    db = FalkorDB(host=os.getenv("FALKOR_HOST", "localhost"), port=int(os.getenv("FALKOR_PORT", "6379")))
    return db.select_graph(name or os.getenv("GRAPH", "roomfacts"))


def load_optins(path=OPTINS):
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def person_name(row):
    first, last = row.get("first_name"), row.get("last_name")
    return f"{first.strip()} {last.strip()}" if isinstance(first, str) and first.strip() and isinstance(last, str) and last.strip() else str(row.get("name") or "").strip()


def linkedin_match_key(row):
    inp = row.get("input") or {}
    return linkedin_slug(row.get("linkedin_id")) or linkedin_slug(inp.get("url") if isinstance(inp, dict) else None) or linkedin_slug(row.get("input_url"))


def prepare(luma, linkedin, orgs=None, x_profiles=None, posts=None, github=None, instagram=None, crunchbase=None):
    profiles = {}
    for row in linkedin:
        if isinstance(row, dict) and "error" not in row:
            key = linkedin_match_key(row)
            if key:
                profiles[key] = row
    company_ids = defaultdict(Counter)
    preferred_company_ids = defaultdict(Counter)
    for profile in profiles.values():
        current = profile.get("current_company")
        if isinstance(current, dict) and current.get("name"):
            name = current["name"]
            eid = entity_slug(name, "company", current.get("link"), current.get("company_id"))
            if eid:
                company_ids[slug(name)][eid] += 1
                if current.get("company_id"):
                    preferred_company_ids[slug(name)][eid] += 1
        for exp in profile.get("experience") or []:
            if isinstance(exp, dict):
                name = exp.get("company") or exp.get("company_name")
                if isinstance(name, dict):
                    name = name.get("name")
                eid = entity_slug(name, "company", exp.get("url"), exp.get("company_id"))
                if eid:
                    company_ids[slug(name)][eid] += 1
    company_canonical = {
        name: sorted(preferred_company_ids[name] or counts, key=lambda eid: (-(preferred_company_ids[name] or counts)[eid], eid))[0]
        for name, counts in company_ids.items()
    }
    cert_issuers = defaultdict(set)
    for profile in profiles.values():
        for item in profile.get("certifications") or []:
            if isinstance(item, dict) and item.get("title"):
                title_id = slug(item["title"])
                if title_id:
                    cert_issuers[title_id].add(slug(item.get("subtitle")))
    split_certs = {title for title, issuers in cert_issuers.items() if len(issuers) > 1}

    def cert_id(title, issuer):
        base = slug(title)
        if not base:
            return None
        return f"{base}--{slug(issuer) or 'unknown-issuer'}" if base in split_certs else base

    people, edges, names = [], defaultdict(list), defaultdict(Counter)
    org_slugs = {"company": {}, "school": {}}
    linkedin_people, x_people, instagram_people = defaultdict(list), defaultdict(list), defaultdict(list)
    matched = 0

    def add(kind, pid, name, *, link=None, company_id=None, **props):
        if not name:
            return None
        if kind == "tagged_company":
            eid = org_slugs["company"].get(linkedin_org_slug(link, "company")) or company_canonical.get(slug(name)) or entity_slug(name, "company", link)
        elif kind == "company":
            eid = company_canonical.get(slug(name)) or entity_slug(name, kind, link, company_id)
        elif kind == "school":
            eid = entity_slug(name, kind, link, company_id)
        elif kind == "city":
            eid = city_id(props.get("raw_city") or name, props.get("country"))
        elif kind == "cert":
            eid = cert_id(name, props.get("issuer"))
        elif kind == "country":
            eid = props.get("code")
        elif kind == "repo":
            eid = str(name).strip().lower()
        else:
            eid = props.get("target_id") or slug(name)
        if not eid:
            return
        label = KINDS[kind][1]
        nice = display_name(name, kind, eid)
        names[(label, eid)][nice] += 1
        record = {"pid": pid, "id": eid, "hidden": False}
        record.update({k: v if isinstance(v, (str, int, float, bool)) else json.dumps(v, ensure_ascii=False, sort_keys=True)
                       for k, v in props.items() if v is not None and k not in {"code", "raw_city", "target_id"}})
        edges[kind].append(record)
        if kind in org_slugs:
            for candidate in (linkedin_org_slug(link, kind), slug(company_id) if kind == "company" and company_id else None):
                if candidate:
                    org_slugs[kind][candidate] = eid
        return eid

    for guest in luma:
        if not isinstance(guest, dict) or not guest.get("api_id"):
            continue
        pid = guest["api_id"]
        handle = guest.get("linkedin_handle")
        li = linkedin_slug(handle) if isinstance(handle, str) and "/in/" in handle.lower() else None
        profile = profiles.get(li) if li else None
        if profile:
            matched += 1
        github_profile = (github or {}).get(pid)
        github_matched = isinstance(github_profile, dict) and bool(github_profile.get("match")) and not github_profile.get("error")
        people.append({"id": pid, "name": person_name(guest), "linkedin": li or "", "avatar": guest.get("avatar_url") or "", "matched": bool(profile), "github_matched": github_matched})
        if li:
            linkedin_people[li].append(pid)
        handle_x = x_handle(guest.get("twitter_handle"))
        if handle_x:
            x_people[handle_x].append(pid)
        handle_ig = instagram_handle(guest.get("instagram_handle"))
        if handle_ig:
            instagram_people[handle_ig].append(pid)
        if not profile:
            continue
        titled_school = False
        for school in profile.get("education") or []:
            if isinstance(school, dict) and isinstance(school.get("title"), str) and school["title"].strip():
                titled_school = True
                add("school", pid, school["title"], link=school.get("url"), degree=school.get("degree"), field=school.get("field"), start=school.get("start_year"), end=school.get("end_year"))
        if not titled_school and isinstance(profile.get("educations_details"), str):
            add("school", pid, profile["educations_details"])
        experiences = list(profile.get("experience") or [])
        current = profile.get("current_company") or {}
        if isinstance(current, dict) and (current.get("name") or profile.get("current_company_name")):
            experiences.insert(0, {"company": current.get("name") or profile.get("current_company_name"), "company_id": current.get("company_id") or profile.get("current_company_company_id"), "url": current.get("link"), "title": current.get("title") or profile.get("position"), "current": True})
        seen_companies = set()
        for exp in experiences:
            if not isinstance(exp, dict):
                continue
            raw_name = exp.get("company") or exp.get("company_name")
            if isinstance(raw_name, dict):
                raw_name = raw_name.get("name")
            eid = company_canonical.get(slug(raw_name)) or entity_slug(raw_name, "company", exp.get("url"), exp.get("company_id"))
            if not eid or eid in seen_companies:
                continue
            seen_companies.add(eid)
            add("company", pid, raw_name, link=exp.get("url"), company_id=exp.get("company_id"), title=exp.get("title"), start=exp.get("start_date"), end=exp.get("end_date"), current=bool(exp.get("current")))
        raw_city = profile.get("city") or profile.get("location")
        city = city_name(raw_city, profile.get("country_code"))
        if city:
            add("city", pid, city, raw_city=raw_city, country=profile.get("country_code"))
        place = country(profile.get("country_code"))
        if place:
            add("country", pid, place[1], code=place[0])
        for item in profile.get("languages") or []:
            value = item.get("title") if isinstance(item, dict) else item
            lang = language_name(value)
            if lang:
                add("language", pid, lang)
        for item in profile.get("certifications") or []:
            if isinstance(item, dict) and item.get("title"):
                add("cert", pid, item["title"], issuer=item.get("subtitle"))
                issuer = item.get("subtitle")
                certificate_id = cert_id(item["title"], issuer)
                issuer_id = slug(issuer)
                if certificate_id and issuer_id:
                    names[("Issuer", issuer_id)][str(issuer).strip()] += 1
                    edges["cert_issuer"].append({"cert_id": certificate_id, "id": issuer_id})
        for item in profile.get("volunteer_experience") or []:
            if isinstance(item, dict):
                if item.get("subtitle"):
                    add("volunteer", pid, item["subtitle"])
                if item.get("cause"):
                    add("cause", pid, item["cause"])

    def path(kind, source_id, name, *, target_id=None):
        if not source_id or not name:
            return
        eid = target_id or slug(name)
        if not eid:
            return
        label = ORG_PATHS[kind][2]
        names[(label, eid)][str(name).strip()] += 1
        edges[kind].append({"source_id": source_id, "id": eid})

    org_kinds = {"solo": "a one-person company", "government": "a government agency", "nonprofit": "a nonprofit", "public": "a public company", "giant": "companies with 10,000+ employees"}
    company_orgs = defaultdict(list)
    for item in orgs or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        url = (item.get("input") or {}).get("url") or ""
        source = "school" if linkedin_org_slug(url, "school") else "company"
        source_id = org_slugs[source].get(linkedin_org_slug(url, source))
        if not source_id:
            continue
        if source == "company" and isinstance(item.get("name"), str):
            company_orgs[slug(item["name"])].append((source_id, item))
        place = country(item.get("country_code"))
        if source == "school":
            if place:
                path("study_country", source_id, place[1], target_id=place[0])
            continue
        industry = item.get("industries")
        if isinstance(industry, str) and industry.strip().lower() not in {"higher education", "education"}:
            path("industry", source_id, industry)
        if place:
            path("company_country", source_id, place[1], target_id=place[0])
        size, org_type = item.get("company_size"), item.get("organization_type")
        kinds = []
        if isinstance(size, str) and size.strip().lower() in {"1 employee", "1 employees"}:
            kinds.append("solo")
        if isinstance(size, str) and size.strip().startswith("10,001+"):
            kinds.append("giant")
        kinds += [key for key, value in (("government", "Government Agency"), ("nonprofit", "Nonprofit"), ("public", "Public Company")) if str(org_type or "").lower() == value.lower()]
        for key in kinds:
            path("org_kind", source_id, org_kinds[key], target_id=key)
        year = item.get("founded")
        if isinstance(year, int) and not isinstance(year, bool) and (year <= 2015 or year == 2026):
            path("founded_year", source_id, str(year))

    for item in x_profiles or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        handle = x_handle((item.get("input") or {}).get("url"))
        for pid in x_people.get(handle, []):
            joined = item.get("date_joined") or ""
            if isinstance(joined, str) and len(joined) >= 4 and joined[:4].isdigit():
                year = int(joined[:4])
                if year <= 2008:
                    add("x_since", pid, "joined Twitter before 2009", target_id="pre2009")
                elif year <= 2010:
                    add("x_since", pid, str(year))
            if item.get("is_verified") is True:
                add("x_verified", pid, "verified on X", target_id="x_verified")

    for item in posts or []:
        if not isinstance(item, dict) or item.get("error") or not str(item.get("date_posted") or "").startswith("2026-"):
            continue
        for pid in linkedin_people.get(linkedin_slug(item.get("user_id")), []):
            for tag in hashtags(item.get("hashtags")):
                add("hashtag", pid, tag)
            for company in item.get("tagged_companies") or []:
                if isinstance(company, dict):
                    add("tagged_company", pid, company.get("name"), link=company.get("link"))

    for item in instagram or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        handle = instagram_handle((item.get("input") or {}).get("url"))
        for pid in instagram_people.get(handle, []):
            for tag in hashtags(item.get("post_hashtags"), GENERIC_IG_HASHTAGS):
                add("ig_hashtag", pid, tag)

    selected_crunchbase = {}
    for index, item in enumerate(crunchbase or []):
        if not isinstance(item, dict) or item.get("error"):
            continue
        discovery = item.get("discovery_input") or {}
        if isinstance(discovery, str):
            try:
                discovery = ast.literal_eval(discovery)
            except (ValueError, SyntaxError):
                continue
        keyword = discovery.get("keyword") if isinstance(discovery, dict) else None
        if isinstance(keyword, str) and keyword.strip().startswith("{"):
            try:
                keyword = ast.literal_eval(keyword)
            except (ValueError, SyntaxError):
                continue
        if isinstance(keyword, dict):
            keyword = (keyword.get("name") or keyword.get("keyword") or keyword.get("company_name")
                       or keyword.get("company") or keyword.get("value"))
        if not isinstance(keyword, str):
            continue
        cb_host = root_domain(item.get("website"))
        cb_name = slug(item.get("name"))
        for source_id, org in company_orgs.get(slug(keyword), []):
            org_host = root_domain(org.get("website_simplified"))
            same_host = bool(cb_host and cb_host == org_host)
            same_name = bool(cb_name and cb_name == slug(org.get("name")))
            if not same_host and not (same_name and (not cb_host or not org_host)):
                continue
            rank = (same_host, same_name, -index)
            if source_id not in selected_crunchbase or rank > selected_crunchbase[source_id][0]:
                selected_crunchbase[source_id] = (rank, item)

    for source_id, (_, item) in selected_crunchbase.items():
        for investor in item.get("investors") or []:
            if not isinstance(investor, dict):
                continue
            value = investor.get("investor") or investor.get("value") or investor.get("name")
            if isinstance(value, dict):
                value = value.get("value") or value.get("name")
            if isinstance(value, str) and value.strip():
                path("investor", source_id, value)
        stage = funding_stage(item.get("last_funding_type"))
        if "last_funding_type" not in item:
            rounds = item.get("funding_rounds_list") or []
            if rounds and isinstance(rounds[0], dict):
                title = rounds[0].get("title") or ""
                if isinstance(title, str):
                    stage = funding_stage(title.split(" - ", 1)[0])
        if stage:
            path("funding_stage", source_id, stage)

    known_people = {p["id"] for p in people}
    for pid, item in (github or {}).items():
        if not isinstance(item, dict) or item.get("error") or not item.get("match") or pid not in known_people:
            continue
        for repo in (item.get("repositoriesContributedTo") or {}).get("nodes") or []:
            if isinstance(repo, dict) and repo.get("nameWithOwner"):
                add("repo", pid, repo["nameWithOwner"], stars=repo.get("stargazerCount"))
        for org in (item.get("organizations") or {}).get("nodes") or []:
            if isinstance(org, dict) and org.get("login"):
                add("gh_org", pid, org.get("name") or org["login"], target_id=org["login"].lower())
        languages = Counter()
        for repo in (item.get("repositories") or {}).get("nodes") or []:
            if isinstance(repo, dict) and not repo.get("isFork") and isinstance(repo.get("primaryLanguage"), dict):
                lang = repo["primaryLanguage"].get("name")
                if lang:
                    languages[lang] += 1
        for lang, count in languages.items():
            if count >= 2:
                add("prog_lang", pid, lang)
        created = item.get("createdAt") or ""
        if isinstance(created, str) and len(created) >= 4 and created[:4].isdigit() and int(created[:4]) <= 2011:
            add("gh_since", pid, "joined GitHub before 2012", target_id="pre2012")

    entities = defaultdict(list)
    for (label, eid), counts in names.items():
        name = counts.most_common(1)[0][0]
        row = {"id": eid, "name": name}
        if label == "City":
            row["country"] = next((e.get("country", "") for e in edges["city"] if e["id"] == eid), "")
        if label == "Cert":
            row["issuer"] = next((e.get("issuer", "") for e in edges["cert"] if e["id"] == eid), "")
        if label == "Repo":
            row["stars"] = next((e.get("stars") or 0 for e in edges["repo"] if e["id"] == eid), 0)
        entities[label].append(row)
    return people, entities, edges, matched


def set_hidden(graph, pid, fact_id, hidden=True):
    """Hide ordinary graph edges; combo suppression lives in optins.json."""
    kind, sep, ids = str(fact_id).partition(":")
    if not sep:
        return
    if kind == "cert_issuer":
        graph.query("MATCH (p:Person {id:$pid})-[r:CERTIFIED]->(:Cert)-[:ISSUED_BY]->(i:Issuer {id:$eid}) SET r.hidden=$hidden", {"pid": pid, "eid": ids, "hidden": hidden})
    elif kind in ORG_PATHS:
        source_label, rel, target_label, _ = ORG_PATHS[kind]
        first = "WORKED_AT" if source_label == "Company" else "STUDIED_AT"
        current_only = " WHERE r.current=true" if kind in {"investor", "funding_stage"} else ""
        graph.query(f"MATCH (p:Person {{id:$pid}})-[r:{first}]->(:{source_label})-[:{rel}]->(x:{target_label} {{id:$eid}}){current_only} SET r.hidden=$hidden", {"pid": pid, "eid": ids, "hidden": hidden})
    elif kind in KINDS:
        rel, label = KINDS[kind]
        graph.query(f"MATCH (p:Person {{id:$pid}})-[r:{rel}]->(x:{label} {{id:$eid}}) SET r.hidden=$hidden", {"pid": pid, "eid": ids, "hidden": hidden})
    elif kind in {"school_company", "company_company", "school_industry", "school_stage", "school_investor", "repo_lang"}:
        # Combo hides live in optins.json and are applied by fact_catalog.
        return


def rebuild(luma_path, linkedin_path, graph_name, orgs_path=None, x_path=None, posts_path=None, github_path=None, instagram_path=None, crunchbase_path=None):
    luma = json.loads(Path(luma_path).read_text(encoding="utf-8"))
    if not isinstance(luma, list):
        raise ValueError("Luma input must be a JSON list")
    linkedin = None
    if Path(linkedin_path).exists():
        try:
            linkedin = json.loads(Path(linkedin_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if not isinstance(linkedin, list):
        linkedin = []
        print(f"LinkedIn profiles unavailable ({linkedin_path}); loading Luma people only.")
    def optional(path, expected):
        path = Path(path)
        if not path.exists():
            print(f"Skipping {path.name}: file missing.")
            return expected()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Skipping {path.name}: invalid JSON.")
            return expected()
        if not isinstance(value, expected):
            print(f"Skipping {path.name}: expected {expected.__name__}.")
            return expected()
        return value
    orgs = optional(orgs_path or ROOT / "data" / "orgs_raw.json", list)
    x_profiles = optional(x_path or ROOT / "data" / "x_raw.json", list)
    posts = optional(posts_path or ROOT / "data" / "li_posts_raw.json", list)
    github = optional(github_path or ROOT / "data" / "github_raw.json", dict)
    instagram = optional(instagram_path or ROOT / "data" / "instagram_raw.json", list)
    crunchbase = optional(crunchbase_path or ROOT / "data" / "crunchbase_raw.json", list)
    people, entities, edges, matched = prepare(luma, linkedin, orgs, x_profiles, posts, github, instagram, crunchbase)
    graph = graph_client(graph_name)
    try:
        graph.delete()
    except Exception:
        pass
    for label in sorted({"Person", "Issuer", *{v[1] for v in KINDS.values()}, *{v[2] for v in ORG_PATHS.values()}}):
        graph.query(f"CREATE INDEX FOR (x:{label}) ON (x.id)")
    if people:
        graph.query("UNWIND $rows AS row CREATE (p:Person {id:row.id, name:row.name, linkedin:row.linkedin, avatar:row.avatar, matched:row.matched, github_matched:row.github_matched, opted_in:false, opted_in_at:''})", {"rows": people})
    for label, rows in entities.items():
        if rows:
            extra = " SET x.country=row.country" if label == "City" else " SET x.issuer=row.issuer" if label == "Cert" else " SET x.stars=row.stars" if label == "Repo" else ""
            graph.query(f"UNWIND $rows AS row CREATE (x:{label} {{id:row.id, name:row.name}}){extra}", {"rows": rows})
    for kind, rows in edges.items():
        if kind == "cert_issuer":
            if rows:
                graph.query("UNWIND $rows AS row MATCH (c:Cert {id:row.cert_id}), (i:Issuer {id:row.id}) MERGE (c)-[:ISSUED_BY]->(i)", {"rows": rows})
            continue
        if kind in ORG_PATHS:
            source_label, rel, target_label, _ = ORG_PATHS[kind]
            graph.query(f"UNWIND $rows AS row MATCH (s:{source_label} {{id:row.source_id}}), (x:{target_label} {{id:row.id}}) MERGE (s)-[:{rel}]->(x)", {"rows": rows})
            continue
        rel, label = KINDS[kind]
        if rows:
            properties = {"school": ["degree", "field", "start", "end"], "company": ["title", "start", "end", "current"]}.get(kind, [])
            setters = ", ".join(f"r.{field}=row.{field}" for field in properties)
            setters = ", " + setters if setters else ""
            graph.query(f"UNWIND $rows AS row MATCH (p:Person {{id:row.pid}}), (x:{label} {{id:row.id}}) MERGE (p)-[r:{rel}]->(x) SET r.hidden=false{setters}", {"rows": rows})
    known = {p["id"] for p in people}
    for pid, state in load_optins().items():
        if pid not in known:
            continue
        graph.query("MATCH (p:Person {id:$pid}) SET p.opted_in=true, p.opted_in_at=$at", {"pid": pid, "at": state.get("opted_in_at", "")})
        for fact_id in state.get("hidden", []):
            set_hidden(graph, pid, fact_id)
    from facts import eligible_facts
    facts = eligible_facts(graph)
    github_matched = sum(1 for p in people if isinstance(github.get(p["id"]), dict) and github[p["id"]].get("match") and not github[p["id"]].get("error"))
    print(f"People loaded: {len(people)}; LinkedIn profiles matched: {matched}; GitHub accounts matched: {github_matched}")
    for label, rows in sorted(entities.items()):
        print(f"{label} nodes: {len(rows)}")
    for kind, rows in edges.items():
        rel = KINDS[kind][0] if kind in KINDS else ORG_PATHS[kind][1] if kind in ORG_PATHS else "ISSUED_BY"
        print(f"{rel} edges: {len(rows)}")
    print(f"Screen-eligible facts: {len(facts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--luma", default=str(ROOT / "data" / "luma_guests.json"))
    parser.add_argument("--linkedin", default=str(ROOT / "data" / "linkedin_raw.json"))
    parser.add_argument("--orgs", default=str(ROOT / "data" / "orgs_raw.json"))
    parser.add_argument("--x", default=str(ROOT / "data" / "x_raw.json"))
    parser.add_argument("--li-posts", default=str(ROOT / "data" / "li_posts_raw.json"))
    parser.add_argument("--github", default=str(ROOT / "data" / "github_raw.json"))
    parser.add_argument("--instagram", default=str(ROOT / "data" / "instagram_raw.json"))
    parser.add_argument("--crunchbase", default=str(ROOT / "data" / "crunchbase_raw.json"))
    parser.add_argument("--graph", default=os.getenv("GRAPH", "roomfacts"))
    args = parser.parse_args()
    rebuild(args.luma, args.linkedin, args.graph, args.orgs, args.x, args.li_posts, args.github, args.instagram, args.crunchbase)
