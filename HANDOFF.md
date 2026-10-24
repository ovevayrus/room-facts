# Room Facts: handoff for the next assistant

Use this file to continue the project from **ChatGPT, Codex (cloud or CLI), or a Claude Code cloud session** if the current Claude session runs out. It is the single source of truth for status and decisions. Update the **Status** and **Next steps** sections whenever you finish something.

## Starter prompt (paste this first)

> You are taking over a hackathon project mid-build. The repo is `github.com/ovevayrus/room-facts`. Read `HANDOFF.md` fully, then `SPEC.md` (the contract and the privacy rules), `DATA_NOTES.md` and `DATA_NOTES_2.md` (data quirks and the fact kinds). Follow the "Rules for whoever continues" section strictly, especially the privacy rules and never committing `data/` or secrets. Start by telling me, in 5 bullets, what the project does, its current status, and what you'd do next from "Next steps". Then wait for me to pick. Work on a branch and open a PR for every change; Qodo reviews PRs automatically.
>
> (ChatGPT: connect GitHub, or upload HANDOFF.md, SPEC.md, DATA_NOTES*.md and the file you're changing. Codex cloud: point a task at this repo. Claude Code cloud session: start it on this repo; CLAUDE.md points here.)

## What it is

**Room Facts** is for the Patch the Conference hackathon (Sat Oct 24 2026, Bright Data office in SF; submit by 5:30 pm, on-stage demos at 5:30–6:30). We're entering the **FalkorDB track**. Its criteria: the graph is at the core, answers are explainable ("a path behind every answer"), it solves a real conference problem, and the demo runs live on stage.

The problem comes from user interviews. Valuable conference meetings come from *shared* connections (the same school, town or project), not interest-matching with strangers, and people delight in the *surprising* person. Room Facts therefore shows **rare overlaps** within the crowd on rotating venue screens, as anonymous counts: "7 people here contributed to NousResearch/hermes-agent". Each fact has a QR code. Scanning it opens a phone page where you find yourself, confirm your facts, and opt in. You then see the *other opted-in* people who share that fact.

## Architecture

```
Luma guest list ──► fetch_luma.py ──► data/luma_guests.json        (616 guests, socials)
LinkedIn profiles ─► enrich_linkedin.py (Bright Data) ─► data/linkedin_raw.json (514)
Company/school pages, X, LinkedIn posts, Instagram, Crunchbase ─► bd_dataset.py (Bright Data) ─► data/*_raw.json
GitHub accounts ──► enrich_github.py (GitHub GraphQL, gh token) ─► data/github_raw.json (174 matched)
                         │
                         ▼
build_graph.py + normalize.py ──► FalkorDB graph "roomfacts" (docker, :6379; Browser :3000)
                         │
facts.py (rare-fact catalog: k ≥ 3, ≤ 12, dedupe, round-robin rotation)
                         │
server.py (FastAPI :8000) ──► /screen  static/screen.html  (the approved rotating-screen design, live data)
                          └─► /m       static/m.html       (phone opt-in)  ← QR codes point here via PUBLIC_BASE_URL (ngrok)
```

- **Graph**: `(:Person)` linked to School, Company, City, Country, Language, Cert→Issuer, Org, Cause, Industry, Year, OrgKind, Hashtag, Repo, GitHubOrg, ProgLang, Badge. Two-hop path kinds include `(p)-[:WORKED_AT]->(:Company)-[:IN_INDUSTRY]->(:Industry)` and `(p)-[:STUDIED_AT]->(:School)-[:LOCATED_IN]->(:Country)`. The full kind list and its wording are in `facts.py` and DATA_NOTES_2.md.
- **API**: SPEC.md lists it (`/api/facts`, `/api/fact/{id}`, `/api/stats`, `/api/events`, `/api/people/search`, `/api/person/{id}[/facts]`, `/api/optin`, `/api/optout`, `/api/me`, `/api/fact/{id}/people`).
- **Opt-in state**: `data/optins.json` (token hashes), replayed after every rebuild.

## Run it locally

```bash
docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
pip install -r requirements.txt
python build_graph.py            # needs data/ (not in git — see below)
PUBLIC_BASE_URL=https://<your-ngrok-domain> python server.py
ngrok http 8000                  # phones reach /m through this; QR codes use PUBLIC_BASE_URL
pytest -q                        # 27 tests; DB tests need FalkorDB on :6379
git config core.hooksPath .githooks   # once per clone: secret/personal-data guard + tests before push
```

**The data is not in the repo, on purpose.** It's scraped personal data. A cloud session or a fresh clone can work on the code and run the tests, which use synthetic fixtures. To rebuild the real graph, you need the `data/` folder from the owner's laptop, or a re-scrape:
- `fetch_luma.py <event_api_id> <ticket_key>`: the ticket key is the `?tk=` value of the owner's Luma link. Never commit it.
- The Bright Data scripts read `BRIGHTDATA_API_KEY` from the environment (`bd_key.py`).
- `enrich_github.py` uses `gh auth token`.

## Decisions the owner made (don't relitigate)

1. **The screens show counts only.** Names never appear on screens. The k ≥ 3 minimum applies everywhere public.
2. **The QR code opens the phone opt-in page.** People pick their name, confirm or uncheck their facts, and opt in. They then see the other opted-in co-holders.
3. **The rotating-screen design is approved.** `static/screen.html` is the owner's `room-facts.html` with only the data plumbing changed. Don't redesign it.
4. **Data comes from the Luma guest list plus Bright Data scrapers**, matched by the LinkedIn/X/Instagram handles guests gave Luma. GitHub accounts are accepted only with evidence: a published link, the GitHub profile listing their LinkedIn or X, the same website, or the same name plus location.
5. **Codex development runs on the owner's ChatGPT subscription** (`gpt-6-sol`). The **OpenAI API key is reserved for runtime features** in the app (see Next steps). It belongs in `.env` (gitignored), which the owner creates.
6. **The repo is public.** Qodo Code Review reviews PRs (`.pr_agent.toml`). `main` is protected: PRs plus green CI only.
7. **Hosting is the owner's laptop plus ngrok** (decided Oct 24, about 12:10; at most ~50 opt-ins expected). FalkorDB runs in Docker, `server.py` on :8000, and ngrok exposes it. Don't move to hosted infrastructure unless asked.
8. **After opt-in, people see overlap cards** (decided Oct 24, about 12:10): every other *opted-in* person who shares a non-hidden fact with them, with name, LinkedIn and the shared facts. It's mutual opt-in only. This is being implemented as `/api/connections` on `feat/opt-in-connect` (see Next steps 2).

## Status (update this; last updated Oct 24, about 14:00)

- **Data** (local `data/`, never in git): 616 guests; 514 LinkedIn profiles; 493 company and school pages; 358 X profiles; 1,277 LinkedIn posts (2026); 208 Instagram profiles; 220 Crunchbase records (only website-verified matches are used); 174 GitHub accounts. The Bright Data credit is mostly used.
- **The graph** builds from every source. On the PR #4 branch there are 185 facts in rotation with mixed sizes (99 small, 57 medium, 29 large). For example: 18 studied at UC Berkeley, 10 work at Sequoia-backed companies, 17 at a stealth startup, 24 posted #sftechweek. Country-level facts are out of the rotation, at the owner's request.
- **Merged to `main`:** #1 (CI `pytest.ini`), #3 (Instagram, Crunchbase investors and funding stage, country names), #4 (rotation variety per DATA_NOTES_3.md, plus the opt-in privacy fixes below).
- **Open PRs:**
  - **#6** removes certifications from the phone fact lists (below).
  - **#5** `add_guest.py` adds people who aren't on the Luma list. Qodo has open findings (a full `enrich_linkedin.py` run overwrites added profiles, and company matching is by substring). The owner is adding guests locally instead.
  - **#2** (opened by the owner) drops the stage-demo script from the README. It touches README/HANDOFF/SPEC and may conflict with these docs.
- **Qodo's PR #4 findings, and the fixes:**
  1. `/api/person/{id}/facts` leaked hidden and sub-threshold facts unauthenticated. Now, without the person's own `rf_token`, it returns only their public (n ≥ 3, not hidden) facts.
  2. Dedup let study_country beat a school with the same holders. Tier-1 kinds now win.
  3. Hiding a combo hid its underlying edges. Combo hides are now stored per person.
  4. A re-opt-in without the owner's cookie cleared saved hides. Now saved hides only grow without `rf_token`; only the authenticated owner can un-hide.
  5. Facts not shown in the public checklist (sub-threshold ones) counted after opt-in without review. They're now saved as `pending` in optins.json and suppressed per fact (not by hiding edges, so path facts like industry keep their counts). The owner approves or hides them via `POST /api/me/facts` from a "Review your facts" card on m.html.
  6. A cookie-less re-opt-in made already-approved facts pending again. optins.json now keeps an `approved` list too.
  7. `/api/stats` counted schools and companies from raw edges, which included pending holders. It now counts from the catalog.
- **Certifications are off the phone fact lists** (owner request: too generic). The checklist and the review card skip `cert` and `cert_issuer`. Because they're never shown, they never count for anyone who has opted in. `fact_catalog` enforces that from `p.opted_in`, so older approvals in optins.json don't matter, and `POST /api/me/facts` rejects them. They still rotate on the screens, counting only guests who haven't opted in.
- **Tested end to end in a browser:** the live screen with a QR per fact, and phone search → confirm → choose facts → opt in → see co-holders → opt out. Merged `main` was re-checked with the synthetic fixtures: a decoded screen QR, phone opt-in, the review card, and the screen's opted-in count and ticker event.
- **Local-only pieces** (not available to a cloud session): FalkorDB in Docker, the `data/` folder, the server (`python server.py` with `PUBLIC_BASE_URL` set to the owner's ngrok domain), the ngrok tunnel, the Codex plugin, and Bright Data scraping.

## Next steps (pick in order)

1. **Run merged `main` on the laptop:** `git pull`, `python build_graph.py`, restart `server.py` with `PUBLIC_BASE_URL`, then `python facts.py --preview 40` to eyeball the rotation and scan a QR with a phone. `feat/opt-in-connect` still has to merge `main` (see 2).
2. **Overlap cards (decision 8) are being built in a separate session** on branch `feat/opt-in-connect` (the worktree `../roomfacts-connect`). It adds `/api/connections` (every other opted-in person you share a visible fact with, refreshed every 15 s) and an OpenAI-assisted name lookup at opt-in (`assist.py`, key in `.env`). That session also runs the live laptop server behind ngrok. Don't build a second version. It branched from PR #3 before #4, so it will need to merge #4's `server.py` / `facts.py` / `m.html` changes when it opens its PR: the person-facts privacy rule, saved hides kept on a cookie-less re-opt-in, `pending` facts and `POST /api/me/facts`, and the rotation. `/api/connections` must use `fact["holders"]` (which already excludes hidden and pending people), never `all_holders`. Merge order: #3, then #4, then opt-in-connect.
3. **Demo prep:** rehearse the 90-second script in README.md. Have one audience member who holds a fact scan live (the owner's own facts are all under 3 holders). Open FalkorDB Browser with `demo_queries.cypher`.
3. **Privacy hardening before going public at the venue** (known gaps):
   - `/api/people/search` lets anyone with the URL enumerate guest names. Require ≥ 3 characters, rate-limit per IP, and return at most 5 results.
   - Opt-in has no identity check (anyone can pick anyone's name). A cheap fix: confirm by typing your own LinkedIn handle, or a one-time code shown on your Luma ticket.
   - `/api/person/{id}/facts` is unauthenticated.
   - ngrok's free tier shows a one-time "You are about to visit" page on phones. A Cloudflare tunnel avoids it.
4. **OpenAI-powered runtime features** (they use `OPENAI_API_KEY` from `.env`). Ideas the owner wants: when people scan, they can **add their own facts** in free text ("I used to be a nurse"). An LLM normalizes the text into graph entities (with an existing-node match), and it only counts toward k ≥ 3 groups. The model could also write a one-line "why you two should talk" for opted-in co-holders, grounded in the graph path.
5. Stretch: per-location screens (the `LOCATIONS` in screen.html) driven by check-ins.

## Rules for whoever continues

- **Never commit** `data/`, `.env`, raw scrape files, guest names, or keys and tokens (including the Luma `?tk=` key and the Bright Data token). The pre-commit hook and CI (`scripts/guard_commit.py`) enforce this; don't weaken them to get a push through.
- **Privacy rules 1–4 in SPEC.md are hard requirements.** Every public response is counts-only and k ≥ 3. Names come only from `/api/fact/{id}/people`, for an opted-in holder of that fact.
- **Ignore sensitive scraped fields** even if they reappear: birth dates, emails, pronouns, post text, tagged people, `activity`, `similar_profiles`.
- **Cypher**: labels and relationship types come only from the code's fixed tables; values are always parameters.
- **Workflow**: branch → PR → CI (pytest with a FalkorDB service, plus the guard) → Qodo review → merge. Keep PRs small. Add a test for every new fact kind.
- Keep `static/screen.html` visually unchanged unless the owner asks.
