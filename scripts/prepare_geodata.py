#!/usr/bin/env python3
"""Clip OSM ways/relations, preserve water holes, and prepare scene geometry.

Coordinates are local east/north in units of 100 meters, centered on the bbox.
Procedural infill is explicitly distinguished from mapped OSM footprints.
"""
import json
import math
import random
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize
from shapely import make_valid, set_precision
from shapely.prepared import prep
import mapbox_earcut
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"
terrain = json.loads((DATA / "terrain.json").read_text())
cx, cy = terrain["center"]
w, s, e, n = terrain["bbox"]
KX = math.cos(math.radians(cy)) * 1113.2
KY = 1113.2


def xy(lon, lat):
    return ((lon - cx) * KX, (lat - cy) * KY)


CLIP = box(*xy(w, s), *xy(e, n))


def parts(geom, kind):
    if geom.geom_type == kind:
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from parts(g, kind)


def geom_for(element, polygon=True):
    if element["type"] == "way":
        pts = [xy(p["lon"], p["lat"]) for p in element.get("geometry", [])]
        if len(pts) < (3 if polygon else 2):
            return None
        geom = Polygon(pts) if polygon else LineString(pts)
    else:
        outer, inner = [], []
        for member in element.get("members", []):
            pts = [xy(p["lon"], p["lat"]) for p in member.get("geometry", [])]
            if len(pts) > 1:
                (inner if member.get("role") == "inner" else outer).append(LineString(pts))
        geom = unary_union(list(polygonize(unary_union(outer))))
        if inner:
            geom = geom.difference(unary_union(list(polygonize(unary_union(inner)))))
    return set_precision(make_valid(geom).intersection(CLIP), .001)


def coords(polygon):
    return [[[round(x, 3), round(y, 3)] for x, y in ring.coords] for ring in [polygon.exterior, *polygon.interiors]]


def numeric(value, fallback):
    try:
        return float(str(value).replace("m", "").strip())
    except (ValueError, TypeError):
        return fallback


def triangulate_water(poly):
    rings = [list(ring.coords)[:-1] for ring in [poly.exterior, *poly.interiors]]
    points = np.array([point for ring in rings for point in ring], dtype=np.float64)
    ends = np.cumsum([len(ring) for ring in rings], dtype=np.uint32)
    indices = mapbox_earcut.triangulate_float64(points, ends).reshape(-1, 3)
    return [[[round(float(points[i][0]), 3), round(float(points[i][1]), 3)] for i in tri] for tri in indices]


