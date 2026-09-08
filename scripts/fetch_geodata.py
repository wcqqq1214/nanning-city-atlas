#!/usr/bin/env python3
"""Download an attributed, reproducible snapshot; no API key is required.

pip install -r scripts/requirements.txt
python3 scripts/fetch_geodata.py
"""
import concurrent.futures
import datetime
import io
import json
import math
from pathlib import Path
import urllib.parse
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "work" / "geodata"
OUT = ROOT / "public" / "data"
BBOX = [108.265, 22.735, 108.465, 22.875]  # west, south, east, north; WGS84
CENTER = [(BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2]
ZOOM = 12


def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "NanningCityAtlas/1.0 (open geographic visualization)"})
    with urllib.request.urlopen(req, timeout=150) as response:
        return response.read()


def tile_xy(lon, lat):
    n = 2 ** ZOOM
    return ((lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def fetch_osm():
    path = CACHE / "osm.json"
    if path.exists():
        return path
    w, s, e, n = BBOX
    bbox = f"({s},{w},{n},{e})"
    query = f'''[out:json][timeout:100];(
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)(_link)?$"]{bbox};
      way["waterway"="river"]{bbox};
      way["natural"="water"]{bbox}; relation["natural"="water"]{bbox};
      way["waterway"="riverbank"]{bbox}; relation["waterway"="riverbank"]{bbox};
      way["leisure"="park"]{bbox}; relation["leisure"="park"]{bbox};
      way["natural"="wood"]{bbox}; relation["natural"="wood"]{bbox};
      way["landuse"~"^(forest|residential|commercial|retail|industrial)$"]{bbox};
      relation["landuse"="forest"]{bbox};
      way["building"]{bbox};
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
            print(f"OSM: {len(payload['elements'])} elements from {endpoint}", flush=True)
            return path
        except Exception as error:
            print(f"Overpass endpoint unavailable: {error}", flush=True)
    raise RuntimeError("No complete OSM snapshot available; refusing to invent geographic data.")


def fetch_terrain():
    w, s, e, n = BBOX
    x0, y0 = tile_xy(w, n)
    x1, y1 = tile_xy(e, s)
    tiles = {}

    def fetch_tile(key):
        x, y = key
        path = CACHE / f"terrain-{ZOOM}-{x}-{y}.png"
        url = f"https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{ZOOM}/{x}/{y}.png"
        if not path.exists():
            path.write_bytes(request(url))
        return key, Image.open(io.BytesIO(path.read_bytes())).convert("RGB")

    keys = [(x, y) for x in range(int(x0), int(x1) + 1) for y in range(int(y0), int(y1) + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tiles.update(pool.map(fetch_tile, keys))
    cols, rows = 225, 173
    heights = []
    for j in range(rows):
        lat = n - (n - s) * j / (rows - 1)
        for i in range(cols):
            lon = w + (e - w) * i / (cols - 1)
            x, y = tile_xy(lon, lat)
            rgb = tiles[(int(x), int(y))].getpixel((min(255, int(x % 1 * 256)), min(255, int(y % 1 * 256))))
            heights.append(round(rgb[0] * 256 + rgb[1] + rgb[2] / 256 - 32768, 1))
    terrain = {"bbox": BBOX, "center": CENTER, "cols": cols, "rows": rows, "heights": heights, "tileZoom": ZOOM,
               "minElevation": min(heights), "maxElevation": max(heights), "units": "meters", "datum": "source DEM heights",
               "source": "Mapzen / AWS Terrain Tiles; SRTM terrain data courtesy of the U.S. Geological Survey",
               "accessed": datetime.date.today().isoformat()}
    (OUT / "terrain.json").write_text(json.dumps(terrain, separators=(",", ":")))
    print(f"Terrain: {len(keys)} tiles, {cols} × {rows}, {min(heights)}–{max(heights)} m", flush=True)


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(fetch_osm), pool.submit(fetch_terrain)]
        for task in tasks:
            task.result()
