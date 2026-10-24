# Room Facts: live build spec

Hackathon demo for today (Patch the Conference, judging 5:30 pm). Rotating screens at the venue show **rare, anonymous overlaps** among the 616 registered guests ("4 people here studied at UC Berkeley"). Each fact has a QR code. Scanning it opens a phone page where an attendee finds themself, confirms their facts, and opts in. They can then see the *other opted-in* people who share that fact. The graph lives in FalkorDB; every fact is a graph pattern, and we show the path behind it.

Project folder: `C:\Users\oveva\01winningiphones\roomfacts` (Windows, Python 3.13, FalkorDB in Docker at `localhost:6379`, FalkorDB Browser at `localhost:3000`). Installed: `falkordb` 1.8, `fastapi`, `uvicorn`, `requests`, `httpx`, `pytest`.

**Do not touch** `fetch_luma.py`, `enrich_linkedin.py`, `bd_key.py`, or anything in `data/` except `data/optins.json`. Never print or log the Bright Data key.

## Privacy rules (hard requirements)

1. The screens and every public endpoint return **counts only**. A fact needs `n >= MIN_N` (default 3) holders to appear anywhere public. A count below 3 is never shown, not even as "fewer than 3".
2. Names are returned only by `GET /api/fact/{id}/people`, and only when the requester is opted in (valid token cookie) **and** holds that fact. It returns only holders who are also opted in.
3. People can hide any of their facts (wrong data). Hidden edges don't count anywhere.
4. Opt-in state survives a graph rebuild: persist it to `data/optins.json` (`{person_id: {"opted_in_at": iso, "hidden": [fact_id, ...], "pending": [fact_id, ...], "tokens": [sha256, ...]}}`) and re-apply it after loading. `pending` facts were never shown to the person, so they don't count anywhere until the owner approves them.

## Inputs

`data/luma_guests.json`: list of Luma users:
```json
{"api_id": "usr-…", "name": "Jai", "first_name": "Jai Surya", "last_name": "Gupta", "avatar_url": "https://…",
 "bio_short": "", "linkedin_handle": "/in/jai-surya-gupta", "twitter_handle": "…", "instagram_handle": "…",
 "website": null, "timezone": "America/Los_Angeles", "username": null, "youtube_handle": null, "tiktok_handle": null}
```
Use `first_name + " " + last_name` when both exist, else `name`. 576 guests have a valid `/in/<slug>` handle. Some handles are `/company/…`, `/in/` or free text: treat those as no LinkedIn.

`data/linkedin_raw.json` (Bright Data "LinkedIn people profiles", dataset `gd_l1viktl72bvl7bjuj0`). It may not exist yet when you start, because a scrape is still running. Write tolerant code: every field can be missing or null. It's a list of records. Error records have an `error` key plus `input.url`. Join to Luma by the LinkedIn slug: `linkedin_id`, or the slug from `input.url` / `input_url`, compared case-insensitively. Fields seen:
```
linkedin_id, name, first_name, last_name, city ("Pune, Maharashtra, India" | "San Francisco Bay Area" | "Singapore, Singapore"),
country_code ("IN","US","SG"), location, about, position, avatar, followers, connections,
current_company {name, company_id, title, link, location}, current_company_name, current_company_company_id,
experience [{title, company, company_id, url, location, start_date, end_date, positions:[{title,...}]}],
education [{title, url ("https://www.linkedin.com/school/<slug>/"), start_year, end_year, degree, field, description}]
  (some entries have no title; skip those),
educations_details (string), languages [{title, subtitle}], certifications [{title, subtitle (issuer), meta, credential_url}],
volunteer_experience [{title, subtitle (org), cause, start_date}], honors_and_awards [{title, publication, date}],
organizations, projects [{title, ...}], bio_links [{title, link}], activity, similar_profiles   <- ignore activity & similar_profiles
```
For offline development, create `tests/fixtures/linkedin_sample.json` with about 12 **synthetic** records in this shape, plus a matching `tests/fixtures/luma_sample.json`.

## Graph (`GRAPH` env, default `roomfacts`)

```
(:Person {id: luma api_id, name, linkedin: slug, avatar, opted_in: false, opted_in_at})
(:Person)-[:STUDIED_AT {degree, field, start, end}]->(:School {id, name})
(:Person)-[:WORKED_AT {title, start, end, current}]->(:Company {id, name})
(:Person)-[:LIVES_IN]->(:City {id, name, country})
(:Person)-[:BASED_IN]->(:Country {id: code, name})
(:Person)-[:SPEAKS]->(:Language {id, name})
(:Person)-[:CERTIFIED]->(:Cert {id, name, issuer})
(:Person)-[:VOLUNTEERED_AT]->(:Org {id, name})
(:Person)-[:VOLUNTEERS_FOR]->(:Cause {id, name})
```
Every relationship gets `hidden: false`. Add indexes on `Person.id` and each label's `id`.

