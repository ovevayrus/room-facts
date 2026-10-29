# LinkedIn data: what the scrape actually looked like

Scraped at 10:36 on build day into `data/linkedin_raw.json`.

The file holds 576 records: 514 profiles and 62 errors (`dead_page` / `wait_element_timeout`). Fill counts, out of 514: city 514, country_code 514, current_company 379, education 350 (many entries have no title), educations_details 445, languages 204, certifications 264, volunteer_experience 145, courses 81, honors 140, organizations 57. **experience: 3** (it's effectively absent).

What `normalize.py`, `facts.py` and `build_graph.py` do about it:

1. **Accent-fold ids**: NFKD, then drop combining marks. "San José State University" and "San Jose State University" are the same school (22 holders). Display the most common spelling.
2. **Company comes from `current_company`** (`{name, company_id, link}`), since experience is missing. Set `current=true`. When every holder edge is current, the line is "people here work at {c}", otherwise "people here have worked at {c}". Prefer `current_company.company_id` as the id, but note the slugs can be odd ("steath", "marshell-labs" for "Mote"), so merge by folded name too.
3. **Stealth**: "Stealth", "Stealth Startup", "Stealth AI Startup", "Stealth Mode" and "Stealth Investment Firm" all become company id `stealth`, display "a stealth startup", line "people here work at a stealth startup".
4. **Education fallback**: if a person has no education entry with a `title`, use `educations_details` (a string with one school name) as their school. The school "Y Combinator" gets the line "people here went through Y Combinator".
5. **City**: about a third of values have no commas and are countries or metros. Skip the city when the value is just a country ("United States", "India", "Canada", "Brazil", "Argentina", "Italy", "Romania", "Sweden", "Switzerland", "Philippines", "United Arab Emirates"); the country already arrives through BASED_IN. Map metros:
   - "Greater X Area" / "X Metropolitan Area" / "X Metro" → X
   - "New York City Metropolitan Area" and "New York, New York, United States" → "New York City"
   - "Greater Bengaluru Area" and "Bengaluru, Karnataka, India" → "Bengaluru"
   - "Pune/Pimpri-Chinchwad Area" → "Pune"; "Greater Delhi Area" / "New Delhi, …" → "Delhi"
   - "Washington DC-Baltimore Area" → "Washington DC"; "Hong Kong SAR" → "Hong Kong"
   - "San Francisco Bay Area" and "San Francisco, California, …" stay distinct from specific Bay Area cities (Sunnyvale 7, Palo Alto 6, Santa Clara 6, Oakland 4, Fremont 3, …). Those specific cities are the rare ones and must stay separate.
6. **Languages**: drop English. Title-case the display name, and map "Chinese (Mandarin)" / "Mandarin Chinese" → "Mandarin". There are 17 rare ones (Sanskrit 7, Kannada 7, Romanian 3, Greek 3, …).
7. **New path kind, `cert_issuer`**: model `(:Cert)-[:ISSUED_BY]->(:Issuer {id, name})` from `certifications[].subtitle`. The fact `(p)-[:CERTIFIED]->(:Cert)-[:ISSUED_BY]->(i:Issuer)` gets the line "people here have certifications from {i}" and src "LinkedIn certifications". It's a 2-hop path and good for the "path behind every answer" story. There are 37 rare issuers (Hugging Face 4, The Linux Foundation 3, Stanford Online 3, …). Add it to the dedupe kind order after `cert`.
8. The `cause` values are LinkedIn's fixed list (Education 76 … Animal Welfare 4). Keep it.
9. Keep `MIN_N=3` and `MAX_N=12`.

Things I noticed on the first real build (106 eligible facts: cert 37, school 18, language 16, city 14, cause 7, company 6, volunteer 5, country 2, school_company 1):

10. **US city display**: show "Fremont, CA" (state abbreviation, from "Fremont, California, United States"), because "people here live in Dublin" means Dublin, CA, not Ireland. Non-US cities stay bare ("Bengaluru", "London"). The id must still separate same-named cities in different states or countries.
11. **Rotation balance**: deal round-robin across kinds, each kind sorted by `n` ascending and then id, so the mix stays varied. Cap `cert` at the 12 rarest and `cert_issuer` at 10. Facts over a cap are still valid for `/api/person/{id}/facts` and `/api/fact/{id}`; they're just left out of the `/api/facts` rotation.
12. **Event grammar bug**: `"Someone who " + line.removeprefix("people here ")` produces "Someone who have worked at…" and "Someone who speak…". Add per-kind third-person templates: "Someone who studied at {a}", "works at {a}", "lives in {a}", "is based in {a}", "speaks {a}", "holds the {a} certification", "has certifications from {a}", "has volunteered at {a}", "volunteers for {a}", "went from {a} to {b}", "has worked at both {a} and {b}", "went through Y Combinator".
13. `YOU_LINES` follow the same rules: "You work at {a}", "You went through Y Combinator", "You have certifications from {a}".
