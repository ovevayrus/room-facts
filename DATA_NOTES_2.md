# New sources (scraped 10:47–11:00), to add to the graph

All files are in `data/`, written by `bd_dataset.py` / `enrich_github.py`. Error records have an `error` key. Join everything back to `Person` through the keys below. Keep the privacy rules in SPEC.md as they are: counts only, k≥3, names only via `/people`.

## 1. `orgs_raw.json`: LinkedIn company **and** school pages (493 ok)
The input URL is `input.url`: `/company/<slug>` (302 current employers) or `/school/<slug>` (191 schools). Join to `Company` / `School` by that slug: the same slug as `current_company.company_id`/link and `education[].url`. Fields: `name, organization_type, industries (string), company_size ("2-10 employees"), founded (int|null), headquarters ("Santa Clara, CA"), country_code, specialties, website_simplified`.

New nodes and edges, as 2-hop path facts (the "path behind the answer"):
- `(c:Company)-[:IN_INDUSTRY]->(i:Industry)` → kind `industry`: `(p)-[:WORKED_AT]->(:Company)-[:IN_INDUSTRY]->(i)`. Line "people here work in {i}", for example "Computer and Network Security" or "Venture Capital and Private Equity Principals". Skip "Higher Education" and "Education" for companies, since those are mostly universities as employers.
- `(c:Company)-[:HQ_IN]->(:Country)` for non-US HQs → kind `company_country`: "people here work for companies headquartered in {country}".
- Company size and type → kind `org_kind`, modelled as `(c)-[:IS_A]->(:OrgKind {id})`, from a fixed list: `solo` ("1 employee" → "people here work at a one-person company"), `government` ("Government Agency" → "people here work for a government agency"), `nonprofit` ("Nonprofit" → "people here work at a nonprofit"), `public` ("Public Company" → "people here work at a public company"), `giant` ("10,001+ employees" → "people here work at companies with 10,000+ employees").
- `founded` → kind `founded_year`: `(c)-[:FOUNDED_IN]->(:Year)`. "people here work at companies founded in {year}". Only years ≤ 2015 or the year 2026 are interesting ("founded this year"); skip 2016–2025.
- School pages: `(s:School)-[:LOCATED_IN]->(:Country)` → kind `study_country` (non-US only): "people here studied in {country}" via `(p)-[:STUDIED_AT]->(:School)-[:LOCATED_IN]->(c)`.

## 2. `x_raw.json`: X profiles (358 ok)
Join by `input.url` (`https://x.com/<handle>`) to the Luma `twitter_handle`, case-insensitively. Fields: `date_joined` (ISO), `followers`, `is_verified`, `category_name` (string like "['Science & Technology']"), `biography`, `external_link`. **Ignore** `birth_date` (already stripped) and `location`.
- kind `x_since`: `(p)-[:ON_X_SINCE]->(:Year)`. Only years ≤ 2010 count: "people here have been on X since {year}". Also bucket ≤ 2008 as id `x_since:pre2009`, "people here joined Twitter before 2009".
- kind `x_verified`: one node `(:Badge {id:'x_verified'})`, line "people here are verified on X".

## 3. `li_posts_raw.json`: LinkedIn posts authored since 2026-01-01 (1,277 ok)
Join by `user_id` (the LinkedIn slug) to `Person.linkedin`. Fields: `hashtags` (list or a string repr of a list, e.g. "['#JobSearch', '#buildinpublic']"), `tagged_companies` (a list of `{name, link}`; check the actual shape in the file), `date_posted`.
- kind `hashtag`: `(p)-[:POSTED_ABOUT]->(:Hashtag {id: lowercased without '#'})`. Count distinct people, not posts. Line "people here posted #{tag} on LinkedIn this year". Skip generic tags: ai, artificialintelligence, machinelearning, tech, technology, innovation, startups, startup, hiring, career, learning, linkedin, opentowork, jobsearch, software, softwareengineering, programming, coding, datascience, genai, generativeai.
- kind `tagged_company`: `(p)-[:TAGGED]->(c:Company)`, merged with existing Company nodes by LinkedIn slug when the link has one. Line "people here tagged {c} in a LinkedIn post this year".
- Do NOT use `tagged_people`, `post_text` or comments.