Normalization lives in `normalize.py` as pure, unit-tested functions:
- School and Company ids: prefer the LinkedIn slug (`/school/<slug>/`, `/company/<slug>/`, `company_id`). Otherwise use a slug of the name with case, punctuation, "the", and suffixes like Inc/LLC/Ltd/Corp/GmbH/Pvt stripped. Keep the most common display name.
- Add a small alias table for well-known duplicates (UC Berkeley / University of California, Berkeley; IIT Bombay / Indian Institute of Technology, Bombay; CMU / Carnegie Mellon University; Georgia Tech; UIUC; UT Austin; NYU; …). It's fine for the table to be small.
- Drop non-entities: Self-employed, Freelance, Freelancer, Confidential, Stealth Mode is allowed (keep "Stealth" and "Stealth Startup" as one company id `stealth`), "-", empty.
- City: the first comma part of `city`, but map "San Francisco Bay Area", "Greater Seattle Area", etc. to their metro name. Country from `country_code`. Skip "US" for BASED_IN, because it isn't rare.
- Language: skip English. Normalize case.

`build_graph.py`: drops and rebuilds the graph from the two input files, re-applies `data/optins.json`, and prints a summary: people loaded, matched profiles, nodes and edges per label, and the number of screen-eligible facts.

## Facts (`facts.py`)

A **fact** is a set of opted-in or not-yet-opted-in Person holders, defined by a graph pattern. Kinds:

| kind | pattern | line template |
|---|---|---|
| school | `(p)-[:STUDIED_AT]->(s:School)` | "people here studied at {s}" |
| company | `(p)-[:WORKED_AT]->(c:Company)` | "people here have worked at {c}" |
| city | `(p)-[:LIVES_IN]->(c:City)` | "people here live in {c}" |
| country | `(p)-[:BASED_IN]->(c:Country)` | "people here are based in {c}" |
| language | `(p)-[:SPEAKS]->(l:Language)` | "people here speak {l}" |
| cert | `(p)-[:CERTIFIED]->(c:Cert)` | "people here hold the {c} certification" |
| volunteer | `(p)-[:VOLUNTEERED_AT]->(o:Org)` | "people here have volunteered at {o}" |
| cause | `(p)-[:VOLUNTEERS_FOR]->(c:Cause)` | "people here volunteer for {c}" |
| school_company (path) | `(s:School)<-[:STUDIED_AT]-(p)-[:WORKED_AT]->(c:Company)` | "people here went from {s} to {c}" |
| company_company (path) | `(a:Company)<-[:WORKED_AT]-(p)-[:WORKED_AT]->(b:Company)` with `a.id < b.id` | "people here have worked at both {a} and {b}" |

- Count distinct holders, ignoring hidden edges. Eligible if `MIN_N <= n <= MAX_N` (env, defaults 3 and 12).
- Fact id: `kind:entity_id` (path kinds: `school_company:<s>><c>`). It must be stable across rebuilds.
- Drop a fact if another eligible fact has exactly the same holder set; keep the path fact over the single one, and otherwise the smaller kind order in the table.
- Each fact returns `{id, kind, n, opted_in, line, src, pattern, entities:[{label, name}]}`. `src` is a short provenance string such as "LinkedIn education". `pattern` is the Cypher MATCH as text, used for the "path behind every answer" display.
- Rotation order: sort by `n` ascending (rarest first), then interleave kinds so two facts of the same kind never appear back to back when avoidable.
- Ticker stats (`/api/stats`): guests, linkedin_profiles_matched, schools, companies, countries, cities, opted_in, plus the top 3 schools and top 3 companies **by count** (names plus counts are fine here, because those are big groups).

## API (`server.py`, FastAPI, run with `python server.py` on `0.0.0.0:8000`)

Static pages: `GET /` redirects to `/screen`; `GET /screen` serves `static/screen.html`; `GET /m` serves `static/m.html`; `/static/*`.

