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
from facts import eligible_facts, fact_catalog, fact_path, graph_rows, hidden_combos_from_optins, public_fact, rotation

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
            catalog = fact_catalog(graph_rows(graph()), hidden_combos=hidden_combos_from_optins(load_optins()))
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
    # Count from the catalog so hidden and pending holders are excluded exactly as on the screens.
    catalog = snapshot()["catalog"].values()
    counts = {kind: sum(1 for f in catalog if f["kind"] == kind and f["n"]) for kind in ("school", "company", "country", "city")}
    minimum = max(3, int(os.getenv("MIN_N", "3")))
    tops = {}
    for kind, key in (("school", "top_schools"), ("company", "top_companies")):
        top = sorted((f for f in catalog if f["kind"] == kind and f["n"] >= minimum), key=lambda f: (-f["n"], f["entities"][0]["name"]))[:3]
        tops[key] = [{"name": f["entities"][0]["name"], "count": f["n"]} for f in top]
    return {"guests": int(guests or 0), "linkedin_profiles_matched": int(matched or 0), "github_matched": int(github_matched or 0), "schools": counts["school"], "companies": counts["company"], "countries": counts["country"], "cities": counts["city"], "opted_in": int(opted or 0), **tops}


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


def publicly_listed(fact, pid):
    """The pre-opt-in checklist: facts anyone may see for this person."""
    return fact["eligible"] and fact["n"] >= 3 and pid in fact["holders"] and pid not in fact["hidden_holders"]


def apply_hidden(g, pid, hidden):
    g.query("MATCH (p:Person {id:$pid})-[r]->() SET r.hidden=false", {"pid": pid})
    for fid in hidden:
        set_hidden(g, pid, fid)


@app.get("/api/person/{id}/facts")
def person_facts(id: str, request: Request):
    person_row(id)
    catalog = snapshot()["catalog"]
    owner = auth_person(request)
    private = bool(owner and owner["id"] == id)
    pending = set(load_optins().get(id, {}).get("pending", [])) if private else set()
    values = [f for f in catalog.values() if id in f["all_holders"] and (private or publicly_listed(f, id))]
    values.sort(key=lambda f: (f["n"], f["kind"], f["id"]))
    return [{**{"fact_id": f["id"], "kind": f["kind"], "line_you": f["line_you"], "n_if_eligible": f["n"] if f["eligible"] else None},
             **({"hidden": id in f["hidden_holders"] and f["id"] not in pending, "pending": f["id"] in pending} if private else {})} for f in values]


class OptInBody(BaseModel):
    person_id: str
    hide: list[str] = Field(default_factory=list)


@app.post("/api/optin")
def optin(body: OptInBody, request: Request, response: Response):
    person = person_row(body.person_id)
    pid = body.person_id
    owner = auth_person(request)
    is_owner = bool(owner and owner["id"] == pid)
    with _lock:
        catalog = snapshot(force=True)["catalog"]
        mine = {f["id"] for f in catalog.values() if pid in f["all_holders"]}
        if any(fid not in mine for fid in body.hide):
            raise HTTPException(422, "A hidden fact does not belong to this person")
        saved = load_optins()
        previous = saved.get(pid, {})
        if is_owner:
            # The owner reviewed their full private list, so their choices replace the saved ones.
            hidden, pending, approved = set(body.hide), set(), mine - set(body.hide)
        else:
            # Without the owner's cookie, saved hides can only grow, and anything not in the
            # public checklist or approved before stays pending until the owner reviews it.
            shown = {f["id"] for f in catalog.values() if publicly_listed(f, pid)}
            hidden = set(previous.get("hidden", [])) | set(body.hide)
            approved = (set(previous.get("approved", [])) | shown) - hidden
            pending = (set(previous.get("pending", [])) | (mine - approved)) - hidden
        g = graph()
        apply_hidden(g, pid, hidden)
        at = now_iso()
        g.query("MATCH (p:Person {id:$pid}) SET p.opted_in=true, p.opted_in_at=$at", {"pid": pid, "at": at})
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        saved[pid] = {"opted_in_at": at, "hidden": sorted(hidden), "pending": sorted(pending), "approved": sorted(approved), "tokens": [digest]}
        save_optins(saved)
        snap = snapshot(force=True)
        suitable = next((f for f in snap["catalog"].values() if f["eligible"] and pid in f["holders"]), None)
        if suitable:
            _events.append({"at": at, "text": suitable["line_event"] + " just opted in", "fact_id": suitable["id"]})
            del _events[:-50]
    response.set_cookie("rf_token", token, httponly=True, samesite="lax", secure=os.getenv("PUBLIC_BASE_URL", "").startswith("https://"))
    return {"ok": True, "person": public_person(person)}


class FactReviewBody(BaseModel):
    hide: list[str] = Field(default_factory=list)
    show: list[str] = Field(default_factory=list)


@app.post("/api/me/facts")
def review_facts(body: FactReviewBody, request: Request):
    person = auth_person(request)
    if not person:
        raise HTTPException(401, "Not opted in")
    pid = person["id"]
    hide, show = set(body.hide), set(body.show)
    if hide & show:
        raise HTTPException(422, "A fact cannot be both hidden and shown")
    with _lock:
        saved = load_optins()
        state = saved.get(pid, {})
        allowed = {f["id"] for f in snapshot(force=True)["catalog"].values() if pid in f["all_holders"]}
        allowed |= set(state.get("hidden", [])) | set(state.get("pending", []))
        if any(fid not in allowed for fid in hide | show):
            raise HTTPException(422, "A fact does not belong to this person")
        hidden = (set(state.get("hidden", [])) | hide) - show
        pending = set(state.get("pending", [])) - hide - show
        approved = (set(state.get("approved", [])) | show) - hide
        apply_hidden(graph(), pid, hidden)
        saved[pid] = {**state, "hidden": sorted(hidden), "pending": sorted(pending), "approved": sorted(approved)}
        save_optins(saved)
        snapshot(force=True)
    return person_facts(pid, request)


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
