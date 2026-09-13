"""Improve mapped footprints and height provenance after deterministic infill.

This postprocess preserves building IDs, array order, and every non-building
feature. Run against a frozen input before promoting the candidate geography.
"""
import argparse
import copy
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.strtree import STRtree

from prepare_urban_blocks import rings, roof_triangles

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/building-quality-source.json'
POLICY = json.loads(SOURCE.read_text())


def mesh_roof_triangles(outlines):
    """Triangulate in Blender's stored precision, without changing source rings.

    Rounding already-triangulated concave roofs can move a vertex across a
    diagonal. Quantize first so the resulting topology fits the stored walls.
    """
    vertices=np.asarray([p for ring in outlines for p in ring[:-1]],dtype=np.float32).astype(np.float64)
    ends=np.cumsum([len(ring)-1 for ring in outlines],dtype=np.uint32)
    faces=mapbox_earcut.triangulate_float64(vertices,ends).reshape(-1,3)
    faces=stable_roof_diagonals(vertices,faces)
    return vertices[faces].tolist()


def stable_roof_diagonals(vertices,faces):
    """Flip interior diagonals to avoid compression-sensitive needle triangles.

    Only strictly convex pairs are flipped. All boundary edges and vertices
    stay fixed, including courtyard boundaries. Prefer a larger minimum
    altitude in the pair; a deterministic sweep makes output reproducible.
    """
    faces=[list(map(int,f)) for f in faces]
    def cross(a,b,c):
        p,q,r=vertices[a],vertices[b],vertices[c]
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def orient(f):return f if cross(*f)>0 else [f[0],f[2],f[1]]
    def altitude(f):
        lengths=[math.dist(vertices[a],vertices[b]) for a,b in zip(f,f[1:]+f[:1])]
        return abs(cross(*f))/max(lengths)
    faces=[orient(f) for f in faces]
    for _ in range(30):
        edges={}
        for i,f in enumerate(faces):
            for a,b in zip(f,f[1:]+f[:1]):edges.setdefault(tuple(sorted((a,b))),[]).append(i)
        changed=False;used=set()
        for (a,b),ids in sorted(edges.items()):
            if len(ids)!=2 or any(i in used for i in ids):continue
            i,j=ids;c=next(v for v in faces[i] if v not in (a,b));d=next(v for v in faces[j] if v not in (a,b))
            if c==d or tuple(sorted((c,d))) in edges:continue
            if cross(a,b,c)*cross(a,b,d)>=0 or cross(c,d,a)*cross(c,d,b)>=0:continue
            first,second=orient([c,d,a]),orient([d,c,b])
            old=min(altitude(faces[i]),altitude(faces[j]));new=min(altitude(first),altitude(second))
            if new<=old+1e-10:continue
            faces[i],faces[j]=first,second;used.update(ids);changed=True
        if not changed:break
    return np.asarray(faces,dtype=np.int64)


def positive_number(value):
    try:
        number = float(str(value).strip().removesuffix('m').strip())
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def use_group(use):
    groups = {
        'apartments': 'apartments', 'residential': 'apartments',
        'house': 'house', 'terrace': 'house', 'dormitory': 'dormitory',
        'office': 'office', 'commercial': 'office', 'retail': 'retail',
        'school': 'education', 'university': 'education', 'college': 'education',
        'kindergarten': 'kindergarten', 'industrial': 'industrial',
        'warehouse': 'warehouse', 'hospital': 'hospital', 'hotel': 'hotel',
    }
    return groups.get(use)