## 4. `github_raw.json`: matched GitHub accounts (dict keyed by Luma `api_id`)
Each value is `{match, login, name, location, company, websiteUrl, twitterUsername, createdAt, followers{totalCount}, organizations{nodes[{login,name}]}, repositoriesContributedTo{nodes[{nameWithOwner, stargazerCount}]}, repositories{nodes[{name, stargazerCount, primaryLanguage{name}}]}}`. `match` says why the account was trusted.
- kind `repo`: `(p)-[:CONTRIBUTED_TO]->(:Repo {id: nameWithOwner lowercased, name: nameWithOwner, stars})`. Line "people here have contributed to {repo} on GitHub". This is the best dev fact: rank `repo` first among kinds in the round-robin.
- kind `gh_org`: `(p)-[:MEMBER_OF]->(:GitHubOrg {id: login})`. Line "people here are members of the {name or login} GitHub org".
- kind `prog_lang`: the primary language of their own non-fork repos with at least 2 repos in that language → `(p)-[:WRITES]->(:ProgLang)`. Line "people here write {lang} on GitHub". It's a separate label from spoken `Language`.
- kind `gh_since`: a single bucket: createdAt year ≤ 2011 → id `gh_since:pre2012`, "people here joined GitHub before 2012" (7 people).
- Real numbers (174 matched): repos with 3–12 people include nousresearch/hermes-agent 7, raycast/extensions 4, xai-org/plugin-marketplace 4, openclaw/openclaw 3, pytorch/helion 3, punkpeye/awesome-mcp-servers 3. GitHub orgs never reach 3, but keep the kind anyway. The rare prog_langs are Swift 11, Rust 8, Go 8, Objective-C 4, C# 3, Ruby 3.
- `stats` adds `github_matched`.

## 5. `instagram_raw.json` and `crunchbase_raw.json` (ready since 11:10)
**Instagram** (208 ok, with emails, pronouns and fbids already stripped). Join by `input.url` (`https://www.instagram.com/<handle>/`) to the Luma `instagram_handle`, case-insensitively. Use only `post_hashtags` (a list, or a string repr of a list); ignore everything else.
- kind `ig_hashtag`: `(p)-[:POSTED_ON_IG]->(:Hashtag)`, reusing the Hashtag nodes. Line "people here posted #{tag} on Instagram". Skip-list: fyp, foryou, instadaily, instalike, instagram, instagood, love, viral, ai, sf, sanfrancisco, bayarea, startup, startups, business, entrepreneur, photooftheday, explore, reels, trending, plus the LinkedIn generic list. Cap it at 8 in the rotation.

**Crunchbase** (220 ok). Each record came from a keyword search for one LinkedIn company name; `discovery_input.keyword` (possibly a string repr of a dict) holds that name. The search is loose ("Quivly AI (YC F26)" → "OpEra Technologies"), so **accept a record only if** its `website` root domain equals that company's `website_simplified` from orgs_raw, or the folded names are equal. Fields: `investors` (a list of dicts; each has an investor name under keys like `investor`/`value`/`name`; check the real shape), `last_funding_type`, `ipo_status`, `founders`.
- kind `investor`: `(p)-[:WORKED_AT]->(:Company)-[:BACKED_BY]->(i:Investor {id, name})`. Line "people here work at companies backed by {i}". It's a 2-hop path. Y Combinator counts as an investor too.
- kind `funding_stage`: `(c)-[:AT_STAGE]->(:Stage)` from `last_funding_type` (Pre-Seed, Seed, Series A, …). Line "people here work at {stage}-stage startups". Skip null/None.

## Fixes from the third real build
- `study_country` (and anywhere else a country is shown) displayed raw codes: "people here studied in IT". Map ISO codes to names with a small built-in dict (no new dependency).
- Countries that need "the": the United Kingdom, the United States, the United Arab Emirates, the Netherlands, the Philippines. Fix both the screen lines and the "You…" lines.

## Fixes from the second real build
- `school_company` produced "people here went from San José State University to San José State University". Skip the pair when the school and the company are the same org: equal folded names, or the same LinkedIn slug, since universities appear as employers too.

## Rotation
Add the new kinds to the round-robin. Order of kinds per round: repo, school, language, industry, city, gh_org, hashtag, study_country, company, org_kind, x_since, tagged_company, prog_lang, cause, volunteer, company_country, founded_year, country, cert_issuer, cert, gh_since, x_verified. Keep the per-kind caps: cert 12, cert_issuer 10, hashtag 15, everything else 20.
