"""Pull the Luma guest list (names + socials) for the event into data/luma_guests.json.

  python fetch_luma.py <event_api_id> <ticket_key>   # ticket_key = the ?tk= value of your Luma invite link
"""
import json, sys, time, pathlib, requests

event_id, ticket_key = sys.argv[1], sys.argv[2]
out = pathlib.Path(__file__).parent / "data" / "luma_guests.json"
url = "https://api.lu.ma/event/get-guest-list"
guests, cursor = [], None
while True:
    params = {"event_api_id": event_id, "ticket_key": ticket_key, "pagination_limit": 100}
    if cursor:
        params["pagination_cursor"] = cursor
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    d = r.json()
    guests += [e["user"] for e in d["entries"]]
    print(f"{len(guests)} guests", flush=True)
    if not d.get("has_more"):
        break
    cursor = d["next_cursor"]
    time.sleep(0.5)
out.write_text(json.dumps(guests, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote", out)
