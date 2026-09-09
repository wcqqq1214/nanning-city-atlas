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
from shapely.affinity import rotate
from shapely.ops import unary_union, polygonize
from shapely import make_valid, set_precision
from shapely.prepared import prep
from shapely.strtree import STRtree
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


def infer_urban_blocks(roads, mapped, known):
    """Fill land-use gaps only in bounded streets near mapped city buildings.

    These blocks are inferred display areas, not additional surveyed land use.
    Water, parks, roads and existing buildings are excluded by the caller.
    """
    classes = {"primary", "secondary", "tertiary", "residential",
               "living_street", "unclassified", "service"}
    lines = [LineString(r["points"]) for r in roads
             if not r["bridge"] and r["class"] in classes]
    centers = STRtree([Polygon(b["rings"][0]).centroid for b in mapped])
    known_prepared = prep(known)
    accepted = []
    for block in polygonize(unary_union(lines)):
        # Units are 100 m: accept 0.3–30 ha blocks, within 100 m of known
        # urban land and anchored by at least three buildings within 60 m.
        if not .3 < block.area < 30 or known_prepared.covers(block):
            continue
        if block.distance(known) > 1:
            continue
        if len(centers.query(block.buffer(.6), predicate="intersects")) < 3:
            continue
        accepted.append(block)
    return set_precision(unary_union(accepted), .001).difference(known)


def generate_infill(area):
    """Pack varied, non-overlapping blocks along each buildable parcel's axes."""
    rng = random.Random(771)
    cbd_x, cbd_y = xy(108.377, 22.814)
    buildings = []
    for poly in parts(area, "Polygon"):
        if poly.area < .18:
            continue
        envelope = list(poly.minimum_rotated_rectangle.exterior.coords)
        a, b = max(zip(envelope, envelope[1:]),
                   key=lambda edge: math.dist(*edge))
        angle = (math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi / 4) % (math.pi / 2) - math.pi / 4
        origin = (poly.centroid.x, poly.centroid.y)
        local = rotate(poly, -angle, origin=origin, use_radians=True)
        permitted = prep(local.buffer(-.003))
        minx, miny, maxx, maxy = local.bounds
        x = minx + .31
        while x < maxx:
            y = miny + .37
            while y < maxy:
                px, py = x + rng.uniform(-.035, .035), y + rng.uniform(-.035, .035)
                # A 62 x 74 m cell preserves a gap even for the largest blocks
                # after jitter. Rotation applies to the whole parcel grid.
                width, depth = rng.uniform(.24, .50), rng.uniform(.32, .60)
                footprint = box(px - width / 2, py - depth / 2,
                                px + width / 2, py + depth / 2)
                if permitted.contains(footprint) and rng.random() > .025:
                    footprint = rotate(footprint, angle, origin=origin, use_radians=True)
                    center = footprint.centroid
                    cbd = math.exp(-((center.x - cbd_x) ** 2 + (center.y - cbd_y) ** 2) / 430)
                    tier = rng.random()
                    height = rng.uniform(9, 17) if tier < .22 else rng.uniform(18, 38)
                    if tier > .9:
                        height = rng.uniform(40, 60)
                    height += cbd * rng.uniform(5, 30)
                    buildings.append({"rings": coords(footprint), "height": round(height, 1),
                                      "mappedHeight": False, "source": "procedural"})
                y += .74
            x += .62
    return buildings


def main():
    print('Clipping OSM features...', flush=True)
    snapshot = json.loads((ROOT / "work/geodata/osm.json").read_text())
    elements = snapshot["elements"]
    waters, parks, roads, mapped, urban = [], [], [], [], []
    def feature_kind(t):
        if t.get('natural') == 'water' or t.get('waterway') == 'riverbank': return 'water'
        if t.get('leisure') == 'park' or t.get('natural') == 'wood' or t.get('landuse') == 'forest': return 'park'
        if t.get('building') and t['building'] != 'no': return 'building'
        if t.get('landuse') in ['residential', 'commercial', 'retail', 'industrial']: return 'urban'
        return None
    relation_members = {(feature_kind(el.get('tags', {})), m['ref']) for el in elements if el['type'] == 'relation' for m in el.get('members', []) if m['type'] == 'way'}
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
        kind = feature_kind(t)
        if not kind or (el['type'] == 'way' and (kind, el['id']) in relation_members):
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
    road_mask = unary_union([LineString(r["points"]).buffer(
        .19 if r["class"] in ["primary", "trunk", "motorway"] else
        (.135 if r["class"] == "secondary" else .10)) for r in roads])
    # Snap both land-use sources before overlay so serialized shared boundaries
    # remain coincident instead of opening narrow gaps after JSON rounding.
    urban_area = set_precision(unary_union(urban), .001)
    inferred_urban = infer_urban_blocks(roads, mapped, urban_area)
    buildable = urban_area.union(inferred_urban)
    infill_area = buildable.difference(water.buffer(.25)).difference(park).difference(mapped_union.buffer(.12)).difference(road_mask)
    urban_rings = [coords(p) for p in parts(urban_area, "Polygon")]
    inferred_rings = [coords(p) for p in parts(inferred_urban, "Polygon")]
    # Check the actual serialized boundaries as well: overlay/rounding can leave
    # sub-meter seams where an inferred street block meets mapped land use.
    serialized_land = prep(unary_union([Polygon(p[0], p[1:])
                                       for p in urban_rings + inferred_rings]))
    print('Generating infill...', flush=True)
    infill = [b for b in generate_infill(infill_area)
              if serialized_land.covers(Polygon(b["rings"][0]))]

    print(f'Infill complete: {len(infill)} buildings. Planting trees...', flush=True)
    # Keep planting reproducible independently of changes to building density.
    rng = random.Random(772)
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
    while len(trees) < 11000 and attempts < 220000:
        attempts += 1
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        point = Point(x, y)
        candidate = tree_park.contains(point) or (tree_outer.contains(point) and not tree_inner.contains(point))
        if candidate and not tree_roads.contains(point) and not tree_buildings.contains(point):
            trees.append([round(x, 3), round(y, 3), round(rng.uniform(.24, .49), 2)])

    print(f'Trees complete: {len(trees)}. Triangulating water...', flush=True)
    output = {"bbox": terrain["bbox"], "center": terrain["center"], "bounds": list(CLIP.bounds), "metersPerUnit": 100,
              "water": [coords(p) for p in parts(water, "Polygon")], "parks": [coords(p) for p in parts(park, "Polygon")],
              "urban": urban_rings, "inferredUrban": inferred_rings,
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
