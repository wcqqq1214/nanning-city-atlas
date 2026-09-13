"""Independently compare complete GLB geometry, material ownership and normals."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from validate_cultural_landmarks import glb


def rows(points, faces, normals=None):
    values = points if normals is None else np.concatenate([points, normals], axis=1)
    values = values.astype('<f4')[faces]
    for face in values:
        # Position-first canonical corner order, independent of the normal data.
        corners = [tuple(face[i, :3]) for i in range(3)]
        start = min(range(3), key=lambda i: corners[i:]+corners[:i])
        yield np.ascontiguousarray(np.roll(face, -start, axis=0)).tobytes()


def check(before_path, after_path):
    before, decode_before = glb(before_path); after, decode_after = glb(after_path)
    for key in ['nodes', 'scenes', 'scene', 'materials', 'textures', 'images', 'samplers']:
        assert before.get(key) == after.get(key), f'{key} changed'
    assert len(before['meshes']) == len(after['meshes'])
    result = {'triangles': 0, 'flatFaces': 0, 'maximumFlatNormalDifferenceDegrees': 0., 'meshes': []}
    for old, new in zip(before['meshes'], after['meshes']):
        old_metadata = {k: v for k, v in old.items() if k != 'primitives'}
        assert old_metadata == {k: v for k, v in new.items() if k != 'primitives'}
        original = Counter(); original_flat = Counter(); remaining = Counter(); flat = Counter(); triangle_count = 0
        for primitive in old['primitives']:
            data = decode_before(primitive); material = primitive.get('material', -1)
            if data.normals is None:
                original_flat.update((material, row) for row in rows(data.points, data.faces))
            else:
                original.update((material, row) for row in rows(data.points, data.faces, data.normals))
            triangle_count += len(data.faces)
        remaining.update(original)
        explicit = Counter()
        for primitive in new['primitives']:
            data = decode_after(primitive); material = primitive.get('material', -1)
            if data.normals is None:
                flat.update((material, row) for row in rows(data.points, data.faces))
            else:
                explicit.update((material, row) for row in rows(data.points, data.faces, data.normals))
        assert not explicit-original, 'Explicit normals or geometry changed'
        remaining.subtract(explicit); remaining = +remaining
        # A second scoped pass may start from an already compacted asset.
        # Preserve its missing-normal faces exactly, then account separately for
        # explicit faces newly converted by this pass and their normal error.
        expected_flat = original_flat.copy(); maximum = 0.
        for (material, row), count in remaining.items():
            values = np.frombuffer(row, dtype='<f4').reshape(3, 6).astype(float)
            positions, normals = values[:, :3], values[:, 3:]
            normal = np.cross(positions[1]-positions[0], positions[2]-positions[0])
            length = np.linalg.norm(normal)
            assert length > 1e-15, 'A degenerate face lost its explicit normal'
            angle = np.degrees(np.arccos(np.clip((normals @ (normal/length))/np.linalg.norm(normals, axis=1), -1, 1)))
            maximum = max(maximum, float(angle.max()))
            expected_flat[(material, positions.astype('<f4').tobytes())] += count
        assert flat == expected_flat, 'Face positions, winding, count or material changed'
        assert maximum <= .5+1e-7, 'Flat normal deviation exceeds acceptance gate'
        assert sum(explicit.values())+sum(flat.values()) == triangle_count
        result['triangles'] += triangle_count; result['flatFaces'] += sum(flat.values())
        result['maximumFlatNormalDifferenceDegrees'] = max(result['maximumFlatNormalDifferenceDegrees'], maximum)
        result['meshes'].append({'name': old.get('name'), 'triangles': triangle_count, 'flatFaces': sum(flat.values())})
    result['status'] = 'all geometry, material ownership, hierarchy and explicit normals preserved; flat deviation bounded; visual checks separate'
    result['inputs'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in [before_path, after_path, Path(__file__)]}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); report = check(args.before, args.after)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print({k: v for k, v in report.items() if k not in ['inputs', 'meshes']}, flush=True)
