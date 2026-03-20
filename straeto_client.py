"""
Reykjavik Strætó vehicle positions client.

# ============================================================
# TODO — COMPLETE THIS FILE WHEN STRÆTÓ AGREEMENT ARRIVES
# ============================================================
#
# Provider: Strætó bs (straeto.is)
# Contact:  dadi@straeto.is (Daði Áslaugarson, Head of IT)
#
# IMPORTANT DIFFERENCES FROM OTHER CITIES:
#   - Strætó uses CUSTOM XML, not GTFS-RT protobuf
#   - Feed format: proprietary XML (see below)
#   - All vehicles are buses — no metro/tram/rail in Reykjavik
#   - Feed URL and credentials come via direct agreement with Strætó
#   - No public documentation for the real-time endpoint
#
# STEP 1: Get endpoint URL + credentials from the agreement email.
#
# STEP 2: Test the feed:
#   curl "ENDPOINT_URL?key=YOUR_KEY" | xmllint --format -
#
# STEP 3: Verify XML structure. Expected per-vehicle fields:
#   lat   — latitude
#   lon   — longitude
#   head  — bearing (degrees, 0=North)
#   fix   — GPS quality (0=bad, 1=lower, 2=high) — skip fix=0 records
#   route — bus line number (short int e.g. "15", "57")
#   stop  — last visited stop ID
#   next  — next stop ID
#   time  — GPS timestamp (YYMMDDhhmmss format)
#
#   Note: exact XML tag names must be confirmed against the real feed.
#   Adapt _parse_xml() if tag names differ.
#
# STEP 4: Set Fly secret:
#   fly secrets set STRAETO_KEY=your_key --app nta-rkv-recorder
#
# STEP 5: Create volume + deploy:
#   fly volumes create rkv_data --region arn --size-gb 1
#   fly deploy
#
# ============================================================

import os
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

import state

INTERVAL = 30

# Greater Reykjavik Capital Region bounding box
LAT_MIN, LAT_MAX = 64.05, 64.25
LON_MIN, LON_MAX = -22.10, -21.50

# TODO: replace with real endpoint from Strætó agreement
FEED_URL = "https://PLACEHOLDER.straeto.is/realtime/vehicles"

# Credentials from Strætó — set as Fly secret STRAETO_KEY
API_KEY = os.environ.get("STRAETO_KEY", "")


def _parse_xml(raw: bytes) -> int:
    """
    Parse Strætó custom XML vehicle feed.
    TODO: verify tag names against actual feed — adapt as needed.
    Returns number of vehicles updated.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"[Strætó] XML parse error: {e}")
        return 0

    seen: set = set()

    # TODO: confirm the actual parent element name (e.g. <Buses>, <Vehicles>, <feed>)
    for bus in root.iter("bus"):  # ← adjust tag name after inspecting real feed
        try:
            lat = float(bus.findtext("lat") or "0")
            lon = float(bus.findtext("lon") or "0")
            fix = int(bus.findtext("fix") or "0")
            route = bus.findtext("route") or ""
            vid_raw = bus.findtext("id") or bus.findtext("vehicleId") or route

            # Skip bad GPS fixes
            if fix == 0:
                continue

            if lat == 0.0 and lon == 0.0:
                continue
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                continue

            vid = f"bus_{vid_raw}"
            seen.add(vid)
            state.update_vehicle(vid, {
                "lat":   round(lat, 6),
                "lon":   round(lon, 6),
                "type":  "bus",   # all Reykjavik transit is bus
                "route": route,
            })
        except (ValueError, TypeError):
            continue

    # Remove vehicles gone from feed
    for gone in set(state.get_all_vehicles().keys()) - seen:
        state.remove_vehicle(gone)

    return len(seen)


def _fetch_and_update() -> int:
    if not API_KEY:
        print("[Strætó] WARNING: STRAETO_KEY not set — skipping fetch")
        return 0

    try:
        # TODO: confirm auth method — URL param, header, or Basic auth
        url = f"{FEED_URL}?key={API_KEY}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "nta-rkv-recorder/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"[Strætó] HTTP {e.code}: {e.reason}")
        return 0
    except Exception as e:
        print(f"[Strætó] Fetch error: {e}")
        return 0

    return _parse_xml(raw)


def _poll_loop() -> None:
    print(f"[Strætó] Starting poll loop (every {INTERVAL}s)")
    backoff = 5
    while True:
        try:
            n = _fetch_and_update()
            print(f"[Strætó] {n} vehicles in state")
            backoff = 5
        except Exception as e:
            print(f"[Strætó] Unexpected error: {e} — retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        time.sleep(INTERVAL)


def start_straeto_thread() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()
