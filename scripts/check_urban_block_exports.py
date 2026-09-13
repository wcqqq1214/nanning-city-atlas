"""Check exported scope, shared slab geometry and strict existing size budgets."""
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from validate_cultural_landmarks import glb, terrain_peak

ROOT = Path(__file__).resolve().parents[1]


def meshes(path):
    raw = path.read_bytes()
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20+size])
    binary = 28+size
    result = {}
    for node in doc['nodes']:
        if 'mesh' not in node:
            continue
        signatures = []
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            view = doc['bufferViews'][primitive['extensions']['KHR_draco_mesh_compression']['bufferView']]
            start = binary+view.get('byteOffset', 0)
            material = doc['materials'][primitive['material']]
            data = json.dumps(material, sort_keys=True).encode()+raw[start:start+view['byteLength']]
            signatures.append(hashlib.sha256(data).hexdigest())
        transform = {k: node[k] for k in ['matrix', 'translation', 'scale', 'rotation'] if k in node}
        result[node['name']] = [signatures, transform]
    triangles = sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])
    return result, {'bytes': len(raw), 'triangles': triangles, 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    output = {}
    building_variants = []
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    pilot = [b for b in geo['buildings'] if b.get('blockId')]
    support = {r['id']:r for r in json.loads((ROOT/'work/urban-structure/p1/support.json').read_text())}
    for profile, suffix, budget in [('detail', '', 26_000_000), ('smooth', '-mobile', 18_000_000)]:
        path = Path(f'public/models/nanning-city{suffix}.glb')
        old, before = meshes(ROOT/'work/urban-structure/baseline-73edbb7'/path)
        new, after = meshes(ROOT/path)
        changed = [name for name in old.keys() | new.keys() if old.get(name) != new.get(name)]
        unexpected = [n for n in changed if not n.startswith('Buildings_')]
        output[profile] = {'before': before, 'after': after, 'changedMeshNodes': sorted(changed),
                           'unexpectedChanges': sorted(unexpected), 'identicalMeshNodes': len(new)-len(changed),
                           'byteDelta': after['bytes']-before['bytes'], 'triangleDelta': after['triangles']-before['triangles']}
        assert after['bytes'] < budget, f'{profile} exceeds existing size budget'
        assert not unexpected, f'{profile}: changed unrelated geometry/materials: {unexpected}'
        building_variants.append({k:v for k,v in new.items() if k.startswith('Buildings_')})
        doc, decode = glb(ROOT/path)
        site = unary_union([Polygon(b['rings'][0]) for b in pilot])
        west, south, east, north = site.bounds
        terrain, roofs = [], []
        for node in doc['nodes']:
            name = node.get('name', '')
            if 'mesh' not in node or not name.startswith(('Terrain_', 'Buildings_')):
                continue
            for p in doc['meshes'][node['mesh']]['primitives']:
                accessor = doc['accessors'][p['attributes']['POSITION']]
                low, high = accessor['min'], accessor['max']
                if low[0] > east or high[0] < west or -high[2] > north or -low[2] < south:
                    continue
                if name.startswith('Buildings_') and doc['materials'][p['material']]['name'] != 'Roof':
                    continue
                mesh = decode(p)
                (terrain if name.startswith('Terrain_') else roofs).append(mesh.points[mesh.faces])
        terrain, roofs = np.concatenate(terrain), np.concatenate(roofs)
        roof_shapes = [Polygon(t[:, [0, 2]]*np.array([1, -1])) for t in roofs]
        from shapely.strtree import STRtree
        roof_tree = STRtree(roof_shapes)
        measured = []
        for b in pilot:
            footprint = Polygon(b['rings'][0], b['rings'][1:])
            peak = terrain_peak(terrain, footprint)
            ids = roof_tree.query(footprint, predicate='intersects')
            coverage = unary_union([roof_shapes[i] for i in ids]).intersection(footprint).area/footprint.area
            assert coverage > .95, f"{b['id']}: exported roof footprint incomplete"
            actual_top = float(np.median(roofs[ids, :, 1]))
            assert abs(actual_top-support[b['id']]['top']) < .005, 'Roof height changed in export'
            assert support[b['id']]['floor'] > peak, 'Terrain enters the slab floor'
            measured.append({'id': b['id'], 'roofCoverage': round(coverage, 5),
                             'floorClearanceMeters': round((support[b['id']]['floor']-peak)*100, 3),
                             'exportedTopMeters': round(actual_top*100, 3)})
        output[profile]['slabs'] = measured
    assert building_variants[0] == building_variants[1], 'Building geometry differs between quality tiers'
    output['identicalBuildingsAcrossQualities'] = True
    (ROOT/'work/urban-structure/p1/exports.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
