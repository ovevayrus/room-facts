# Run Room Facts with your own data

Room Facts builds a graph from an event registration list and optional profile exports. The public repository includes synthetic test fixtures. The owner's event dataset is deliberately absent: do not copy it into a clone, screenshot, issue, test fixture, or pull request.

Start with the synthetic walkthrough below. Use an event export only when its owner has agreed to its use and the intended audience understands the phone flow. Confirming a name is self-identification, not proof of ownership. This guide preserves that demo behavior.

## Try the existing synthetic fixtures

Use a fresh clone with no private `data/` folder. Install the reviewed requirements in a virtual environment:

```sh
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -r requirements.txt
mkdir ../roomfacts-demo
```

The directory beside the clone is for disposable local state; it is not a dataset to commit. In PowerShell, set:

```powershell
$env:GRAPH = 'roomfacts_demo'
$env:OPTINS_PATH = '../roomfacts-demo/optins.json'
```

In a POSIX shell, use:

```sh
export GRAPH=roomfacts_demo
export OPTINS_PATH=../roomfacts-demo/optins.json
```

Set these variables **before** both graph construction and the API start. `OPTINS_PATH` holds participant preferences and hashed session tokens; keep it private even in a demo.

Start a separate local FalkorDB instance if one is not already reserved for this demo. The explicit loopback mappings keep its database and Browser off public network interfaces:

```sh
docker run -d --name roomfacts-demo-db -p 127.0.0.1:6379:6379 -p 127.0.0.1:3000:3000 falkordb/falkordb:latest
```

If either port or that container name is already used, choose a separate mapping/name rather than stopping an existing database. Set `FALKOR_PORT` to any alternate database host port. The image tag here matches the existing local demo instructions; pin and review an image version for a maintained installation.

Build only the fixture graph. **Rebuild deletes and replaces the selected graph.** Check that `--graph` names a disposable demo graph, never an existing event graph:

```sh
python build_graph.py --luma tests/fixtures/luma_sample.json --linkedin tests/fixtures/linkedin_sample.json --orgs ../roomfacts-demo/no-orgs.json --x ../roomfacts-demo/no-x.json --li-posts ../roomfacts-demo/no-posts.json --github ../roomfacts-demo/no-github.json --instagram ../roomfacts-demo/no-instagram.json --crunchbase ../roomfacts-demo/no-crunchbase.json --graph roomfacts_demo
```

The optional `no-*.json` paths intentionally do not exist. The builder skips them. Passing every optional source explicitly prevents a private `data/*_raw.json` export from being included accidentally in a fixture demo. Do not create those files with real data to make the example run.

Start the API on loopback:

```sh
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/screen` and `http://127.0.0.1:8000/m`. Use names from the fixture file, review the displayed facts, opt in, inspect overlaps and leave. The graph Browser is at `http://127.0.0.1:3000`; `demo_queries.cypher` contains examples. The screen's `?mock=1` mode shows its original visual sample and is not evidence that a dataset loaded.

This walkthrough does not scrape profiles, use an OpenAI key, or open a public tunnel. Name search works without optional model-assisted matching.

## Input formats and matching

The existing synthetic files are the best small examples. Do not replace them with event exports.

| Input | JSON shape and important fields | How Room Facts uses it |
|---|---|---|
| Registration list (`--luma`) | List of objects with stable `api_id`, a display `name` or `first_name`/`last_name`, and optional `linkedin_handle`, avatar and social fields. | Creates people. The registration ID is the stable person ID; keep IDs unique. Missing LinkedIn data does not remove a registered person. |
| LinkedIn profiles (`--linkedin`) | List of records; profile slug in `linkedin_id` or `input.url`/`input_url`. Optional education, experience, city, country and related fields can be null. | Joins to the registration LinkedIn slug case-insensitively. Invalid/company-only handles and scrape-error records do not establish a person match. |
| Organization, X, post, Instagram and Crunchbase exports | Optional lists, each with the existing source-specific shape. | Adds richer facts. See `DATA_NOTES.md`, `DATA_NOTES_2.md` and `DATA_NOTES_3.md` for the fields and matching caveats; do not assume every export shares one schema. |
| GitHub export (`--github`) | Optional object keyed by registration person ID, containing matched account evidence. | Adds repository/language/organization facts. A same-name account alone is not a verified match. |
| Preference/session state (`OPTINS_PATH`) | Object keyed by person ID, with selected/hidden/pending facts and token hashes. | Replays supported opt-in state after a rebuild. It is private application state, not a public dataset or example export. |

