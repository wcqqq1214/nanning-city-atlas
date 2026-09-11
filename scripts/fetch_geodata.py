#!/usr/bin/env python3
"""Download an attributed, reproducible snapshot; no API key is required.

pip install -r scripts/requirements.txt
python3 scripts/fetch_geodata.py
"""
import concurrent.futures
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "work" / "geodata"
OUT = ROOT / "public" / "data"
REGION = json.loads((ROOT / 'data/region.json').read_text())
BBOX = REGION['bbox']  # west, south, east, north; WGS84
CENTER = [(BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2]


def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "NanningCityAtlas/1.0 (open geographic visualization)"})
    with urllib.request.urlopen(req, timeout=150) as response:
        return response.read()


def fetch_osm():
    path = CACHE / "osm.json"
    meta = CACHE / 'osm-region.json'
    if path.exists() and meta.exists() and json.loads(meta.read_text()) == BBOX:
        return path
    w, s, e, n = BBOX
    bbox = f"({s},{w},{n},{e})"
    query = f'''[out:json][timeout:140];(
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)(_link)?$"]{bbox};
      way["waterway"="river"]{bbox};
      way["natural"="water"]{bbox}; relation["natural"="water"]{bbox};
      way["waterway"="riverbank"]{bbox}; relation["waterway"="riverbank"]{bbox};
      way["leisure"="park"]{bbox}; relation["leisure"="park"]{bbox};
      way["natural"="wood"]{bbox}; relation["natural"="wood"]{bbox};
      way["landuse"~"^(forest|residential|commercial|retail|industrial)$"]{bbox};
      relation["landuse"="forest"]{bbox};
      way["building"]{bbox};
      relation["building"]{bbox};
      relation["landuse"~"^(residential|commercial|retail|industrial)$"]{bbox};
      way["amenity"="university"]{bbox}; relation["amenity"="university"]{bbox};
      way["tourism"="zoo"]{bbox}; relation["tourism"="zoo"]{bbox};
    );out geom;'''
    (CACHE / "query.overpassql").write_text(query)
    endpoints = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
    for endpoint in endpoints:
        try:
            raw = request(endpoint, urllib.parse.urlencode({"data": query}).encode())
            payload = json.loads(raw)
            if "remark" in payload or not payload.get("elements"):
                raise RuntimeError(payload.get("remark", "Empty Overpass result"))
            path.write_bytes(raw)
            meta.write_text(json.dumps(BBOX))
            print(f"OSM: {len(payload['elements'])} elements from {endpoint}", flush=True)
            return path
        except Exception as error:
            print(f"Overpass endpoint unavailable: {error}", flush=True)
    raise RuntimeError("No complete OSM snapshot available; refusing to invent geographic data.")


def fetch_terrain():
    from resample_terrain import prepare
    prepare(raw_only=True)


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(fetch_osm), pool.submit(fetch_terrain)]
        for task in tasks:
            task.result()