| method | path | returns |
|---|---|---|
| GET | `/api/config` | `{public_base_url}` from env `PUBLIC_BASE_URL`, falling back to the request's base URL |
| GET | `/api/facts` | `{facts:[fact…], generated_at}` — eligible facts in rotation order, counts only. Cache 5 s |
| GET | `/api/fact/{id}` | one fact plus `path`: e.g. `["You", "STUDIED_AT", "UC Berkeley", "STUDIED_AT", "3 others"]`. 404 if not eligible |
| GET | `/api/stats` | ticker stats (above) |
| GET | `/api/events?since=<iso>` | recent anonymous opt-in events: `{at, text}`, e.g. "Someone who studied at UC Berkeley just opted in". Only mention eligible facts. Keep the last 50 in memory |
| GET | `/api/people/search?q=` | at most 8 `{id, name, avatar}` (q ≥ 2 chars, case-insensitive substring on name and LinkedIn slug) |
| GET | `/api/person/{id}` | `{id, name, avatar, linkedin}` |
| GET | `/api/person/{id}/facts` | that person's facts: `[{fact_id or null, kind, line_you ("You studied at UC Berkeley"), n_if_eligible or null}]`. Without the person's own `rf_token`, only their public facts (eligible, n ≥ 3, not hidden or pending). With it, every fact, plus `hidden` and `pending` |
| POST | `/api/optin` | body `{person_id, hide:[fact_id…]}`. Sets `opted_in`, hides those edges, persists to `data/optins.json`, issues a random token stored server-side and set as an httpOnly cookie `rf_token` (SameSite=Lax), and records an event. Without the person's own `rf_token`, saved hides are kept (the union with `hide`) and facts not in the public checklist become `pending`; only the authenticated owner can un-hide. Returns `{ok, person}` |
| POST | `/api/optout` | clears the cookie's person: `opted_in=false` and removed from optins.json |
| GET | `/api/me` | the cookie's person or 401 |
| POST | `/api/me/facts` | the cookie's person (401 otherwise) reviews their facts: body `{hide:[fact_id…], show:[fact_id…]}`. `show` approves pending facts and un-hides hidden ones. Returns the private `/api/person/{id}/facts` list |
| GET | `/api/fact/{id}/people` | the privacy rule 2 check (403 otherwise). Returns `{people:[{name, avatar, linkedin_url}], hidden_count}` |

Keep tokens in `data/optins.json` as a SHA-256 hash so restarts don't log people out. Use parameterized Cypher everywhere; labels and relationship types come only from the code's own fixed table.

## Frontend

**`static/screen.html`, the rotating screen.** It is an exact copy of the approved `../room-facts.html`, with only the data plumbing changed (the user's decision, Oct 24). Keep the visuals, the controls, the 3D view and the locations as they are.
- Swap the hardcoded facts `F` for `/api/facts` (poll every 15 s). Every location rotates through all live facts, each starting at a different offset.
- The ticker comes from `/api/stats` plus `/api/events` (poll every 5 s).
- Give each fact its own QR, encoding `{public_base_url}/m?f={fact_id}` (from `/api/config`), with the existing qrcode-generator styling.
- `?mock=1` keeps the original sample data. Live mode with no facts shows a "Scan to join Room Facts" face.

**`static/m.html`, the phone page.** Mobile-first, the same palette, large tap targets, no framework; vanilla JS is fine.
1. `/m?f=<id>` shows the fact big and its path as chips (`You → STUDIED_AT → UC Berkeley ← 3 others`). Without `f`, show a generic intro.
2. "Is this you?" leads to a name search box with debounced `/api/people/search` and avatar rows.
3. Pick a person to see a confirm card (avatar, name, `linkedin.com/in/<slug>`) with "Yes, that's me" and "Not me".
4. "Your facts" lists `/api/person/{id}/facts` as checkboxes, all checked, with the note "Uncheck anything that's wrong. It won't count." Then the button "Opt in and see who else".
5. After `POST /api/optin`, show for the scanned fact (or each of their eligible facts if no `f`) the opted-in co-holders from `/api/fact/{id}/people`, with a LinkedIn link and "+{hidden_count} haven't opted in yet". Add a "Leave Room Facts" button that calls `/api/optout`.
6. If `/api/me` already works, skip straight to step 5.
7. Step 5 also shows "Review your facts": the full private list with a checkbox each (pending and hidden unchecked) and "Save my facts", which calls `POST /api/me/facts`.

## Verification

- `pytest -q` passes: normalization (aliases, suffix stripping, slugs, junk dropping, city mapping) and a privacy test on the fixture graph. The privacy test checks that no public endpoint returns a name or a fact with `n < 3`, and that `/people` returns 403 without a token. Use FalkorDB if it's reachable, and skip the DB tests with a clear message if it isn't.
- `python build_graph.py --luma tests/fixtures/luma_sample.json --linkedin tests/fixtures/linkedin_sample.json --graph roomfacts_test` works. With no args it uses `data/`.
- `README.md` covers the run steps (docker, build_graph, server, ngrok with `PUBLIC_BASE_URL`), a 90-second stage demo script, and `demo_queries.cypher` (5–8 queries to paste into the FalkorDB Browser that show the graph and a rare-fact path).