Normalization and fact selection are separate stages. `normalize.py` handles entity IDs, aliases and malformed/missing values. `build_graph.py` loads people/entities/relationships; `facts.py` selects display facts. Public screen counts require at least three holders; catalog selection also considers group size and duplicate holder sets. Missing, hidden and pending facts can change counts, so do not expect raw export row counts to equal screen facts.

When checking a new adapter, first use a small fictional dataset outside the repository. Inspect unmatched IDs and source errors, confirm joins using evidence rather than names alone, then inspect a few graph paths. Do not print full attendee rows, export credentials, ticket URLs or session cookies in debug output. Screenshots and PR examples must use the existing synthetic fixtures or clearly labelled fictional records.

## Keep an event dataset outside the clone

You do not need to distribute the original owner's dataset to run or contribute to Room Facts. Obtain your own authorized export independently. Keep it in a separate private directory and pass absolute paths through the corresponding builder flags; keep preference/session state outside the clone too. Do not move an event export into `tests/fixtures` or force-add an ignored `data/` directory.

Before rebuilding a real event graph, record the current graph name, source files and private state path, and make an operator-approved backup. Rebuild is destructive for that selected graph. Stable person IDs and the matching preference file matter; do not replay another event's state into a new guest list. Review the current replay behavior on synthetic data before relying on privacy-state preservation for a real event.

The repository's `.gitignore` excludes `data/` and `.env`; `scripts/guard_commit.py` rejects data and secret paths. These are useful checks, not permission to put a private export in another tracked folder. Before any commit, inspect `git status --short` and run:

```sh
python scripts/guard_commit.py
```

For a check of all currently tracked files, use `python scripts/guard_commit.py --all`. Do not alter the guard merely to accept a dataset.

## Phone access and privacy boundaries

The venue screen displays aggregate facts. The phone flow offers person search and profile confirmation, then selected-fact sharing and introductions. **Selecting a name is a claim, not authentication.** Review cookies limit actions but do not establish that a visitor owns the selected profile. Use fictional data for an unrestricted public demo; decide who may reach an event installation before using personal records.

Hiding a fact and leaving introductions are different operations. Leaving is not a promise that the underlying source record, graph, backups or every aggregate contribution has been erased. Check these behaviors against the current `SPEC.md` and synthetic tests before offering a privacy guarantee. Restrict the graph Browser and database to operators.

If you separately decide to share a demo with phones, set `PUBLIC_BASE_URL` to that demo's HTTPS address before starting the server; QR codes use this value. A tunnel publishes whichever routes it forwards and does not verify an attendee's identity. Do not expose a private graph/browser or reuse a production account/key to make a public demo. Public deployment and new data collection are separate operator decisions.

## Checks and common problems

- `pytest -q` runs the existing suite. Database tests need a disposable FalkorDB and explicitly skip when unavailable; a skip is not a passed database check.
- An empty screen can mean no eligible overlap, the wrong `GRAPH`, missing optional enrichment, or no graph connection. Start with the fixture graph and compare `GRAPH` in both processes.
- If a registration person is present but unmatched, check the stable ID and profile slug, not just the name. Source error/null records are expected inputs.
- Wrong QR targets usually mean `PUBLIC_BASE_URL` was set after server startup or points at another demo.
- Keep screenshots, raw exports, provider activity and troubleshooting logs private unless you have inspected and sanitized them. Share code and fictional reproductions in a PR.
