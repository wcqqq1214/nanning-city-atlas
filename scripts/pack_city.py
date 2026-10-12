"""Pack regenerated full-city flat terrain before applying the display scope.

Retains exact decoded positions, winding and face counts. Only normals within
0.5 degrees of their face normal may use the browser's flat-normal convention.
The existing packer checks every encoded face, including explicit custom normals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from pack_flat_surfaces import pack

ROOT = Path(__file__).resolve().parents[1]
FILES = {'detail': 'nanning-city.glb', 'smooth': 'nanning-city-mobile.glb'}


def prepare(root, resources):
    root = root.resolve()
    manifest_path = root/'data/packing.json'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if all(sha(root/'models'/filename) == previous['models'][profile]['outputSha256']
               for profile, filename in FILES.items()):
            print('Full-city models already packed', flush=True)
            return
    overview = json.loads((root/'data/overview.json').read_text())
    reports = {}
    (root/'raw-models').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='packing-', dir=root) as temporary:
        stage = Path(temporary)
        for profile, filename in FILES.items():
            source = root/'raw-models'/filename
            shutil.copy2(root/'models'/filename, source)
            output = stage/filename
            pack(source, output, resources)
            report = json.loads(output.with_suffix('.report.json').read_text())
            report['output'] = str(root/'models'/filename)
            reports[profile] = report
            overview['models'][profile]['bytes'] = output.stat().st_size
        # Publish the pair only after both packer audits have succeeded.
        for filename in FILES.values():
            (stage/filename).replace(root/'models'/filename)
    (root/'data/overview.json').write_text(json.dumps(overview, ensure_ascii=False, separators=(',', ':')))
    manifest_path.write_text(json.dumps({'models': reports}, indent=2)+'\n')
    print('Packed both full-city models; scoped geometry validation remains required', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT/'work/full-city')
    parser.add_argument('--blender-resources', type=Path, default=Path('/Applications/Blender.app/Contents/Resources'))
    args = parser.parse_args()
    prepare(args.root, args.blender_resources)
