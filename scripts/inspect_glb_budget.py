"""Attribute actual GLB storage to encoded mesh payloads without decoding them."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', raw)
    assert magic == 0x46546C67 and version == 2 and length == len(raw)
    size, kind = struct.unpack_from('<II', raw, 12)
    assert kind == 0x4E4F534A
    doc = json.loads(raw[20:20 + size])
    names = {}
    for node in doc.get('nodes', []):
        if 'mesh' in node:
            names.setdefault(node['mesh'], []).append(node.get('name', 'unnamed'))
    used = set()
    records = []
    for index, mesh in enumerate(doc.get('meshes', [])):
        views = set()
        triangles = 0
        for primitive in mesh['primitives']:
            count = doc['accessors'][primitive['indices']]['count'] if 'indices' in primitive else doc['accessors'][primitive['attributes']['POSITION']]['count']
            if primitive.get('mode', 4) == 4:
                triangles += count // 3
            draco = primitive.get('extensions', {}).get('KHR_draco_mesh_compression')
            if draco:
                views.add(draco['bufferView'])
            else:
                accessors = list(primitive['attributes'].values())
                if 'indices' in primitive:
                    accessors.append(primitive['indices'])
                for accessor in accessors:
                    entry = doc['accessors'][accessor]
                    if 'bufferView' in entry:
                        views.add(entry['bufferView'])
                    for field in ['indices', 'values']:
                        if field in entry.get('sparse', {}):
                            views.add(entry['sparse'][field]['bufferView'])
        # Count shared payload only once; list every referring node separately.
        exclusive = views - used
        used.update(views)
        records.append({'mesh': index, 'nodes': names.get(index, []), 'triangles': triangles,
                        'payloadBytes': sum(doc['bufferViews'][v]['byteLength'] for v in exclusive),
                        'bufferViews': sorted(views)})
    mesh_bytes = sum(r['payloadBytes'] for r in records)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'fileBytes': len(raw), 'jsonChunkBytes': size, 'meshPayloadBytes': mesh_bytes,
            'otherBytes': len(raw) - mesh_bytes,
            'meshes': sorted(records, key=lambda r: r['payloadBytes'], reverse=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', type=Path, nargs='+')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = {'models': [inspect(path) for path in args.models]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for model in result['models']:
        print(model['path'], model['fileBytes'], 'bytes; mesh payload', model['meshPayloadBytes'])
        for record in model['meshes'][:12]:
            print(record['payloadBytes'], record['triangles'], ', '.join(record['nodes']))


if __name__ == '__main__':
    main()
