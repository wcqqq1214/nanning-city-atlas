"""Partition verified city GLBs into a continuous base and additive near detail.

Never decimates or re-encodes geometry. Terrain, water, building bodies and
transport surfaces remain in the base; complete compressed detail primitives
are copied into spatial/landmark assets. Their union must equal the source.
"""
import copy
import json
from pathlib import Path
import re
import shutil
import tempfile

from scope_city import CityGLB

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'detail': 'nanning-city.glb', 'smooth': 'nanning-city-mobile.glb'}
# Structural roofs, façades, bridge decks/supports, terrain and water stay ready.
ORNAMENT = re.compile(r'mullions|lettering|raised tile ridges|ochre eave trim|'
    r'jade eave edges|white limestone mouldings|pale balustrade|garden fittings|'
    r'field markings|scoreboard|brushed aluminium frames|aluminium frames', re.I)


def detail_key(name, material, bounds):
    if name.startswith('Landmark_'):
        return 'landmark-' + name.removeprefix('Landmark_') if ORNAMENT.search(material) else None
    if (name.startswith(('Railway_Details_', 'RiverBridge_Details_', 'QingxiangViaduct_Details',
                         'ZhuxiInterchange_Details')) or
        name.startswith(('GroundRoads_', 'ElevatedRoads_', 'MinzuAvenue_')) and 'markings' in material or
        name.startswith('Railways_') and material in ['Railway polished rail heads', 'Railway overhead fittings']):
        # Source primitives already use bounded spatial batches. Keep them
        # intact; grouping by their center adds no new seams or quantization.
        x, y = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
        return f'transport-{int(x//40)}-{int(y//40)}'
    return None


def primitive_records(city):
    for mi, mesh in enumerate(city.doc['meshes']):
        for pi, primitive in enumerate(mesh['primitives']):
            accessor = city.doc['accessors'][primitive['attributes']['POSITION']]
            lo, hi = accessor['min'], accessor['max']
            yield mi, pi, mesh['name'], primitive, [lo[0], -hi[2], hi[0], -lo[2]]


def build(root=ROOT):
    public = root/'public'
    manifest_path = public/'data/city-streaming.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'profiles': {}}
    manifest = {'version': 1, 'units': '100m', 'profiles': {}}
    with tempfile.TemporaryDirectory(prefix='city-stream-', dir=root/'work') as temporary:
        stage = Path(temporary)
        for profile, filename in MODELS.items():
            source = CityGLB(public/'models'/filename)
            buckets = {'base': []}
            for mi, pi, name, primitive, bounds in primitive_records(source):
                material = source.doc['materials'][primitive['material']]['name']
                key = detail_key(name, material, bounds) or 'base'
                buckets.setdefault(key, []).append((mi, pi, bounds))
            assets = {}
            for key, records in buckets.items():
                city = copy.deepcopy(source)
                selected = {(mi, pi) for mi, pi, _ in records}
                for mi, mesh in enumerate(city.doc['meshes']):
                    mesh['primitives'] = [p for pi, p in enumerate(mesh['primitives']) if (mi, pi) in selected]
                path = stage/profile/f'{key}.glb'
                result = city.write(path)
                bounds = [min(b[k] for _, _, b in records) for k in [0, 1]] + [max(b[k] for _, _, b in records) for k in [2, 3]]
                # Flat normals expand indexed faces in the browser; budget the
                # decoded layout rather than assuming download bytes equal RAM.
                cost = 0
                for mi, pi, _ in records:
                    p = source.doc['meshes'][mi]['primitives'][pi]
                    count = source.doc['accessors'][p['indices']]['count']
                    vertices = source.doc['accessors'][p['attributes']['POSITION']]['count']
                    cost += count*24 if 'NORMAL' not in p['attributes'] else vertices*24+count*4
                assets[key] = {'id': key, 'url': f'/models/stream/{profile}/{key}.glb',
                    'bytes': result['bytes'], 'sha256': result['sha256'], 'bounds': bounds,
                    'geometryBytes': cost, 'triangles': result['triangles'],
                    'layer': 'buildings' if key.startswith('landmark-') else 'roads'}
                if key.startswith('transport-'):
                    assets[key]['layers'] = sorted({'railways' if source.doc['meshes'][mi]['name'].startswith('Railway') else 'roads' for mi, _, _ in records})
            manifest['profiles'][profile] = {'sourceSha256': source.sha, 'sourceBytes': source.bytes,
                'base': assets.pop('base'), 'details': list(assets.values())}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        from check_city_streaming import validate
        validate(root, stage, manifest)
        destination = public/'models/stream'
        destination.mkdir(parents=True, exist_ok=True)
        for profile in MODELS:
            shutil.copytree(stage/profile, destination/profile, dirs_exist_ok=True)
        manifest_path.write_bytes((stage/'manifest.json').read_bytes())
        # Remove only formerly published generator-owned assets after the new
        # partition has passed validation and its files are in place.
        current_urls = {a['url'] for p in manifest['profiles'].values() for a in [p['base'], *p['details']]}
        for p in previous['profiles'].values():
            for asset in [p['base'], *p['details']]:
                url = asset['url']
                if url not in current_urls and re.fullmatch(r'/models/stream/(detail|smooth)/[a-z0-9-]+\.glb', url):
                    (public/url.lstrip('/')).unlink(missing_ok=True)
    print(json.dumps({k: {'baseBytes': v['base']['bytes'], 'sourceBytes': v['sourceBytes'],
        'detailAssets': len(v['details'])} for k, v in manifest['profiles'].items()}, indent=2))


if __name__ == '__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    build()
