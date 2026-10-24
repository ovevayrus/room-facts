"""Name lookup at opt-in (optionally OpenAI-assisted) and who an opted-in person shares facts with."""
import difflib
import json
import os

import httpx

from build_graph import KINDS, ORG_PATHS, ROOT
from facts import YOU_LINES
from normalize import COUNTRIES, country_phrase

DEFAULT_MODEL = "gpt-5-mini"
# Two-hop paths worth showing between two people (same industry, same HQ country, ...).
PAIR_PATHS = ("industry", "company_country", "study_country", "investor", "funding_stage")
KIND_OF = {value: kind for kind, value in KINDS.items()}


def env(name):
    """Read a setting from the environment, then from .env (re-read, so adding a key needs no restart)."""
    if os.getenv(name):
        return os.getenv(name)
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip('"').strip("'")
    return ""


def llm_json(system, user, schema, name):
    body = {
        "model": env("OPENAI_MODEL") or DEFAULT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    if env("OPENAI_REASONING_EFFORT"):
        body["reasoning_effort"] = env("OPENAI_REASONING_EFFORT")
    response = httpx.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}, json=body, timeout=20)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


PICK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ids"],
    "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
}
PICK_PROMPT = """An attendee typed their own name (or LinkedIn handle) to find themself on a conference guest list.
From the candidates given, return the ids of the people they could be, best match first, at most 3.
Allow typos, nicknames, missing or reordered names, and handles. Return an empty list if none fit."""


def close_names(people, q, limit=12):
    """Guests whose name or handle is close to the typed text, without an exact substring hit."""
    q = " ".join(q.lower().split())
    words = q.split()
    ratio = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
    scored = []
    for pid, name, avatar, linkedin in people:
        full = [option for option in (str(name or "").lower(), str(linkedin or "").lower().replace("-", " ")) if option]
        tokens = str(name or "").lower().split()
        # Whole-string similarity, or every typed word matching some word of the name (handles "Jai Gupta").
        scores = [ratio(q, option) for option in full]
        if tokens and words:
            scores.append(sum(max(ratio(w, t) for t in tokens) for w in words) / len(words))
        score = max(scores, default=0)
        if score >= 0.6:
            scored.append((score, pid, name, avatar))
    scored.sort(key=lambda row: (-row[0], row[2] or ""))
    return scored[:limit]


def lookup(graph, q):
    """Fallback name search: fuzzy candidates, narrowed by OpenAI when a key is configured."""
    people = graph.ro_query("MATCH (p:Person) RETURN p.id, p.name, p.avatar, p.linkedin").result_set
    candidates = close_names(people, q)
    if not candidates:
        return []
    if env("OPENAI_API_KEY"):
        try:
            payload = {"typed": q, "candidates": [{"id": pid, "name": name} for _, pid, name, _ in candidates]}
            ids = llm_json(PICK_PROMPT, json.dumps(payload, ensure_ascii=False), PICK_SCHEMA, "name_match").get("ids", [])
            by_id = {pid: (pid, name, avatar) for _, pid, name, avatar in candidates}
            return [{"id": pid, "name": by_id[pid][1] or "", "avatar": by_id[pid][2] or ""} for pid in ids[:3] if pid in by_id]
        except Exception as error:
            print(f"OpenAI name lookup failed, using fuzzy matches: {error}")
    return [{"id": pid, "name": name or "", "avatar": avatar or ""} for _, pid, name, avatar in candidates[:3]]


def both_line(kind, name):
    if kind in {"country", "company_country", "study_country"}:
        name = country_phrase(COUNTRIES.get(str(name).upper(), name))
    line = YOU_LINES[kind].format(a=name, b=name)
    for start, both in (("You are ", "You're both "), ("You have ", "You've both "), ("You ", "You both ")):
        if line.startswith(start):
            return both + line[len(start):]
    return line


def first_name(name):
    return (str(name or "").split() or ["them"])[0]


def connections(graph, viewer, catalog):
    """Opted-in people who share at least one visible fact with the viewer, rarest overlap first."""
    people = {}

    def add(pid, name, avatar, linkedin, key, line, path):
        # Only facts both people visibly hold in the catalog: hidden facts, hidden combos and facts
        # still pending review are already left out of "holders".
        fact = catalog.get(key)
        if not fact or viewer not in fact["holders"] or pid not in fact["holders"]:
            return
        person = people.setdefault(pid, {"name": name or "", "avatar": avatar or "", "linkedin": linkedin or "", "shared": {}})
        person["shared"].setdefault(key, {"n": max(len(fact["holders"]), 2), "line": line, "path": path})

    rows = graph.ro_query(
        "MATCH (v:Person {id:$v})-[r1]->(x)<-[r2]-(o:Person) "
        "WHERE o.opted_in=true AND o.id<>$v AND type(r1)=type(r2) AND r1.hidden=false AND r2.hidden=false "
        "RETURN o.id, o.name, o.avatar, o.linkedin, type(r1), labels(x)[0], x.id, x.name", {"v": viewer}).result_set
    for pid, name, avatar, linkedin, rel, label, eid, ename in rows:
        kind = KIND_OF.get((rel, label))
        if kind:
            add(pid, name, avatar, linkedin, f"{kind}:{eid}", both_line(kind, ename), ["You", rel, ename, rel, first_name(name)])
    for kind in PAIR_PATHS:
        source, rel, target, _ = ORG_PATHS[kind]
        first = "WORKED_AT" if source == "Company" else "STUDIED_AT"
        current = " AND r1.current=true AND r2.current=true" if kind in {"investor", "funding_stage"} else ""
        rows = graph.ro_query(
            f"MATCH (v:Person {{id:$v}})-[r1:{first}]->(a:{source})-[:{rel}]->(x:{target})<-[:{rel}]-(b:{source})<-[r2:{first}]-(o:Person) "
            f"WHERE o.opted_in=true AND o.id<>$v AND a.id<>b.id AND r1.hidden=false AND r2.hidden=false{current} "
            "RETURN o.id, o.name, o.avatar, o.linkedin, x.id, x.name, a.name, b.name", {"v": viewer}).result_set
        for pid, name, avatar, linkedin, eid, ename, aname, bname in rows:
            add(pid, name, avatar, linkedin, f"{kind}:{eid}", both_line(kind, ename), ["You", first, aname, rel, ename, rel, bname, first, first_name(name)])
    result = []
    for pid, person in people.items():
        shared = sorted(person["shared"].values(), key=lambda s: (s["n"], s["line"]))
        result.append({"name": person["name"], "avatar": person["avatar"], "linkedin": person["linkedin"], "score": sum(1 / s["n"] for s in shared),
                       "shared": [{"line": s["line"], "path": s["path"]} for s in shared[:3]], "more": max(len(shared) - 3, 0)})
    result.sort(key=lambda p: (-p["score"], p["name"]))
    return result
