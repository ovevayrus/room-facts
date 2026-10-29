# Build notes

What I decided while building Room Facts, where it ended up after the hackathon, and what I'd do next. The reasoning behind the idea itself is in [docs/how-i-found-the-problem.md](docs/how-i-found-the-problem.md).

## Decisions

1. Screens show counts only, never names. Public fact feeds exclude groups smaller than 3.
2. The QR code opens the phone page. You pick your name, check your facts and opt in. After that you see every other opted-in person you share a visible fact with, even for facts fewer than 3 people share, because both of you chose to be visible. The list refreshes every 15 seconds.
3. I kept the screen design from my original mockup and only wired in the live data. No time to redesign on build day, and I liked it.
4. Data comes from the Luma guest list plus Bright Data scrapers, matched on the LinkedIn, X and Instagram handles people gave Luma. GitHub accounts only count with evidence: a published link, the GitHub profile listing their LinkedIn or X, the same website, or the same name plus location.
5. The OpenAI key is used for one thing at runtime: helping someone find their own name when the plain search misses (typos, nicknames, names in a different order). It doesn't write anything people see. I considered generated "why you two should talk" lines and left them out for the demo.
6. The repo is public. `main` is protected: PRs only, green CI, Qodo reviews every PR.
7. Hosting was my laptop plus ngrok. I expected 50 opt-ins at most, so I didn't set up anything bigger.
8. You choose your facts on the first scan. Confirming your profile opens a 10-minute review that only covers your own facts. It doesn't opt you in or show you anyone else. The final button shares only what you ticked. Anything that shows up later stays pending until you review it.
9. The fact checklist starts collapsed with everything available ticked. You can open it and untick things, on the first scan and again on the results page.
10. The checklist only shows facts that actually connect you to someone (at least one other opted-in person who hasn't hidden it), with how many people each one connects you to.
11. Rotation: the first live rotation was all 3s and 4s and broad facts like "studied in the UK". I wanted a spread of group sizes and more specific facts (the actual university, not the country). Country-level facts are out of the rotation now. See [docs/rotation-variety.md](docs/rotation-variety.md).

## Where it ended up (Oct 24)

Data, local only and never in git: 616 guests, 514 LinkedIn profiles, 493 company and school pages, 358 X profiles, 1,277 LinkedIn posts from 2026, 208 Instagram profiles, 220 Crunchbase records (I only used the ones whose website matched the company's LinkedIn page) and 174 GitHub accounts. That used up most of the Bright Data credit.

The graph has People linked to School, Company, City, Country, Language, Cert/Issuer, Org, Cause, Industry, Year, OrgKind, Hashtag, Repo, GitHubOrg, ProgLang and Badge nodes. About 185 facts made it into the rotation, a mix of sizes. A few real ones: 18 studied at UC Berkeley, 10 work at Sequoia-backed companies, 17 work at a stealth startup, 24 posted #sftechweek. The data quirks per source are in [docs/data-linkedin.md](docs/data-linkedin.md) and [docs/data-more-sources.md](docs/data-more-sources.md).

For the stage demo I seeded some opt-ins locally so the phone page had people to show. That seed isn't in the repo.

Merged: #1 (CI fix), #3 (Instagram, Crunchbase investors and funding stage), #4 (rotation variety), #8 (phone loading states), #9 (opt-in connections, name lookup, `/monitor`), #11 (reading past FalkorDB's result cap), #12 (choosing facts on the first scan).

Still open: #2 (drop the stage demo from the README, which this README already does), #5 (`add_guest.py` for people not on the Luma list), #6 (no certifications in the phone lists), #7 (broader overlaps and field of study; it overlaps with `/api/connections`, so pick one) and #10 (draft notes on the participant enrichment).

Qodo caught real bugs. On PR #4 alone it found that `/api/person/{id}/facts` returned hidden and under-3 facts without auth, that re-opting in without your cookie wiped your saved hides, and that facts you'd never seen counted after opt-in. All fixed, with tests in `tests/test_qodo_review.py`.

## Next

1. Prove identity at opt-in. Right now you pick your own name and nothing checks it. A one-time code from the Luma ticket is the cheapest fix.
2. Rate limit `/api/people/search` and require a longer query to make bulk guest-list lookups harder.
3. Swap ngrok for a Cloudflare tunnel. ngrok's free tier shows a warning page on phones first.
4. Let people add their own facts in plain text ("I used to be a nurse"). An LLM maps it onto an existing node if there is one, and it only counts in groups of 3+.
5. Maybe a one-line "why you two should talk" for opted-in people, built only from the graph path between them.
6. Per-location screens driven by check-ins, which the mockup already has room for.
7. Talk to the people I couldn't test with: developers who hate networking, and an organizer who'd have to run this.

## Rules I stick to on this repo

- Never commit `data/`, `.env`, raw scrapes, guest names, or keys and tokens (that includes the Luma `?tk=` key). The pre-commit hook and CI (`scripts/guard_commit.py`) block these. Don't loosen the guard to get a push through.
- The privacy rules in SPEC.md remain the intended contract. Venue screens and public fact feeds show aggregate groups of 3 or more; connection lists require mutual opt-in. Name search and profile confirmation expose guest names before opt-in, and identity remains self-claimed. Those gaps still need hardening.
- Ignore sensitive scraped fields even if they show up again: birth dates, emails, pronouns, post text, tagged people, `activity`, `similar_profiles`.
- In Cypher, labels and relationship types only come from the fixed tables in the code. Values are always parameters.
- Small PRs. Every new fact kind gets a test.
- Leave `static/screen.html` looking the way it does unless there's a reason to change it.
