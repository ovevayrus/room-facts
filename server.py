"""Room Facts API and static entry points."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from threading import RLock
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from build_graph import OPTINS, graph_client, load_optins, set_hidden
from facts import eligible_facts, fact_catalog, fact_path, graph_rows, public_fact, rotation

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Room Facts")
app.mount("/static", StaticFiles(directory=ROOT / "static", check_dir=False), name="static")
_lock = RLock()
_cache = {"at": 0.0, "catalog": {}, "facts": [], "generated_at": ""}
_events = []


def graph():
    return graph_client()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def snapshot(force=False):
    with _lock:
        if force or time.monotonic() - _cache["at"] >= 5:
            catalog = fact_catalog(graph_rows(graph()))
            _cache.update(at=time.monotonic(), catalog=catalog, facts=[public_fact(f) for f in rotation(catalog)], generated_at=now_iso())
        return _cache


def person_row(pid):
    rows = graph().ro_query("MATCH (p:Person {id:$pid}) RETURN p.id, p.name, p.avatar, p.linkedin, p.opted_in", {"pid": pid}).result_set
    if not rows:
        raise HTTPException(404, "Person not found")
    row = rows[0]
    return {"id": row[0], "name": row[1] or "", "avatar": row[2] or "", "linkedin": row[3] or "", "opted_in": bool(row[4])}


def public_person(person):
    return {k: person[k] for k in ("id", "name", "avatar", "linkedin")}


def auth_person(request):
    token = request.cookies.get("rf_token")
    if not token:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for pid, state in load_optins().items():
        if digest in state.get("tokens", []):
            try:
                person = person_row(pid)
            except HTTPException:
                return None
            return person if person["opted_in"] else None
    return None


def save_optins(data):
    OPTINS.parent.mkdir(parents=True, exist_ok=True)
    temp = OPTINS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(OPTINS)


@app.get("/")
def root():
    return RedirectResponse("/screen")


@app.get("/screen")
def screen():
    return FileResponse(ROOT / "static" / "screen.html")


@app.get("/m")
def mobile():
    return FileResponse(ROOT / "static" / "m.html")


@app.get("/api/config")
def config(request: Request):
    return {"public_base_url": (os.getenv("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")}


@app.get("/api/facts")
def facts_list():
    snap = snapshot()
    return {"facts": snap["facts"], "generated_at": snap["generated_at"]}


def fact_detail(id: str):
    item = snapshot()["catalog"].get(id)
    if not item or not item["eligible"]:
        raise HTTPException(404, "Fact not found")
    return {**public_fact(item), "path": fact_path(item)}


@app.get("/api/stats")
def stats():
    g = graph()
    rows = g.ro_query("MATCH (p:Person) RETURN count(p), sum(CASE WHEN p.matched THEN 1 ELSE 0 END), sum(CASE WHEN p.opted_in THEN 1 ELSE 0 END), sum(CASE WHEN p.github_matched THEN 1 ELSE 0 END)").result_set
    guests, matched, opted, github_matched = rows[0] if rows else (0, 0, 0, 0)
    counts = {}
    for label in ("School", "Company", "Country", "City"):
        counts[label] = int(g.ro_query(f"MATCH (:Person)-[r]->(x:{label}) WHERE r.hidden=false RETURN count(DISTINCT x)").result_set[0][0] or 0)
    minimum = max(3, int(os.getenv("MIN_N", "3")))
    tops = {}
    for label, key in (("School", "top_schools"), ("Company", "top_companies")):
        rows = g.ro_query(f"MATCH (p:Person)-[r]->(x:{label}) WHERE r.hidden=false WITH x, count(DISTINCT p) AS n WHERE n >= $min RETURN x.name, n ORDER BY n DESC, x.name LIMIT 3", {"min": minimum}).result_set
        tops[key] = [{"name": name, "count": int(n or 0)} for name, n in rows]
    return {"guests": int(guests or 0), "linkedin_profiles_matched": int(matched or 0), "github_matched": int(github_matched or 0), "schools": counts["School"], "companies": counts["Company"], "countries": counts["Country"], "cities": counts["City"], "opted_in": int(opted or 0), **tops}


@app.get("/api/events")
def events(since: str | None = None):
    if since:
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(422, "Invalid since timestamp")
    else:
        cutoff = None
    eligible = {f["id"] for f in snapshot()["catalog"].values() if f["eligible"]}
    return [{"at": e["at"], "text": e["text"]} for e in _events if e["fact_id"] in eligible and (not cutoff or datetime.fromisoformat(e["at"]) > cutoff)]


@app.get("/api/people/search")
def people_search(q: str = ""):
    q = q.strip()
    if len(q) < 2:
        return []
    rows = graph().ro_query("MATCH (p:Person) WHERE toLower(p.name) CONTAINS toLower($q) OR toLower(p.linkedin) CONTAINS toLower($q) RETURN p.id, p.name, p.avatar ORDER BY p.name LIMIT 8", {"q": q}).result_set
    return [{"id": pid, "name": name or "", "avatar": avatar or ""} for pid, name, avatar in rows]


@app.get("/api/person/{id}")
def person_detail(id: str):
    return public_person(person_row(id))


@app.get("/api/person/{id}/facts")
def person_facts(id: str):
    person_row(id)
    catalog = snapshot()["catalog"]
    values = [f for f in catalog.values() if id in f["all_holders"]]
    values.sort(key=lambda f: (f["n"], f["kind"], f["id"]))
    return [{"fact_id": f["id"], "kind": f["kind"], "line_you": f["line_you"], "n_if_eligible": f["n"] if f["eligible"] else None, "hidden": id in f["hidden_holders"]} for f in values]


class OptInBody(BaseModel):
    person_id: str
    hide: list[str] = Field(default_factory=list)


@app.post("/api/optin")
def optin(body: OptInBody, response: Response):
    person = person_row(body.person_id)
    with _lock:
        catalog = snapshot(force=True)["catalog"]
        allowed = {f["id"] for f in catalog.values() if body.person_id in f["all_holders"]}
        if any(fid not in allowed for fid in body.hide):
            raise HTTPException(422, "A hidden fact does not belong to this person")
        g = graph()
        g.query("MATCH (p:Person {id:$pid})-[r]->() SET r.hidden=false", {"pid": body.person_id})
        for fid in set(body.hide):
            set_hidden(g, body.person_id, fid)
        at = now_iso()
        g.query("MATCH (p:Person {id:$pid}) SET p.opted_in=true, p.opted_in_at=$at", {"pid": body.person_id, "at": at})
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        saved = load_optins()
        saved[body.person_id] = {"opted_in_at": at, "hidden": sorted(set(body.hide)), "tokens": [digest]}
        save_optins(saved)
        snap = snapshot(force=True)
        suitable = next((f for f in snap["catalog"].values() if f["eligible"] and body.person_id in f["holders"]), None)
        if suitable:
            _events.append({"at": at, "text": suitable["line_event"] + " just opted in", "fact_id": suitable["id"]})
            del _events[:-50]
    response.set_cookie("rf_token", token, httponly=True, samesite="lax", secure=os.getenv("PUBLIC_BASE_URL", "").startswith("https://"))
    return {"ok": True, "person": public_person(person)}


@app.post("/api/optout")
def optout(request: Request, response: Response):
    person = auth_person(request)
    if not person:
        raise HTTPException(401, "Not opted in")
    with _lock:
        g = graph()
        g.query("MATCH (p:Person {id:$pid}) SET p.opted_in=false, p.opted_in_at=''", {"pid": person["id"]})
        g.query("MATCH (p:Person {id:$pid})-[r]->() SET r.hidden=false", {"pid": person["id"]})
        saved = load_optins()
        saved.pop(person["id"], None)
        save_optins(saved)
        snapshot(force=True)
    response.delete_cookie("rf_token")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    person = auth_person(request)
    if not person:
        raise HTTPException(401, "Not opted in")
    return public_person(person)


@app.get("/api/fact/{id:path}/people")
def fact_people(id: str, request: Request):
    person = auth_person(request)
    if not person:
        raise HTTPException(403, "Opt-in required")
    fact = snapshot(force=True)["catalog"].get(id)
    if not fact or not fact["eligible"] or person["id"] not in fact["holders"]:
        raise HTTPException(403, "Fact membership required")
    rows = graph().ro_query("MATCH (p:Person) WHERE p.id IN $ids AND p.opted_in=true RETURN p.id, p.name, p.avatar, p.linkedin ORDER BY p.name", {"ids": list(fact["holders"])}).result_set
    people = [{"name": name or "", "avatar": avatar or "", "linkedin_url": f"https://www.linkedin.com/in/{li}" if li else ""} for pid, name, avatar, li in rows if pid != person["id"]]
    return {"people": people, "hidden_count": fact["n"] - fact["opted_in"]}


app.add_api_route("/api/fact/{id:path}", fact_detail, methods=["GET"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
