# Room Facts

Screens around a conference venue that show rare things the people in the room have in common, one at a time: "3 people here speak Romanian", "7 people here have contributed to nousresearch/hermes-agent". Each one is just a count. No names on the screen.

If one of them is you, scan the QR code under it, check which of your facts are right, and opt in. Then you can see the other people who opted in and share something with you, and go find them.

I built this in a day at [Patch the Conference](https://wemakedevs.org/hackathons/ptc) (Oct 24, 2026, San Francisco) for the FalkorDB track. It ran on the real guest list for the event, 616 people.

## Why

Before the hackathon I interviewed people who go to conferences, and read a lot of Hacker News threads about conference networking. The same things kept coming up:

- The meetings that led somewhere came from something people already shared (same school, same town, a friend of a friend, a peer vouching for something), not from being matched with a stranger on interests. One person told me they'd *rather* meet people from completely different backgrounds. The surprising person was the best part of their day.
- People open conversations with tiny things, like a lanyard or "when's the next talk?"
- Messages sent through the conference app go nowhere, because the other person isn't in the app.
- Developers on HN hate cold networking and flip their badges so the QR code doesn't get them spammed.

So I wanted something that tells you there are people here you share something unusual with, gives you an opener, doesn't need an app, and never puts anyone's name on a wall.

The longer version, with the interviews, what I took from them and the ideas I threw away, is in [docs/how-i-found-the-problem.md](docs/how-i-found-the-problem.md).

## How it works

```
Luma guest list ──► fetch_luma.py ──► data/luma_guests.json
LinkedIn profiles ─► enrich_linkedin.py (Bright Data) ─► data/linkedin_raw.json
Company/school pages, X, LinkedIn posts, Instagram, Crunchbase ─► bd_dataset.py (Bright Data)
GitHub accounts ──► enrich_github.py (GitHub GraphQL)
                         │
build_graph.py + normalize.py ──► FalkorDB graph
                         │
facts.py   picks facts with 3+ people and mixes group sizes
                         │
server.py ──► /screen   rotating screens
          ├─► /monitor  one-screen version (click or space for the next fact)
          └─► /m        phone opt-in page, where the QR codes point
```

Luma gives names plus the LinkedIn, X and Instagram handles people entered when they registered. Bright Data scrapes the public profiles behind those handles. GitHub accounts are only used when there's real evidence they belong to the guest (a published link, the GitHub profile listing their LinkedIn or X, the same website, or the same name and location).

A fact is a graph pattern. "People here work at companies backed by Sequoia" is `(p)-[:WORKED_AT]->(:Company)-[:BACKED_BY]->(:Investor)`. The phone page shows that path, so you can see why you were counted.

My first version showed rare facts first, and the screens ended up showing "3 people here…" over and over, mostly with broad stuff like "studied in the UK". Now `facts.py` cycles small, medium and large groups and prefers specific things (a particular university, a repo) over broad ones. [docs/rotation-variety.md](docs/rotation-variety.md) has the details.

### Privacy

The rules I didn't bend on:

- Screens and every public endpoint return counts only, and only for groups of 3 or more.
- You only see names after you opt in, and only of other opted-in people who share a fact with you.
- You can untick anything that's wrong or that you don't want counted. Facts you never got to review don't count anywhere.
- Scraped data never goes in git. `scripts/guard_commit.py` runs as a pre-commit hook and in CI to block `data/`, raw scrapes and anything that looks like a key.

[SPEC.md](SPEC.md) has the full API and the exact privacy rules.

## Run it

1. Start FalkorDB: `docker run -d --name roomfacts-db -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest`. The FalkorDB Browser is on `http://localhost:3000`.
2. `pip install -r requirements.txt`
3. Build the graph: `python build_graph.py`. It reads `data/luma_guests.json` plus whichever scraped files are in `data/`. The `data/` folder isn't in this repo since it's scraped personal data, so to try it without that, use the synthetic fixtures:
   `python build_graph.py --luma tests/fixtures/luma_sample.json --linkedin tests/fixtures/linkedin_sample.json --graph roomfacts_test`
4. Start the API: `python server.py` (set `GRAPH=roomfacts_test` first if you used the fixtures). Open `http://localhost:8000/screen` and `http://localhost:8000/m`.
5. For phones at the venue, run `ngrok http 8000` and set `PUBLIC_BASE_URL` to the HTTPS URL before starting the API. That's the address the QR codes use.

Other environment variables: `FALKOR_HOST` (default `localhost`), `FALKOR_PORT` (`6379`), `GRAPH` (`roomfacts`), `MIN_N` (`3`), `MAX_N` (`25`), and `OPENAI_API_KEY` in `.env`, which is optional and only used to help people find their own name when the plain search misses.

Opt-ins are saved to `data/optins.json` (token hashes, not tokens) and replayed after every graph rebuild. Keep that file somewhere durable and private.

To rebuild the real data you need your own Luma ticket key for the event (`python fetch_luma.py <event_api_id> <ticket_key>`), a Bright Data key in `BRIGHTDATA_API_KEY`, and `gh` logged in for the GitHub step.

## Tests

`pytest -q`. The normalization and fact selection tests run offline. The database tests need FalkorDB on port 6379 and skip with a message if it isn't there.

`demo_queries.cypher` has queries to paste into the FalkorDB Browser to look at the graph and at a rare-fact path.

## Making changes

Branch, then open a PR. CI runs pytest against a FalkorDB service plus the data guard, and Qodo reviews the PR. Run `git config core.hooksPath .githooks` once after cloning to get the same checks locally before each commit and push.

## Known gaps

- Opt-in is self-claimed. You pick your own name and nothing proves it's you. A one-time code from your Luma ticket would fix that.
- Name search should be rate limited and need a longer query, so nobody can page through the guest list.
- ngrok's free tier shows a warning page on phones before the site loads. A Cloudflare tunnel avoids it.
- It ran on my laptop for the demo. Fine for ~50 opt-ins, not for a real 3,000-person conference.

[NOTES.md](NOTES.md) has the decisions I made during the build and what I'd do next.

## How it was built

One day, with Claude Code and Codex writing a lot of the code. The research, the privacy rules and the product decisions were mine. Qodo reviewed every PR and caught a few real privacy bugs along the way (see `tests/test_qodo_review.py`).
