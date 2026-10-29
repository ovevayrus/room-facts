# Room Facts

Room Facts puts unusual things conference guests have in common on screens around the venue. A screen might say "3 people here speak Romanian" or "7 people here have contributed to nousresearch/hermes-agent". It shows a count, with a QR code underneath.

Scan it, find your profile, review your facts, and opt in. The phone page then shows other opted-in people you share something with, along with the connection between you.

I built the prototype in a day at Patch the Conference in San Francisco on October 24, 2026, for the FalkorDB track. The demo used the event's real registration list of 616 guests.

## Why I built it

I started with interviews about conferences, before choosing what to build. A short Google Form helped me find people to talk to, and I ended up doing three phone calls: a physician, an independent pharmacy owner, and someone working in insurance. I asked about their last conference, how conversations started, and what happened afterwards.

The pharmacy owner's stories stuck with me. A seatmate on a flight turned out to own the pharmacy they had nearly bought. At another event, a conversation led to someone whose aunt lived in their town. They were comfortable approaching strangers; the interesting part was finding the connection neither person knew about.

The insurance attendee deliberately used small questions about the schedule to start conversations. They preferred meeting people from different backgrounds to being matched by interests. The physician described unanswered messages in a conference app and introductions that happened through people they already knew.

That gave me a direction: put a shared detail somewhere people can notice it, and give them a small reason to say hello. A venue screen doesn't ask anyone to install an app or wait for a match. The QR code gives someone who is interested a next step.

I also read Hacker News discussions about conference networking, where some commenters described awkward introductions and unwanted badge scans. That helped shape the opt-in flow, but it wasn't a substitute for interviewing developers. All three people I spoke to were confident networkers outside tech. I still need to test whether this helps the less confident people I had in mind.

The [research notes](docs/how-i-found-the-problem.md) cover the calls, the ideas I dropped, and what I still don't know.

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

## Data and privacy

The screens show aggregate facts about groups of at least three guests. Names stay off the venue screens. Connection cards on the phone require opt-in from both people and a shared visible fact; those private connections can include groups smaller than three.

The initial aggregate counts include registered guests who haven't opted in. When someone joins, they choose which reviewed facts to share. Unchecked facts are hidden, and unreviewed facts stay pending until approved. Opt-in controls the connection list and saved fact choices; it isn't prior consent from everyone counted on a screen.

The demo also lets people search guest names and confirm a profile before opting in. Picking a name doesn't prove ownership. Identity verification and stronger name-search restrictions still need work.

Raw exports stay out of Git. `scripts/guard_commit.py` checks for private data paths and common secret formats, both locally and in CI. Opt-in state lives in `data/optins.json`, with token hashes rather than raw tokens, and survives graph rebuilds. Keep that file on durable, private storage.

[SPEC.md](SPEC.md) documents the API and intended privacy rules. The limitations above describe the current demo.

## Try it locally

Use Python 3.13 and Docker. A fresh clone includes synthetic guests, so you can try it without the event's private exports or API keys.

```bash
git clone https://github.com/ovevayrus/room-facts.git
cd room-facts
python -m pip install -r requirements.txt
docker run -d --name roomfacts-db -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
python build_graph.py --luma tests/fixtures/luma_sample.json --linkedin tests/fixtures/linkedin_sample.json --graph roomfacts_test
```

Start the server against that graph. In PowerShell:

```powershell
$env:GRAPH = "roomfacts_test"
python server.py
```

On macOS or Linux:

```bash
GRAPH=roomfacts_test python server.py
```

Open the [venue screens](http://localhost:8000/screen), [single-screen view](http://localhost:8000/monitor), or [phone page](http://localhost:8000/m). The [FalkorDB Browser](http://localhost:3000) lets you inspect the graph; `demo_queries.cypher` has example queries.

The fixture graph starts without seeded opt-ins, so the phone's connection list and fact chooser may be empty. For a populated interface preview, use [screen mock mode](http://localhost:8000/screen?mock=1) and [phone mock mode](http://localhost:8000/m?mock=1). Those use sample UI data.

For phones on another network, run `ngrok http 8000` in another terminal. Set `PUBLIC_BASE_URL` to its HTTPS URL before starting the server; that's the address the QR codes use.

Other settings: `FALKOR_HOST` defaults to `localhost`, `FALKOR_PORT` to `6379`, and `GRAPH` to `roomfacts`. `MIN_N` defaults to `3` and cannot go lower. `MAX_N` defaults to `25`; most fact kinds keep a cap of `12`, with selected kinds allowed up to `25`.

With your own authorized exports in `data/`, `python build_graph.py` builds the default graph. The collection scripts need event access for Luma, `BRIGHTDATA_API_KEY` for Bright Data, and a signed-in `gh` for GitHub. None of those are needed for the fixture demo. An optional `OPENAI_API_KEY` in the environment or `.env` helps with name lookup when plain search misses; it doesn't generate the graph facts.

## Tests

Run `pytest -q` and `python scripts/guard_commit.py --all`. The normalization and fact selection tests run offline. The database tests need FalkorDB on port 6379 and skip with a message if it isn't there.

`demo_queries.cypher` has queries to paste into the FalkorDB Browser to look at the graph and at a rare-fact path.

## Making changes

Branch, then open a PR. CI runs pytest against a FalkorDB service plus the data guard, and Qodo reviews the PR. Run `git config core.hooksPath .githooks` once after cloning to get the same checks locally before each commit and push.

## Known gaps

- Opt-in is self-claimed. You pick your own name and nothing proves it's you. A one-time code from your Luma ticket would fix that.
- Name search needs rate limits and a longer minimum query to make bulk guest-list lookups harder.
- ngrok's free tier shows a warning page on phones before the site loads. A Cloudflare tunnel avoids it.
- It ran on my laptop through ngrok, intended for roughly 50 demo opt-ins. I haven't load tested it for a larger event.
- The graph describes registrations, rather than checking who is physically in the room.

I want to test the idea with developers who find networking difficult, and with an organizer who would have to run it. The interviews helped me choose a direction; they haven't established that people will scan or meet because of it.

[NOTES.md](NOTES.md) has the decisions I made during the build and what I'd do next.

## How I used AI

Claude Code and Codex wrote a lot of the implementation. I did the interviews, chose the problem, and made the product decisions, including the screen format and fact-review flow. Qodo's reviews caught privacy bugs that needed fixes; `tests/test_qodo_review.py` records those regressions.
