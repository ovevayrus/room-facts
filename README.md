# Room Facts

Rare, anonymous overlaps among event guests on rotating venue screens, backed by a FalkorDB graph. Scan a fact's QR code to opt in and meet the others who share it.

**Continuing this project in another tool?** Start with [HANDOFF.md](HANDOFF.md).

## How changes land

Branch, then open a PR. CI runs pytest against a FalkorDB service plus a secrets and personal-data guard. Qodo Code Review comments on the PR, and you merge once it's green. Run `git config core.hooksPath .githooks` once per clone to get the same guard and tests locally before each commit and push.

Room Facts turns Luma registrations and optional LinkedIn enrichment into anonymous, rare overlap facts. FalkorDB stores the graph; FastAPI serves the screen and phone API.

## Run

1. Start FalkorDB with Browser: `docker run -d --name roomfacts-db -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest`. Open `http://localhost:3000` for the Browser.
2. Install the Python packages: `pip install falkordb==1.8.* fastapi uvicorn requests httpx pytest`.
3. Build the graph: `python build_graph.py`. It reads `data/luma_guests.json` and, if present, `data/linkedin_raw.json`. When LinkedIn is absent, all Luma guests are still loaded. To try synthetic data, run `python build_graph.py --luma tests/fixtures/luma_sample.json --linkedin tests/fixtures/linkedin_sample.json --graph roomfacts_test`.
4. Start the API: `python server.py`. Open `http://localhost:8000/screen` and `http://localhost:8000/m`. Set `GRAPH=roomfacts_test` before starting if using the sample graph.
5. For phones at the venue, start `ngrok http 8000` and set `PUBLIC_BASE_URL` to the resulting HTTPS URL before starting the API. This value is placed in QR codes through `/api/config`.

Optional environment variables: `FALKOR_HOST` (default `localhost`), `FALKOR_PORT` (default `6379`), `GRAPH` (default `roomfacts`), `MIN_N` (default `3`), `MAX_N` (default `12`), and `PUBLIC_BASE_URL`. The screen fact feed is cached for five seconds. Rebuild after the LinkedIn export arrives.

Opt-in state and SHA-256 token hashes are stored in `data/optins.json`. The file is created by the server on first opt-in and replayed by `build_graph.py` after every rebuild. Keep it on durable storage and restrict access to it. A user can opt out from the phone page.

## Verify

Run `pytest -q`. Pure normalization and fact selection tests run offline; database API tests skip with an explicit message when FalkorDB is unreachable. `demo_queries.cypher` contains Browser queries for graph inspection and rare path examples.
