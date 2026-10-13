"""Independently prove split assets exactly partition each verified city model."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from scope_city import CityGLB

ROOT = Path(__file__).resolve().parents[1]


def signatures(city):
    result = Counter()
    for mesh in city.doc['meshes']:
        for p in mesh['primitives']:
            payload = city.payloads[p['extensions']['KHR_draco_mesh_compression']['bufferView']]
            material = json.dumps(city.doc['materials'][p['material']], sort_keys=True)
            layout = {
                'mode': p.get('mode', 4),
                'indices': city.doc['accessors'][p['indices']],
                'attributes': {k: city.doc['accessors'][i] for k, i in p['attributes'].items()},
                'dracoAttributes': p['extensions']['KHR_draco_mesh_compression']['attributes'],
            }
            result[(mesh['name'], material, hashlib.sha256(payload).hexdigest(), json.dumps(layout, sort_keys=True))] += 1
    return result


def validate(root=ROOT, directory=None, manifest=None):
    directory = directory or root/'public/models/stream'
    manifest = manifest or json.loads((root/'public/data/city-streaming.json').read_text())
    assert manifest['version'] == 1 and manifest['units'] == '100m'
    assert set(manifest['profiles']) == {'detail', 'smooth'}
    for profile, data in manifest['profiles'].items():
        filename = 'nanning-city.glb' if profile == 'detail' else 'nanning-city-mobile.glb'
        source = CityGLB(root/'public/models'/filename)
        assert source.sha == data['sourceSha256'] and source.bytes == data['sourceBytes']
        expected = signatures(source)
        actual = Counter()
        ids = set()
        for asset in [data['base'], *data['details']]:
            assert asset['id'] not in ids
            ids.add(asset['id'])
            assert asset['url'] == f"/models/stream/{profile}/{asset['id']}.glb"
            city = CityGLB(directory/profile/f"{asset['id']}.glb")
            assert city.sha == asset['sha256'] and city.bytes == asset['bytes']
            assert len(city.doc['nodes']) == len(source.doc['nodes'])
            assert city.doc.get('scenes') == source.doc.get('scenes')
            assert city.doc.get('scene') == source.doc.get('scene')
            assert city.doc['nodes'] == source.doc['nodes'] or all(
                {k: v for k, v in n.items() if k != 'mesh'} == {k: v for k, v in s.items() if k != 'mesh'}
                for n, s in zip(city.doc['nodes'], source.doc['nodes']))
            for node, original in zip(city.doc['nodes'], source.doc['nodes']):
                if 'mesh' in node:
                    assert 'mesh' in original
                    assert city.doc['meshes'][node['mesh']]['name'] == source.doc['meshes'][original['mesh']]['name']
            actual.update(signatures(city))
            assert asset['geometryBytes'] > 0
        assert actual == expected, f'{profile}: split changed, duplicated or lost source geometry/materials'
        base = CityGLB(directory/profile/'base.glb')
        base_signatures = signatures(base)
        for signature, count in expected.items():
            if signature[0].startswith(('Terrain', 'Water', 'Plinth', 'Buildings')):
                assert base_signatures[signature] == count, 'Base lost continuous landscape or building bodies'
        source_landmarks = {n[0] for n in expected if n[0].startswith('Landmark_')}
        assert source_landmarks <= {n[0] for n in base_signatures}, 'Base lost a landmark entirely'
        assert data['base']['bytes'] < data['sourceBytes']*.9, 'Base must reduce initial download by at least 10%'
    print('PASS: streaming base preserves continuous landscape; all detail payloads partition the source exactly.')


if __name__ == '__main__':
    validate()
