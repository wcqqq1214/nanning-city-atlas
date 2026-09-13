#!/usr/bin/env python3
"""Freeze an auditable city baseline without importing or rebuilding Blender."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_glb(path):
    with path.open('rb') as source:
        magic, version, length = struct.unpack('<4sII', source.read(12))
        assert magic == b'glTF' and version == 2 and length == path.stat().st_size
        count, kind = struct.unpack('<I4s', source.read(8))
        assert kind == b'JSON'
        model = json.loads(source.read(count))
    accessors = model['accessors']
    triangles = sum(
        accessors[p['indices']]['count'] // 3
        for mesh in model['meshes'] for p in mesh['primitives']
        if p.get('mode', 4) == 4
    )
    return dict(bytes=length, triangles=triangles, meshes=len(model['meshes']),
                materials=len(model.get('materials', [])), sha256=sha256(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freeze-assets', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    # A baseline is immutable: never quietly overwrite the before state.
    if output.exists():
        parser.error(f'Baseline directory already exists: {output}')
    output.mkdir(parents=True)
    overview = json.loads((ROOT / 'public/data/overview.json').read_text())
    assets = [ROOT / 'blender/nanning-city.blend']
    assets += list((ROOT / 'public/models').glob('*.glb'))
    assets += [ROOT / 'public/data' / name for name in
               ('geography.json', 'terrain.json', 'landmarks.json', 'overview.json')]
    sources = [ROOT / 'data/landmarks.json', ROOT / 'data/region.json']
    sources += sorted((ROOT / 'blender').glob('*.py'))
    sources += sorted((ROOT / 'scripts').glob('*.py'))
    sources += sorted((ROOT / 'lib/city').glob('*.ts'))
    sources += sorted((ROOT / 'data').rglob('*.json'))
    files = {str(p.relative_to(ROOT)): dict(bytes=p.stat().st_size, sha256=sha256(p))
             for p in sorted(set(assets + sources))}
    if args.freeze_assets:
        for source in assets:
            target = output / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            assert sha256(target) == files[str(source.relative_to(ROOT))]['sha256']
    manifest = {
        'schemaVersion': 1,
        'capturedAt': datetime.now(timezone.utc).isoformat(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTree': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True).splitlines(),
        'assetsFrozen': args.freeze_assets,
        'models': {p.name: inspect_glb(p) for p in assets if p.suffix == '.glb'},
        'display': {k: overview[k] for k in ('metersPerUnit', 'terrainExaggeration', 'buildingExaggeration', 'osmTimestamp', 'stats')},
        'files': files,
        'note': 'Source and asset hashes describe this exact capture, including any listed uncommitted changes. GLB accessor counts are not a browser performance benchmark.',
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'models': manifest['models'], 'assetsFrozen': args.freeze_assets}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
