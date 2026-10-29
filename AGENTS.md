# Room Facts

Read `NOTES.md` first: decisions, current state, what's next and the repo rules. `SPEC.md` is the API and privacy contract. `docs/` has the research and the data notes.

- Never commit `data/`, `.env`, scraped files or secrets; `scripts/guard_commit.py` enforces this.
- Privacy rules in SPEC.md are hard requirements (counts only, k ≥ 3, names only to opted-in co-holders).
- Work on a branch and open a PR; CI runs pytest against FalkorDB and Qodo reviews it.
- Run `pytest -q` (needs FalkorDB on :6379 for the DB tests: `docker run -d -p 6379:6379 falkordb/falkordb:latest`).
