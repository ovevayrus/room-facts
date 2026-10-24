"""Run a Bright Data scraper on a list of inputs and save the records.

  python bd_dataset.py <name> <dataset_id> <inputs.json> [--discover-limit N] [--type discover_new --discover-by profile_url]
writes data/<name>_raw.json (log: data/<name>.log)
"""
import argparse, json, sys, time, pathlib, requests
from bd_key import bd_key

API = "https://api.brightdata.com/datasets/v3"
DATA = pathlib.Path(__file__).parent / "data"

ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("dataset_id"); ap.add_argument("inputs")
ap.add_argument("--discover-by"); ap.add_argument("--limit", type=int)
ap.add_argument("--snapshot")
a = ap.parse_args()
headers = {"Authorization": f"Bearer {bd_key()}"}
inputs = json.loads(pathlib.Path(a.inputs).read_text(encoding="utf-8"))
print(f"{a.name}: {len(inputs)} inputs", flush=True)

snapshot = a.snapshot
if not snapshot:
    params = {"dataset_id": a.dataset_id, "include_errors": "true"}
    if a.discover_by:
        params.update(type="discover_new", discover_by=a.discover_by)
    if a.limit:
        params["limit_per_input"] = a.limit
    r = requests.post(f"{API}/trigger", headers=headers, params=params, json=inputs, timeout=120)
    if r.status_code >= 400:
        sys.exit(f"trigger failed {r.status_code}: {r.text[:300]}")
    snapshot = r.json()["snapshot_id"]
(DATA / f"{a.name}_snapshot.txt").write_text(snapshot)
print("snapshot", snapshot, flush=True)

while True:
    s = requests.get(f"{API}/progress/{snapshot}", headers=headers, timeout=60).json()
    print(time.strftime("%H:%M:%S"), {k: s.get(k) for k in ("status", "records", "errors")}, flush=True)
    if s.get("status") == "ready":
        break
    if s.get("status") in ("failed", "canceled"):
        sys.exit(f"snapshot {snapshot} {s}")
    time.sleep(20)

while True:  # "ready" can still answer {"status": "building"} for a while
    r = requests.get(f"{API}/snapshot/{snapshot}", headers=headers, params={"format": "json"}, timeout=600)
    r.raise_for_status()
    records = r.json()
    if isinstance(records, list):
        break
    time.sleep(15)
out = DATA / f"{a.name}_raw.json"
out.write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
ok = sum(1 for x in records if not x.get("error"))
print(f"wrote {out.name}: {len(records)} records ({ok} ok, {len(records) - ok} errors)")