def simplify_footprint(original, tags, policy=None):
    policy = policy or POLICY['footprints']
    area = original.area*10000
    tolerance = (policy['smallToleranceMeters'] if area < policy['smallAreaSquareMeters'] else
                 policy['largeToleranceMeters'] if area >= policy['largeAreaSquareMeters'] else
                 policy['ordinaryToleranceMeters'])/100
    if tags.get('name') or tags.get('building') in ['religious', 'temple', 'church', 'school', 'university']:
        tolerance = min(tolerance, policy['namedOrCulturalToleranceMeters']/100)
    while True:
        shape = original.simplify(tolerance, preserve_topology=True)
        serialized = rings(shape)
        shape = Polygon(serialized[0], serialized[1:])
        error = original.symmetric_difference(shape).area/original.area
        if (shape.is_valid and len(shape.interiors) == len(original.interiors)
                and error <= policy['maximumSymmetricDifferenceFraction']):
            break
        tolerance /= 2
        if tolerance < .0001:
            shape = original
            error = 0
            tolerance = 0
            break
    return shape, {'method': 'size-and-shape-constrained-simplification',
                   'toleranceMeters': round(tolerance*100, 6),
                   'symmetricDifferencePercent': round(error*100, 6),
                   'sourceAreaSquareMeters': round(area, 3),
                   'sourceVertices': sum(len(r.coords)-1 for r in [original.exterior, *original.interiors]),
                   'displayVertices': sum(len(r.coords)-1 for r in [shape.exterior, *shape.interiors]),
                   'interiorRings': len(shape.interiors)}


def height_donors(buildings, source_tags):
    result = defaultdict(list)
    for b in buildings:
        tags = source_tags.get(b.get('sourceRef'), {})
        group = use_group(tags.get('building', b.get('use')))
        height, levels = positive_number(tags.get('height')), positive_number(tags.get('building:levels'))
        if b['source'] != 'osm' or group is None or (height is None and levels is None):
            continue
        center = Polygon(b['rings'][0], b['rings'][1:]).centroid
        result[group].append({'sourceRef': b['sourceRef'], 'heightMeters': b['height'],
                              'kind': 'height' if height is not None else 'levels',
                              'center': (center.x, center.y)})
    return result


def estimate_height(building, tags, donors, policy=None):
    policy = policy or POLICY['heightEstimation']
    height, levels = positive_number(tags.get('height')), positive_number(tags.get('building:levels'))
    if height is not None or levels is not None:
        kind = 'height' if height is not None else 'levels'
        return building['height'], {'kind': kind, 'method': 'osm-tag', 'reference': building['sourceRef'],
            'value': tags['height' if kind == 'height' else 'building:levels'],
            **({'floorHeightMeters': policy['floorHeightMeters']} if kind == 'levels' else {})}
    group = use_group(tags.get('building', building.get('use')))
    fallback = {'kind': 'estimate', 'method': 'retained-legacy-fallback',
                'reason': 'unknown-use' if group is None else 'insufficient-same-use-neighbours',
                'useGroup': group, 'searchedRadiusMeters': policy['radiusMeters']}
    center = Polygon(building['rings'][0], building['rings'][1:]).centroid
    unique = {}
    for donor in donors.get(group, []):
        distance = math.dist((center.x, center.y), donor['center'])*100
        ref = donor['sourceRef']
        if ref == building.get('sourceRef') or distance > policy['radiusMeters']:
            continue
        row = {k: v for k, v in donor.items() if k != 'center'}
        row['distanceMeters'] = distance
        if ref not in unique or distance < unique[ref]['distanceMeters']:
            unique[ref] = row
    chosen = sorted(unique.values(), key=lambda r: (r['distanceMeters'], r['sourceRef']))[:policy['maximumSources']]
    if len(chosen) < policy['minimumDistinctSources']:
        return building['height'], fallback
    values = [p['heightMeters'] for p in chosen]
    if max(values)/min(values) > policy['maximumDonorHeightRatio']:
        fallback['reason'] = 'neighbour-heights-disagree'
        return building['height'], fallback
    chosen = [{**row, 'distanceMeters': round(row['distanceMeters'], 3)} for row in chosen]
    return round(statistics.median(values), 1), {'kind': 'estimate', 'method': 'nearby-use-median',
        'useGroup': group, 'radiusMeters': policy['radiusMeters'], 'donors': chosen}


