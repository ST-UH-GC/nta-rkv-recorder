"""
Reykjavik Strætó vehicle positions client.

Fetches GTFS-RT vehicle positions from Swiftly on behalf of Strætó bs.
Endpoint: https://api.goswift.ly/real-time/is-straeto/gtfs-rt-vehicle-positions
Auth:     Authorization: {api_key}  (raw key, no Bearer prefix)
Rate:     180 req / 15 min — our 30 s polling = 30 req / 15 min ✓

All Reykjavik transit is buses — no metro, tram, or rail.
Feed covers all Strætó routes including intercity; bounding box
filters to the Capital Region (Höfuðborgarsvæðið).
"""

import gzip
import os
import threading
import time
import urllib.request
import urllib.error

from google.transit import gtfs_realtime_pb2
import state

INTERVAL = 30

# Greater Reykjavik Capital Region bounding box
LAT_MIN, LAT_MAX = 64.05, 64.25
LON_MIN, LON_MAX = -22.10, -21.50

FEED_URL = "https://api.goswift.ly/real-time/is-straeto/gtfs-rt-vehicle-positions"
API_KEY  = os.environ.get("SWIFTLY_KEY", "")


def _classify(_route_id: str) -> str:
    return "bus"  # Reykjavik is buses only — no metro/tram/rail


def _fetch_and_update() -> int:
    if not API_KEY:
        print("[GTFS] WARNING: SWIFTLY_KEY not set — skipping fetch")
        return 0

    try:
        req = urllib.request.Request(
            FEED_URL,
            headers={
                "Authorization": API_KEY,
                "Accept-Encoding": "gzip",
                "User-Agent": "nta-rkv-recorder/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"[GTFS] HTTP {e.code}: {e.reason}")
        return 0
    except Exception as e:
        print(f"[GTFS] Fetch error: {e}")
        return 0

    # Decompress if gzip
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except Exception as e:
        print(f"[GTFS] Parse error: {e}")
        return 0

    seen: set = set()

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        veh = entity.vehicle
        if not veh.HasField("position"):
            continue

        lat = veh.position.latitude
        lon = veh.position.longitude

        if lat == 0.0 and lon == 0.0:
            continue
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            continue

        vid = veh.vehicle.id or entity.id
        if not vid:
            continue

        route_id = veh.trip.route_id or ""
        route = route_id.split(":")[-1].split("_")[0] if route_id else ""

        seen.add(vid)
        state.update_vehicle(vid, {
            "lat":   round(lat, 6),
            "lon":   round(lon, 6),
            "type":  "bus",
            "route": route,
        })

    # Remove vehicles gone from feed
    for gone in set(state.get_all_vehicles().keys()) - seen:
        state.remove_vehicle(gone)

    return len(seen)


def _poll_loop() -> None:
    print(f"[GTFS] Starting poll loop (every {INTERVAL}s)")
    backoff = 5
    while True:
        try:
            n = _fetch_and_update()
            print(f"[GTFS] {n} vehicles in state")
            backoff = 5
        except Exception as e:
            print(f"[GTFS] Unexpected error: {e} — retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        time.sleep(INTERVAL)


def start_straeto_thread() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()
