# Rotation variety and niche facts

My note at 11:45, after watching the first live rotation:

> "The room facts are all showing only 3 and sometimes 4. Give me a range of different numbers of people for various different interesting facts, that would make people want to scan the QR code. Make it a bit more niche: instead of 'studied in the UK', be specific to different universities."

**Cause:** the rotation deals kinds round-robin, with each kind sorted by `n` ascending, so the first ~20 faces are almost all 3s. `MAX_N=12` also hides the mid-size specific groups.

## 1. Per-kind group-size range (replaces the global MAX_N for eligibility)
`MIN_N` stays 3 everywhere; that's the privacy floor. The upper bound now depends on the kind:
- **Specific kinds, up to 25:** school, company, repo, investor, tagged_company, hashtag, prog_lang, industry, city, language, and every combo kind in section 4.
- **Everything else, up to 12.**

The data supports this. For example: 18 studied at UC Berkeley, 17 work at a stealth startup, 17 tagged Anthropic, 24 posted #sftechweek, 20 write C++ on GitHub, 23 speak Chinese. With MAX_N=12 all of those are invisible today. Keep `MAX_N` as an env override that caps everything (default 25).

## 2. Kind tiers and rotation caps
Facts outside the rotation stay in the catalog: they still show on a person's phone ("Your facts") and through `/api/fact/{id}`.
- **Tier 1** (specific, scan-worthy): school, repo, investor, company, tagged_company, hashtag, prog_lang, industry, city, language, ig_hashtag, and the section 4 combos. Cap 20 per kind, except ig_hashtag 6.
- **Tier 2:** volunteer, funding_stage, org_kind, x_since, gh_since, founded_year. Cap 2 each.
- **Tier 3** (broad or generic, the stuff I didn't like seeing): cert 3, cert_issuer 3, cause 1, company_country 1, and **study_country 0 and country 0** (out of the rotation).

## 3. Ordering: spread the numbers
Replace "rarest first" with a count-spread sequence:
- Bucket every rotation-eligible fact by size: **S** = 3–5, **M** = 6–10, **L** = 11–25.
- Build the sequence by cycling S, L, M, S, M, L, … In each slot, pick the highest-scoring unused fact in that bucket whose kind differs from the previous 3 picks and whose `n` differs from the previous pick. If the bucket is empty, take the next bucket.
- **Score** = tier weight (T1 3, T2 2, T3 1) + a recognizability bonus:
  - repo: log10(stars + 1)
  - investor: the number of distinct companies it backs in this graph (well-known funds back several)
  - school, company, tagged_company: log2 of total holders (well-known names)
  - hashtag / ig_hashtag: a +1 bonus for event or community tags (contains week, conf, hack, summit, meetup, or "opensource"), and −2 for generic tags still present (ai, ml, tech, …)
  
  Break ties by id. The result must be deterministic.
- Expect a first 12 faces of mixed sizes like 3, 18, 7, 4, 9, 17, 5, 12, 6, 3, 24, 8.

## 4. New niche combo kinds (≥ 3 holders; keep a combo only if its n is smaller than both parents)
These read as more specific and more surprising. Each one is a multi-hop graph path, which also suits the FalkorDB judges.
- `school_industry`: `(s:School)<-[:STUDIED_AT]-(p)-[:WORKED_AT {current:true}]->(:Company)-[:IN_INDUSTRY]->(i:Industry)`, 3 hops. Line: "people here studied at {s} and now work in {i}".
- `school_stage`: `(s)<-[:STUDIED_AT]-(p)-[:WORKED_AT {current:true}]->(:Company)-[:AT_STAGE]->(st:Stage)`. Line: "people here from {s} work at {st}-stage startups".
- `school_investor`: `(s)<-[:STUDIED_AT]-(p)-[:WORKED_AT {current:true}]->(:Company)-[:BACKED_BY]->(inv:Investor)`. Line: "people here from {s} work at companies backed by {inv}".
- `repo_lang`: `(r:Repo)<-[:CONTRIBUTED_TO]-(p)-[:WRITES]->(l:ProgLang)`. Line: "people here contribute to {r} and write {l}". Only when n ≥ 3.
- **No combos with Language, Country, City or study_country.** Spoken language and location combined with another attribute can act as a proxy for ethnicity or national origin, or narrow down to individuals.
- Add the combos to `fact_path` (show every hop), the You-lines ("You studied at {s} and now work in {i}") and the event templates ("Someone from {s} who now works in {i} just opted in").

## 5. Tests
- Rotation: the first 12 picks contain at least 3 distinct size buckets, and no two consecutive picks share `n` or kind. study_country and country never appear in the rotation, but stay in the catalog.
- Per-kind max: a school with 18 holders is eligible; a cert with 18 is not.
- Each combo kind, plus the "smaller than both parents" rule.
- The privacy floor: nothing with n < 3 anywhere public.