def prepare(geography, snapshot):
    if geography.get('buildingQuality'):
        raise ValueError('Use a geography input before this quality pass')
    from prepare_geodata import geom_for, parts
    if geography['metersPerUnit'] != 100:
        raise ValueError('Building quality expects scene units of 100 metres')
    # A frozen input defines its own projection; do not silently use the live
    # public terrain's centre/bounds when preparing a historical candidate.
    cx, cy = geography['center']
    kx = math.cos(math.radians(cy))*1113.2
    project = lambda lon, lat: ((lon-cx)*kx, (lat-cy)*1113.2)
    clip = box(*geography['bounds'])
    result = copy.deepcopy(geography)
    by_ref = {f"osm/{e['type']}/{e['id']}": e for e in snapshot['elements']}
    source_tags = {ref: e.get('tags', {}) for ref, e in by_ref.items()}
    donors = height_donors(geography['buildings'], source_tags)
    source_parts, used_parts = {}, defaultdict(set)
    stats = Counter(); originals = []; changed_shapes = []; records = []
    for building in result['buildings']:
        if building['source'] != 'osm':
            continue
        previous = copy.deepcopy(building)
        ref = building['sourceRef'];element = by_ref[ref];tags = source_tags[ref]
        if ref not in source_parts:
            geom = geom_for(element, project=project, clip=clip)
            source_parts[ref] = list(parts(geom, 'Polygon')) if geom is not None else []
        old_shape = Polygon(building['rings'][0], building['rings'][1:])
        candidates = [(i, p) for i, p in enumerate(source_parts[ref]) if i not in used_parts[ref]]
        ranked = [(old_shape.intersection(p).area/old_shape.union(p).area, i, p) for i, p in candidates]
        assert ranked, f'Missing source geometry: {ref}'
        match, part, original = max(ranked, key=lambda r: (r[0], -r[1]))
        assert match > .1, f'Ambiguous source part: {ref}'
        used_parts[ref].add(part)
        shape, provenance = simplify_footprint(original, tags)
        building['rings'] = rings(shape)
        building['roofTriangles'] = roof_triangles(shape)
        building['footprintSource'] = {**provenance, 'reference': ref, 'sourcePart': part}
        building['height'], building['heightSource'] = estimate_height(building, tags, donors)
        building['mappedHeight'] = building['heightSource']['kind'] in ['height', 'levels']
        footprint_changed = building['rings'] != previous['rings']
        height_changed = building['height'] != previous['height']
        needs_geometry = footprint_changed or height_changed or bool(shape.interiors)
        building['qualityGeometry'] = needs_geometry
        if needs_geometry:
            building['meshRoofTriangles']=mesh_roof_triangles(building['rings'])
        stats['mappedBuildings'] += 1
        stats['footprintsChanged'] += footprint_changed
        stats['heightsChanged'] += height_changed
        stats['buildingsWithInteriors'] += bool(shape.interiors)
        stats['geometryChanges'] += needs_geometry
        stats[building['heightSource']['method']] += 1
        if needs_geometry:
            originals.append(previous)
            changed_shapes.append(shape)
        records.append({'id': building['id'], 'sourceRef': ref, 'sourcePart': part,
            'footprintChanged': footprint_changed, 'heightBeforeMeters': previous['height'],
            'heightAfterMeters': building['height'], 'heightMethod': building['heightSource']['method'],
            **provenance})
    spatial = STRtree([p.buffer(.1) for p in changed_shapes])
    hidden_trees = [i for i, tree in enumerate(result['trees']) if len(spatial.query(Point(tree[:2]), predicate='intersects'))]
    result['buildingQuality'] = {'id': POLICY['id'], 'sourceFile': str(SOURCE.relative_to(ROOT)),
        'sourceHash': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'snapshotTimestamp': snapshot.get('osm3s', {}).get('timestamp_osm_base'),
        'statistics': dict(stats), 'originalBuildings': originals,
        'hiddenTreeIndices': hidden_trees, 'records': records}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, default=ROOT/'work/geodata/osm.json')
    args = parser.parse_args()
    result = prepare(json.loads(args.input.read_text()), json.loads(args.snapshot.read_text()))
    result['buildingQuality']['snapshotSha256'] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print(json.dumps(result['buildingQuality']['statistics'], ensure_ascii=False, indent=2))
