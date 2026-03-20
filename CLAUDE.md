# nta-rkv-recorder — Claude Code Handover

Nordic Transit Art — Reykjavik recorder.
Records Tuesday vehicle positions to `/data/tuesday.jsonl` (JSONL, 30 s snapshots).

---

## Status: INCOMPLETE — waiting for Strætó agreement

All boilerplate is in place but `straeto_client.py` has placeholder values.
Do NOT deploy until the endpoint URL + credentials arrive from Strætó.

---

## Reykjavik is different from other cities

| | Stockholm | Oslo | Copenhagen | **Reykjavik** |
|---|---|---|---|---|
| Feed format | GTFS-RT protobuf | GTFS-RT protobuf | GTFS-RT? / SIRI? | **Custom XML** |
| Auth | API key | None | API key | **Agreement + key** |
| Vehicle types | metro/tram/bus/train/ferry | metro/tram/bus/train/ferry | metro/bus/train/ferry | **Bus only** |
| protobuf dep needed | yes | yes | yes | **No** |

---

## Monday checklist

### 1. Get Strætó agreement + credentials
- Emailed: dadi@straeto.is (~20 Mar 2026)
- They issue a proprietary endpoint URL + credentials after reviewing the application
- Expected: early week after ~20 Mar 2026

### 2. Inspect the feed
```bash
# Replace with real endpoint + key from email
curl "https://ENDPOINT_URL?key=YOUR_KEY" | xmllint --format -
```
Note the XML tag names for: vehicle list parent element, lat, lon, route, vehicle ID.

### 3. Fix straeto_client.py
- Fill in `FEED_URL`
- Confirm auth method (URL param `?key=`, header, Basic auth — adapt accordingly)
- Fix `root.iter("bus")` → correct parent tag
- Fix `findtext("lat")` etc. → correct field names

### 4. Set Fly secret
```bash
fly secrets set STRAETO_KEY=your_actual_key --app nta-rkv-recorder
```

### 5. Create volume + deploy
```bash
fly volumes create rkv_data --app nta-rkv-recorder --region arn --size-gb 1
fly deploy
fly logs --app nta-rkv-recorder   # watch for [Strætó] lines
```

---

## Project context

Part of the **Nordic Transit Art** project — animated dark-map replays of 24h city transit.
- Helsinki: `https://st-uh-gc.github.io/hsl-artsy-replay/replay.html` ✅
- Stockholm: `nta-sto-recorder` on Fly.io, recording Tuesdays
- Oslo: `nta-osl-recorder` on Fly.io, recording Tuesdays
- Copenhagen: `nta-cph-recorder` — pending Rejseplanen Labs key
- Reykjavik: this repo — pending Strætó agreement

JSONL schema (Helsinki-compatible):
```json
{"t": 1773525606, "v": {"bus_15": [64.135, -21.895, "bus", "15"]}}
```

Recording day: **Tuesday** (Atlantic/Reykjavik = UTC, `wd == 1`).
Output file: `/data/tuesday.jsonl`

---

## File structure

```
state.py           Thread-safe vehicle dict
recorder.py        30 s JSONL snapshot daemon — Tuesday, Atlantic/Reykjavik
straeto_client.py  ⚠️ PLACEHOLDER XML client — complete when agreement arrives
main.py            FastAPI: /health, /tuesday.jsonl — imports straeto_client
requirements.txt   fastapi, uvicorn, tzdata (NO protobuf — XML uses stdlib)
Dockerfile         python:3.12-slim, port 8080
fly.toml           app=nta-rkv-recorder, region=arn, volume=rkv_data→/data
```
