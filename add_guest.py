"""Add someone who isn't on the Luma guest list, and scrape just their LinkedIn profile with Bright Data.

  python add_guest.py "Kunal Kushwaha" --linkedin https://www.linkedin.com/in/<slug>
  python add_guest.py "Liz Zhang" --company falkordb      # no URL: discover by name, keep the one profile at that company
  python build_graph.py                                   # then rebuild; it merges data/extra_guests.json

Skips anyone already on the Luma list or in data/extra_guests.json (same LinkedIn slug or full name).
Writes data/extra_guests.json and merges the profile into data/linkedin_raw.json. Both stay out of git.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import requests

from normalize import linkedin_slug, slug

DATASET = "gd_l1viktl72bvl7bjuj0"  # Bright Data "LinkedIn people profiles", as in enrich_linkedin.py
API = "https://api.brightdata.com/datasets/v3"
DATA = Path(__file__).resolve().parent / "data"
EXTRA = DATA / "extra_guests.json"


def read_list(path):
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else []


def guest_name(guest):
    return " ".join(str(guest.get(k) or "").strip() for k in ("first_name", "last_name")).strip() or str(guest.get("name") or "")


def existing_guest(guests, name, li_slug):
    for guest in guests:
        if not isinstance(guest, dict):
            continue
        if li_slug and linkedin_slug(guest.get("linkedin_handle")) == li_slug:
            return guest
        if slug(guest_name(guest)) == slug(name):
            return guest
    return None


def scrape(inputs, params, headers):
    """Trigger a Bright Data snapshot, wait for it, and return its records."""
    r = requests.post(f"{API}/trigger", headers=headers, timeout=120,
                      params={"dataset_id": DATASET, "include_errors": "true", **params}, json=inputs)
    if r.status_code >= 400:
        sys.exit(f"trigger failed {r.status_code}: {r.text[:300]}")
    snapshot = r.json()["snapshot_id"]
    print("snapshot", snapshot, flush=True)
    while True:
        status = requests.get(f"{API}/progress/{snapshot}", headers=headers, timeout=60).json()
        print(time.strftime("%H:%M:%S"), status.get("status"), flush=True)
        if status.get("status") == "ready":
            break
        if status.get("status") in ("failed", "canceled"):
            sys.exit(f"snapshot {snapshot} {status}")
        time.sleep(15)
    while True:  # "ready" can still answer {"status": "building"} for a while
        r = requests.get(f"{API}/snapshot/{snapshot}", headers=headers, params={"format": "json"}, timeout=300)
        r.raise_for_status()
        records = r.json()
        if isinstance(records, list):
            return records
        time.sleep(10)


def works_at(record, company):
    want = slug(company)
    current = record.get("current_company") or {}
    names = [current.get("name") if isinstance(current, dict) else None, record.get("current_company_name")]
    names += [exp.get("company") for exp in record.get("experience") or [] if isinstance(exp, dict) and not exp.get("end_date")]
    return any(want and want in slug(n) for n in names if isinstance(n, str))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help='full name, e.g. "Kunal Kushwaha"')
    ap.add_argument("--linkedin", help="LinkedIn profile URL or /in/<slug>")
    ap.add_argument("--company", help="with no --linkedin: keep the discovered profile whose current company matches")
    ap.add_argument("--x", dest="x_handle", help="X handle (optional)")
    ap.add_argument("--no-scrape", action="store_true", help="only add the guest; don't call Bright Data")
    a = ap.parse_args(argv)
    first, _, last = a.name.strip().partition(" ")
    li_slug = linkedin_slug(a.linkedin) if a.linkedin else None
    if a.linkedin and not li_slug:
        sys.exit(f"Not a LinkedIn profile URL: {a.linkedin}")
    if not li_slug and not a.company and not a.no_scrape:
        sys.exit("Give --linkedin, or --company so discovery by name can pick the right profile.")

    extra = read_list(EXTRA)
    found = existing_guest(read_list(DATA / "luma_guests.json") + extra, a.name, li_slug)
    if found:
        print(f"{a.name} is already a guest ({found.get('api_id')}); nothing to add.")
        return 0

    record = None
    if not a.no_scrape:
        from bd_key import bd_key
        headers = {"Authorization": f"Bearer {bd_key()}"}
        if li_slug:
            records = scrape([{"url": f"https://www.linkedin.com/in/{li_slug}"}], {}, headers)
        else:
            records = scrape([{"first_name": first, "last_name": last}], {"type": "discover_new", "discover_by": "name", "limit_per_input": 20}, headers)
            records = [r for r in records if not r.get("error") and works_at(r, a.company)]
            if len(records) != 1:
                for r in records:
                    print(" -", r.get("name"), "|", r.get("position"), "|", r.get("url"))
                sys.exit(f"Found {len(records)} profiles for {a.name} at {a.company}; rerun with --linkedin <url>.")
            li_slug = linkedin_slug(records[0].get("linkedin_id") or records[0].get("url"))
        record = next((r for r in records if not r.get("error")), None)
        if not record:
            sys.exit(f"Bright Data returned no profile for {a.name}: {records[:1]}")
        found = existing_guest(read_list(DATA / "luma_guests.json") + extra, a.name, li_slug)
        if found:
            print(f"{a.name} is already a guest ({found.get('api_id')}); nothing to add.")
            return 0
        linkedin = read_list(DATA / "linkedin_raw.json")
        key = lambda r: linkedin_slug(r.get("linkedin_id")) or linkedin_slug((r.get("input") or {}).get("url")) or linkedin_slug(r.get("input_url"))
        linkedin = [r for r in linkedin if not (isinstance(r, dict) and key(r) == li_slug)] + [record]
        DATA.mkdir(exist_ok=True)
        (DATA / "linkedin_raw.json").write_text(json.dumps(linkedin, indent=1, ensure_ascii=False), encoding="utf-8")

    guest = {"api_id": f"extra-{li_slug or slug(a.name)}", "first_name": first, "last_name": last,
             "linkedin_handle": f"/in/{li_slug}" if li_slug else "", "twitter_handle": a.x_handle or "",
             "avatar_url": (record or {}).get("avatar") or "", "source": "manual"}
    DATA.mkdir(exist_ok=True)
    EXTRA.write_text(json.dumps(extra + [guest], indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Added {a.name} as {guest['api_id']}" + (f" with LinkedIn /in/{li_slug}" if li_slug else "") + ". Now run: python build_graph.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
