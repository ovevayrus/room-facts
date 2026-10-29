"""Name lookup at opt-in (optionally OpenAI-assisted) and who an opted-in person shares facts with."""
from collections import defaultdict
import difflib
import json
import os
from threading import BoundedSemaphore

import httpx

from build_graph import ROOT
from facts import fact_path

DEFAULT_MODEL = "gpt-5-mini"
# At most two OpenAI lookups at once; extra requests use the fuzzy matches alone.
_openai_slots = BoundedSemaphore(2)


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
    response = httpx.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}, json=body, timeout=8)
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
        # Whole-string similarity, or every typed word matching some word of the name (handles "Sam Rivera").
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
    if env("OPENAI_API_KEY") and _openai_slots.acquire(blocking=False):
        try:
            payload = {"typed": q, "candidates": [{"id": pid, "name": name} for _, pid, name, _ in candidates]}
            ids = llm_json(PICK_PROMPT, json.dumps(payload, ensure_ascii=False), PICK_SCHEMA, "name_match").get("ids", [])
            by_id = {pid: (pid, name, avatar) for _, pid, name, avatar in candidates}
            return [{"id": pid, "name": by_id[pid][1] or "", "avatar": by_id[pid][2] or ""} for pid in ids[:3] if pid in by_id]
        except Exception as error:
            print(f"OpenAI name lookup failed, using fuzzy matches: {error}")
        finally:
            _openai_slots.release()
    return [{"id": pid, "name": name or "", "avatar": avatar or ""} for _, pid, name, avatar in candidates[:3]]


def both_line(line_you):
    """Turn a catalog "You ..." line into a "You both ..." line."""
    rest = line_you[4:] if line_you.startswith("You ") else line_you
    if rest.startswith("are "):
        return "You're both " + rest[4:]
    if rest.startswith("have ") and (rest.split()[1:2] or [""])[0].endswith(("ed", "been")):
        return "You've both " + rest[5:]
    return "You both " + rest


def first_name(name):
    return (str(name or "").split() or ["them"])[0]


def connections(graph, viewer, catalog):
    """Opted-in people who share at least one visible catalog fact with the viewer, rarest overlap first.

    Built from catalog holders, so every fact kind counts, and hidden, hidden-combo and pending facts
    (already left out of "holders") never show. Paths come from fact_path, which names only the shared
    entity, never the other person's own company or school.
    """
    shared = defaultdict(list)
    for fact in catalog.values():
        holders = fact["holders"]
        if viewer in holders and len(holders) > 1:
            for pid in holders - {viewer}:
                shared[pid].append(fact)
    if not shared:
        return []
    rows = graph.ro_query("MATCH (p:Person) WHERE p.id IN $ids AND p.opted_in=true RETURN p.id, p.name, p.avatar, p.linkedin", {"ids": sorted(shared)}).result_set
    result = []
    for pid, name, avatar, linkedin in rows:
        facts = sorted(shared[pid], key=lambda f: (len(f["holders"]), f["line_you"]))
        lines = []
        for fact in facts:
            try:
                path = fact_path(fact)[:-1] + [first_name(name)]
            except (KeyError, IndexError):
                path = None
            lines.append({"line": both_line(fact["line_you"]), "path": path})
        result.append({"name": name or "", "avatar": avatar or "", "linkedin": linkedin or "", "score": sum(1 / len(f["holders"]) for f in facts),
                       "shared": lines[:3], "more": max(len(lines) - 3, 0)})
    result.sort(key=lambda p: (-p["score"], p["name"]))
    return result
