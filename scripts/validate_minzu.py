"""Audit Minzu source coverage, shared materials and decoded road/marking meshes."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import DracoPy
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]


def validate_minzu():
    plan = json.loads((ROOT/'data/minzu-plan.json').read_text())
    source = json.loads((ROOT/'data/minzu-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    report = json.loads((ROOT/'public/data/overview.json').read_text())['minzuAvenue']
    digest = hashlib.sha256((ROOT/'data/minzu-plan.json').read_bytes()).hexdigest()
    for path, fingerprint in plan['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Stale Minzu plan: {path}'
    assert report['planHash'] == digest
    assert report['geometry']['minRoadClearanceMeters'] > 1.5
    assert report['geometry']['maxDisplayGrade'] < .121
    assert report['geometry']['nanhuHeightRangeMeters'] < .00001
    assert plan['sceneCenter'] == geo['center'] and plan['bbox'] == geo['bbox']
    selected = {e['id']: e for e in source['elements'] if e['id'] in source['selectedIds']}
    cx,cy = geo['center']; kx = 1113.2*math.cos(math.radians(cy))
    def xy(p): return ((p['lon']-cx)*kx,(p['lat']-cy)*1113.2)
    retained = defaultdict(list)
    for route in plan['paths'] + plan['tunnels'] + plan['omittedPaths']:
        e = selected[route['osmId']]
        assert e['tags'] == route['tags']
        retained[e['id']].append(LineString(route.get('sourcePoints',route['points'])))
        if 'sourcePoints' in route:
            assert LineString(route['sourcePoints']).hausdorff_distance(LineString(route['points'])) < .02501
    for identity,e in selected.items():
        original = LineString([xy(p) for p in e['geometry']]).intersection(box(*geo['bounds']))
        if original.is_empty: continue
        actual = unary_union(retained[identity])
        assert original.hausdorff_distance(actual) < .00001, f'Changed Minzu source alignment: {identity}'
        assert abs(original.length-sum(p.length for p in retained[identity])) < .0001, f'Missing/duplicate Minzu segment: {identity}'
    assert all(not r['frontage'] and r['lanes']==3 for r in plan['paths'])
    assert len(plan['omittedPaths'])==44 and all(r['tags']['name']=='民族大道辅路' for r in plan['omittedPaths'])
    replacements = [r['roadIndex'] for r in plan['paths']+plan['omittedPaths']]
    assert sorted(replacements) == sorted(plan['replacedRoads'])
    assert len(set(replacements)) == len(replacements)
    assert set(replacements) == {i for i,r in enumerate(geo['roads']) if r['name'] in ['民族大道','民族大道辅路']}
    buildings = [Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']]
    building_index = STRtree(buildings)
    for route in plan['paths']:
        footprint = LineString(route['points']).buffer(route['width']/2, cap_style=2)
        for i in building_index.query(footprint, predicate='intersects'):
            assert footprint.intersection(buildings[i]).area < .0001, 'Minzu carriageway overlaps a building'
    profiles = []
    for filename in ['nanning-city.glb','nanning-city-mobile.glb']:
        raw = (ROOT/'public/models'/filename).read_bytes()
        size = struct.unpack_from('<I',raw,12)[0]
        model = json.loads(raw[20:20+size]); binary = 28+size
        nodes = model['nodes']
        parent = next(n for n in nodes if n.get('name') == 'MinzuAvenue')
        roads = next(n for n in nodes if n.get('name') == 'Roads')
        assert nodes.index(parent) in roads.get('children',[]), 'Minzu ignores the roads layer'
        assert parent['extras']['planHash'] == digest, 'Stale Minzu export'
        descendants = []
        def visit(n):
            descendants.append(n)
            for i in n.get('children',[]): visit(nodes[i])
        visit(parent)
        assert any(n.get('name') == 'MinzuAvenue_Details' for n in descendants)
        counts = {'structure':0,'details':0}; asphalt = []; marking_faces=collapsed=0; lake_heights=[]
        minzu_materials = set()
        for n in descendants:
            if 'mesh' not in n: continue
            for p in model['meshes'][n['mesh']]['primitives']:
                counts['details' if n['name'].startswith('MinzuAvenue_Details') else 'structure'] += model['accessors'][p['indices']]['count']//3
                mat = model['materials'][p['material']]['name']
                minzu_materials.add(p['material'])
                if mat not in ['Qingxiang sage asphalt','Qingxiang lane markings']: continue
                ext = p['extensions']['KHR_draco_mesh_compression']
                view = model['bufferViews'][ext['bufferView']]
                start = binary+view.get('byteOffset',0)
                mesh = DracoPy.decode(raw[start:start+view['byteLength']])
                assert np.isfinite(mesh.points).all(), 'Nonfinite Minzu vertex'
                faces = mesh.points[mesh.faces]
                area = np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)/2
                if mat == 'Qingxiang lane markings':
                    marking_faces += len(faces); collapsed += int((area<1e-10).sum())
                else:
                    asphalt.extend(Polygon(f[:,[0,2]]) for f in faces if Polygon(f[:,[0,2]]).area > 1e-10)
                    west,east,south,north=plan['assumptions']['nanhuLevelExtent']
                    points=mesh.points
                    inside=(points[:,0]>west+.15)&(points[:,0]<east-.15)&(-points[:,2]>south)&(-points[:,2]<north)
                    lake_heights.extend(points[inside,1])
        qingxiang = next(n for n in nodes if n.get('name') == 'Landmark_qingxiang-viaduct')
        qingxiang_materials = {p['material'] for p in model['meshes'][qingxiang['mesh']]['primitives']}
        assert len(minzu_materials & qingxiang_materials) >= 3, 'Road surface materials were duplicated instead of shared'
        assert 5_000 < counts['structure'] < 160_000 and 1_000 < counts['details'] < 50_000
        assert marking_faces > 1000 and collapsed / marking_faces < .01, 'Compression erased Minzu road markings'
        index = STRtree(asphalt)
        assert len(lake_heights)>20 and np.ptp(lake_heights)*100 < .05, 'Nanhu exported main road has a visible slope'
        rendered=unary_union([LineString(r['points']).buffer(r['width']/2+.025) for r in plan['paths']])
        omitted_probes=0
        for route in plan['omittedPaths']:
            line=LineString(route['points'])
            for t in [.25,.5,.75]:
                point=line.interpolate(t,normalized=True)
                if rendered.covers(point):continue
                flipped=Point(point.x,-point.y)
                assert flipped.distance(asphalt[index.nearest(flipped)])>.01, 'Omitted side road is still rendered'
                omitted_probes+=1
        assert omitted_probes>40, 'Missing side-road exclusion coverage'
        max_distance = 0.
        for route in plan['paths']:
            for x,y in route['points']:
                point = Point(x,-y)
                distance = point.distance(asphalt[index.nearest(point)])
                max_distance = max(max_distance,distance)
                assert distance < .012, f'Exported Minzu surface misses source way {route["osmId"]}'
        print(f'{filename} Minzu: {counts}; markings collapsed {collapsed}/{marking_faces}; source gap {max_distance*100:.3f} m; Nanhu height range {np.ptp(lake_heights)*100:.4f} m; {omitted_probes} side-road exclusion probes',flush=True)
        profiles.append(counts)
    assert profiles[0]['structure'] == profiles[1]['structure']
    assert profiles[1]['details'] < profiles[0]['details']
    assert report['smoothFittings']['lamps'] == 0 < report['detailFittings']['lamps']
    print('PASS: Minzu provenance, six-lane main road, omitted side roads, level Nanhu crossing, terrain clearance and decoded markings.',flush=True)


if __name__ == '__main__': validate_minzu()
