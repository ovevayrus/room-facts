"""Find guests' GitHub accounts and pull orgs, repos they contributed to, and languages.

A candidate only counts when something ties it to the guest: a github.com link the guest published
(Luma website, LinkedIn bio links, X external link), or a GitHub profile pointing back to the guest's
LinkedIn / X / website, or an exact full-name match plus a matching location.

  python enrich_github.py        -> data/github_raw.json
Uses the GitHub GraphQL API with the `gh` CLI's token.
"""
import json, pathlib, re, subprocess, sys, time, unicodedata
import requests

DATA = pathlib.Path(__file__).parent / "data"
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
S = requests.Session()
S.headers["Authorization"] = f"bearer {TOKEN}"

PROFILE = """
login name location company websiteUrl twitterUsername createdAt bio
followers { totalCount }
socialAccounts(first: 10) { nodes { provider url } }
"""
SEARCH = "query($q: String!) { search(query: $q, type: USER, first: 5) { nodes { ... on User { %s } } } }" % PROFILE
DETAIL = """query($login: String!) { user(login: $login) { %s
  organizations(first: 30) { nodes { login name } }
  repositoriesContributedTo(first: 60, includeUserRepositories: false,
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]) { nodes { nameWithOwner stargazerCount } }
  repositories(first: 50, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { name stargazerCount primaryLanguage { name } } }
} }""" % PROFILE


def gql(query, **variables):
    for attempt in range(5):
        r = S.post("https://api.github.com/graphql", json={"query": query, "variables": variables}, timeout=60)
        if r.status_code in (502, 503) or "rate limit" in r.text.lower():
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json().get("data") or {}
    return {}


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def domain(url):
    m = re.search(r"^(?:https?://)?(?:www\.)?([^/?#]+)", (url or "").strip().lower())
    return m.group(1) if m else ""


def gh_login(url):
    m = re.search(r"github\.com/([A-Za-z0-9-]{1,39})(?:[/?#]|$)", url or "")
    return m.group(1) if m and m.group(1).lower() not in {"orgs", "sponsors", "features", "about", "topics"} else None


guests = json.loads((DATA / "luma_guests.json").read_text(encoding="utf-8"))
li = {}
for x in json.loads((DATA / "linkedin_raw.json").read_text(encoding="utf-8")):
    if not x.get("error") and x.get("linkedin_id"):
        li[x["linkedin_id"].lower()] = x
xp = {}
if (DATA / "x_raw.json").exists():
    for x in json.loads((DATA / "x_raw.json").read_text(encoding="utf-8")):
        if not x.get("error") and x.get("profile_name"):
            xp[x["profile_name"].lower()] = x

out = {}
for i, g in enumerate(guests):
    slug = (re.search(r"/in/([^/?#\s]+)", g.get("linkedin_handle") or "") or [None, ""])[1].lower()
    tw = (g.get("twitter_handle") or "").lstrip("@").lower()
    prof = li.get(slug, {})
    xprof = xp.get(tw, {})
    links = [g.get("website")] + [b.get("link") for b in prof.get("bio_links") or []] + [xprof.get("external_link")]
    sites = {domain(u) for u in links if u and "github.com" not in u and "linkedin.com" not in u}
    full = " ".join(p for p in (g.get("first_name"), g.get("last_name")) if p) or g.get("name") or ""
    place = fold(" ".join(filter(None, [prof.get("city"), prof.get("location"), xprof.get("location")])))

    match = None
    direct = next((l for l in map(gh_login, links) if l), None)
    if direct:
        user = gql("query($login: String!) { user(login: $login) { %s } }" % PROFILE, login=direct).get("user")
        if user:
            match = (user, "published link")
    if not match and len(fold(full).split()) >= 2:
        for user in gql(SEARCH, q=f'fullname:"{full}"').get("search", {}).get("nodes", []):
            if not user:
                continue
            social = " ".join(n["url"].lower() for n in user["socialAccounts"]["nodes"])
            if slug and f"/in/{slug}" in social:
                match = (user, "GitHub lists their LinkedIn"); break
            if tw and ((user.get("twitterUsername") or "").lower() == tw or f"x.com/{tw}" in social or f"twitter.com/{tw}" in social):
                match = (user, "GitHub lists their X"); break
            if sites and domain(user.get("websiteUrl")) in sites:
                match = (user, "same website"); break
            loc = fold(user.get("location"))
            if fold(user.get("name")) == fold(full) and loc and place and set(loc.split()) & set(place.split()) - {"area", "greater", "united", "states", "the"}:
                match = (user, "same name and location"); break
    if match:
        detail = gql(DETAIL, login=match[0]["login"]).get("user")
        if detail:
            out[g["api_id"]] = {"match": match[1], **detail}
    if i % 25 == 0:
        print(f"{i}/{len(guests)} checked, {len(out)} matched", flush=True)
    time.sleep(0.4)

(DATA / "github_raw.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
from collections import Counter
print(f"wrote github_raw.json: {len(out)} matched", Counter(v["match"] for v in out.values()))