def main():
    print('Clipping OSM features...', flush=True)
    snapshot = json.loads((ROOT / "work/geodata/osm.json").read_text())
    elements = snapshot["elements"]
    waters, parks, roads, mapped, urban = [], [], [], [], []
    relation_members = {m["ref"] for el in elements if el["type"] == "relation" for m in el.get("members", []) if m["type"] == "way"}
    for el in elements:
        t = el.get("tags", {})
        name = t.get("name", "")
        if t.get("highway"):
            if t.get("tunnel") == "yes":
                continue
            g = geom_for(el, False)
            if g is not None:
                for line in parts(g, "LineString"):
                    line = line.simplify(.06)
                    roads.append({"points": [[round(x, 3), round(y, 3)] for x, y in line.coords], "class": t["highway"], "bridge": t.get("bridge", "no") != "no", "name": name})
            continue
        kind = None
        if t.get("natural") == "water" or t.get("waterway") == "riverbank":
            kind = "water"
        elif t.get("leisure") == "park" or t.get("natural") == "wood" or t.get("landuse") == "forest":
            kind = "park"
        elif t.get("building") and t["building"] != "no":
            kind = "building"
        elif t.get("landuse") in ["residential", "commercial", "retail", "industrial"]:
            kind = "urban"
        if not kind or (el["type"] == "way" and el["id"] in relation_members and kind in ["water", "park"]):
            continue
        g = geom_for(el)
        if g is None:
            continue
        for poly in parts(g, "Polygon"):
            poly = poly.simplify(.035 if kind == "building" else .075, preserve_topology=True)
            if poly.area < .008:
                continue
            if kind == "water":
                waters.append(poly)
            elif kind == "park":
                parks.append(poly)
            elif kind == "urban":
                urban.append(poly)
            else:
                # Buildings keep mapped footprints; default height is an explicit assumption.
                height = numeric(t.get("height"), numeric(t.get("building:levels"), 5) * 3.2)
                mapped.append({"rings": coords(poly), "height": max(3, min(450, height)), "mappedHeight": "height" in t or "building:levels" in t, "source": "osm", "name": name})

    print(f'Merging {len(waters)} water polygons, {len(parks)} parks, {len(mapped)} buildings...', flush=True)
    water = set_precision(unary_union(waters).buffer(0), .001)
    park = set_precision(unary_union(parks).difference(water).buffer(0), .001)
    mapped_union = unary_union([Polygon(item["rings"][0]) for item in mapped])
    road_mask = unary_union([LineString(r["points"]).buffer(.16 if r["class"] in ["primary", "trunk"] else .10) for r in roads])
    infill_area = unary_union(urban).difference(water.buffer(.25)).difference(park).difference(mapped_union.buffer(.20)).difference(road_mask)
    rng = random.Random(771)
    infill = []
    print('Generating infill...', flush=True)
    for poly in parts(infill_area, "Polygon"):
        minx, miny, maxx, maxy = poly.bounds
        if poly.area < .5:
            continue
        x = minx + .4
        while x < maxx:
            y = miny + .4
            while y < maxy:
                px, py = x + rng.uniform(-.16, .16), y + rng.uniform(-.16, .16)
                bw, bd = rng.uniform(.24, .5), rng.uniform(.35, .68)
                footprint = box(px - bw / 2, py - bd / 2, px + bw / 2, py + bd / 2)
                if poly.contains(footprint) and rng.random() > .09:
                    cbd = math.exp(-((px - 12) ** 2 + (py - 10) ** 2) / 430)
                    height = rng.uniform(9, 34) + cbd * rng.uniform(10, 52)
                    infill.append({"rings": coords(footprint), "height": round(height, 1), "mappedHeight": False, "source": "procedural"})
                y += 1.05
            x += 1.0

    print(f'Infill complete: {len(infill)} buildings. Planting trees...', flush=True)
    trees = []
    minx, miny, maxx, maxy = CLIP.bounds
    # Point membership avoids an expensive overlay of thousands of road/building
    # polygons with the full park network, while preserving the same exclusions.
    float_water = set_precision(water, 0)
    tree_park = prep(park)
    tree_outer = prep(float_water.buffer(.65))
    tree_inner = prep(float_water.buffer(.18))
    tree_roads = prep(road_mask)
    tree_buildings = prep(set_precision(mapped_union, 0).buffer(.1))
    attempts = 0
    while len(trees) < 4700 and attempts < 90000:
        attempts += 1
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        point = Point(x, y)
        candidate = tree_park.contains(point) or (tree_outer.contains(point) and not tree_inner.contains(point))
        if candidate and not tree_roads.contains(point) and not tree_buildings.contains(point):
            trees.append([round(x, 3), round(y, 3), round(rng.uniform(.24, .49), 2)])

    print(f'Trees complete: {len(trees)}. Triangulating water...', flush=True)
    output = {"bbox": terrain["bbox"], "center": terrain["center"], "bounds": list(CLIP.bounds), "metersPerUnit": 100,
              "water": [coords(p) for p in parts(water, "Polygon")], "parks": [coords(p) for p in parts(park, "Polygon")],
              "roads": roads, "buildings": mapped + infill, "trees": trees,
              "attribution": "© OpenStreetMap contributors, ODbL 1.0", "osmTimestamp": snapshot.get("osm3s", {}).get("timestamp_osm_base"),
              "stats": {"mappedBuildings": len(mapped), "infillBuildings": len(infill), "roadSegments": len(roads), "trees": len(trees)}}
    output["waterTriangles"] = [tri for poly in parts(water, "Polygon") for tri in triangulate_water(poly)]
    # Flatten the water mask to a single display stage and classify the terrain.
    # This display height is not a flood model or a measured river level.
    print('Sampling display terrain...', flush=True)
    ground, colors = [], []
    water_prepared, park_prepared = prep(water), prep(park)
    for j in range(terrain["rows"]):
        for i in range(terrain["cols"]):
            x = minx + (maxx - minx) * i / (terrain["cols"] - 1)
            y = maxy - (maxy - miny) * j / (terrain["rows"] - 1)
            p = Point(x, y)
            in_water = water_prepared.contains(p)
            ground.append(53.0 if in_water else max(62.0, terrain["heights"][j * terrain["cols"] + i]))
            colors.append(2 if in_water else (1 if park_prepared.contains(p) else 0))
    terrain["sceneHeights"] = ground
    terrain["landcover"] = colors
    (DATA / "terrain.json").write_text(json.dumps(terrain, separators=(",", ":")))
    (DATA / "geography.json").write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(output["stats"]))
    print(f"Water polygons: {len(output['water'])}; parks: {len(output['parks'])}")


if __name__ == "__main__":
    main()
