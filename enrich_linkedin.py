"""Scrape every guest's LinkedIn profile with Bright Data's LinkedIn people profiles scraper.

  python enrich_linkedin.py            # trigger, wait, download -> data/linkedin_raw.json
  python enrich_linkedin.py sd_xxx     # resume waiting on an existing snapshot
"""
import json, re, sys, time, pathlib, requests
from bd_key import bd_key

DATASET = "gd_l1viktl72bvl7bjuj0"
API = "https://api.brightdata.com/datasets/v3"
DATA = pathlib.Path(__file__).parent / "data"
HEADERS = {"Authorization": f"Bearer {bd_key()}"}


def linkedin_url(handle):
    # Luma stores "/in/<slug>"; skip company pages, blanks and free text
    m = re.fullmatch(r"(?:https?://[^/]*linkedin\.com)?/?in/([^/?#\s]+)/?", (handle or "").strip())
    return f"https://www.linkedin.com/in/{m.group(1)}" if m else None


guests = json.loads((DATA / "luma_guests.json").read_text(encoding="utf-8"))
urls = sorted({u for g in guests if (u := linkedin_url(g.get("linkedin_handle")))})
print(f"{len(urls)} LinkedIn URLs from {len(guests)} guests", flush=True)

if len(sys.argv) > 1:
    snapshot = sys.argv[1]
else:
    r = requests.post(f"{API}/trigger", headers=HEADERS, timeout=60,
                      params={"dataset_id": DATASET, "include_errors": "true"},
                      json=[{"url": u} for u in urls])
    r.raise_for_status()
    snapshot = r.json()["snapshot_id"]
(DATA / "linkedin_snapshot.txt").write_text(snapshot)
print("snapshot", snapshot, flush=True)

while True:
    status = requests.get(f"{API}/progress/{snapshot}", headers=HEADERS, timeout=60).json()
    print(time.strftime("%H:%M:%S"), status, flush=True)
    if status.get("status") == "ready":
        break
    if status.get("status") in ("failed", "canceled"):
        raise SystemExit(f"snapshot {snapshot} {status}")
    time.sleep(20)

while True:  # "ready" can still answer {"status": "building"} for a while
    r = requests.get(f"{API}/snapshot/{snapshot}", headers=HEADERS, params={"format": "json"}, timeout=300)
    r.raise_for_status()
    records = r.json()
    if isinstance(records, list):
        break
    print(time.strftime("%H:%M:%S"), records, flush=True)
    time.sleep(15)
(DATA / "linkedin_raw.json").write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
ok = sum(1 for x in records if not x.get("error"))
print(f"wrote {len(records)} records ({ok} ok, {len(records) - ok} errors)")
