"""Build an opt-in GLB candidate with shared positions on already-flat faces.

The glTF loader uses derivative flat shading when NORMAL is absent. Faces with
custom normals remain explicit. Every face, position and winding is checked
after encoding; this never writes over the input or accepts visual equivalence.
"""
import argparse
import copy
import ctypes as c
import hashlib
import json
from pathlib import Path
import struct

import DracoPy
import numpy as np


def face_signatures(points, faces, normals=None):
    values = points if normals is None else np.concatenate([points, normals], axis=1)
    values = values.astype('<f4')[faces]
    width = values.shape[1]*values.shape[2]
    rows = [np.ascontiguousarray(np.roll(values, i, axis=1)).reshape(-1, width).view(f'V{width*4}').ravel() for i in range(3)]
    return sorted(min(bytes(a), bytes(b), bytes(d)) for a, b, d in zip(*rows))


def flat_faces(points, normals, faces, maximum_degrees):
    triangles = points.astype(float)[faces]
    cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    length = np.linalg.norm(cross, axis=1)
    # Degenerate faces retain their explicit attributes and indices.
    valid = length > 1e-15
    expected = cross/np.maximum(length[:, None], 1e-30)
    corner = normals.astype(float)[faces]
    cosine = np.einsum('ij,ikj->ik', expected, corner)/np.maximum(np.linalg.norm(corner, axis=2), 1e-30)
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1))).max(axis=1)
    return valid & (angles <= maximum_degrees), angles


class Encoder:
    def __init__(self, blender_resources):
        self.base = c.CDLL(str(blender_resources/'lib/libdraco.dylib'), mode=c.RTLD_GLOBAL)
        libraries = sorted(blender_resources.glob('*/scripts/addons_core/io_scene_gltf2/libbf_intern_draco_bridge.dylib'))
        if len(libraries) != 1:
            raise ValueError('Expected one bundled Blender Draco bridge')
        self.dll = c.CDLL(str(libraries[0]))
        signatures = [
            ('encoderCreate', c.c_void_p, [c.c_uint32]), ('encoderRelease', None, [c.c_void_p]),
            ('encoderSetCompressionLevel', None, [c.c_void_p, c.c_uint32]),
            ('encoderSetQuantizationBits', None, [c.c_void_p]+[c.c_uint32]*5),
            ('encoderSetIndices', None, [c.c_void_p, c.c_size_t, c.c_uint32, c.c_void_p]),
            ('encoderSetAttribute', c.c_uint32, [c.c_void_p, c.c_char_p, c.c_size_t, c.c_char_p, c.c_void_p, c.c_bool]),
            ('encoderEncode', c.c_bool, [c.c_void_p, c.c_uint8]),
            ('encoderGetByteLength', c.c_uint64, [c.c_void_p]), ('encoderCopy', None, [c.c_void_p, c.c_void_p]),
        ]
        for name, result, args in signatures:
            method = getattr(self.dll, name); method.restype = result; method.argtypes = args

    def encode(self, points, faces, normals=None):
        attributes = {'POSITION': np.ascontiguousarray(points, dtype='<f4')}
        if normals is not None:
            attributes['NORMAL'] = np.ascontiguousarray(normals, dtype='<f4')
        indices = np.ascontiguousarray(faces, dtype='<u4')
        handle = self.dll.encoderCreate(len(points))
        try:
            ids = {key: self.dll.encoderSetAttribute(handle, key.encode(), 5126, b'VEC3', value.ctypes.data, False)
                   for key, value in attributes.items()}
            self.dll.encoderSetIndices(handle, 5125, indices.size, indices.ctypes.data)
            self.dll.encoderSetCompressionLevel(handle, 10)
            self.dll.encoderSetQuantizationBits(handle, 0, 0, 0, 0, 0)
            if not self.dll.encoderEncode(handle, 0):
                raise ValueError('Draco encoding failed')
            buffer = c.create_string_buffer(self.dll.encoderGetByteLength(handle))
            self.dll.encoderCopy(handle, buffer)
            decoded = DracoPy.decode(buffer.raw)
            assert face_signatures(points, faces, normals) == face_signatures(decoded.points, decoded.faces, decoded.normals)
            return buffer.raw, ids, decoded
        finally:
            self.dll.encoderRelease(handle)


def referenced_views(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'bufferView':
                yield child
            else:
                yield from referenced_views(child)
    elif isinstance(value, list):
        for child in value:
            yield from referenced_views(child)


def remap_views(value, mapping):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'bufferView':
                value[key] = mapping[child]
            else:
                remap_views(child, mapping)
    elif isinstance(value, list):
        for child in value:
            remap_views(child, mapping)


def pack(source, output, resources, normal_degrees=.5, prefixes=('Terrain_',)):
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError('Use a new candidate output; do not overwrite an asset')
    if not 0 < normal_degrees <= .5:
        raise ValueError('Flat-normal trial tolerance must be in (0, 0.5] degrees')
    raw = source.read_bytes()
    assert struct.unpack_from('<III', raw) == (0x46546C67, 2, len(raw))
    size, kind = struct.unpack_from('<II', raw, 12); assert kind == 0x4E4F534A
    doc = json.loads(raw[20:20+size]); binary = raw[28+size:]
    assert len(doc['buffers']) == 1 and 'uri' not in doc['buffers'][0]
    views = doc.pop('bufferViews')
    payloads = [binary[v.get('byteOffset', 0):v.get('byteOffset', 0)+v['byteLength']] for v in views]
    encoder = Encoder(resources); records = []
    mesh_names = {}
    for node in doc['nodes']:
        if 'mesh' in node:
            mesh_names.setdefault(node['mesh'], []).append(node.get('name', ''))
    for mesh_id, names in mesh_names.items():
        if not all(n.startswith(tuple(prefixes)) for n in names):
            continue
        mesh = doc['meshes'][mesh_id]; replacements = []
        for primitive in mesh['primitives']:
            extension = primitive.get('extensions', {}).get('KHR_draco_mesh_compression')
            if (extension is None or set(primitive['attributes']) != {'POSITION', 'NORMAL'}
                    or primitive.get('targets') or primitive.get('mode', 4) != 4):
                replacements.append(primitive); continue
            decoded = DracoPy.decode(payloads[extension['bufferView']])
            mask, angles = flat_faces(decoded.points, decoded.normals, decoded.faces, normal_degrees)
            if not mask.any():
                replacements.append(primitive); continue
            encoded_parts = []
            for flat, selected in [(True, mask), (False, ~mask)]:
                if not selected.any():
                    continue
                source_faces = decoded.faces[selected]
                if flat:
                    positions, mapping = np.unique(decoded.points[source_faces].reshape(-1, 3), axis=0, return_inverse=True)
                    faces = mapping.reshape(-1, 3).astype('<u4'); normals = None
                else:
                    used, mapping = np.unique(source_faces, return_inverse=True)
                    positions = decoded.points[used]; normals = decoded.normals[used]
                    faces = mapping.reshape(-1, 3).astype('<u4')
                data, ids, result = encoder.encode(positions, faces, normals)
                encoded_parts.append((flat, data, ids, result))
            before_bytes = len(payloads[extension['bufferView']])
            after_bytes = sum(len(item[1]) for item in encoded_parts)
            # Extra primitive/accessor JSON has a cost too. Leave marginal cases.
            if after_bytes+1500 >= before_bytes:
                replacements.append(primitive); continue
            for flat, data, ids, result in encoded_parts:
                replacement = copy.deepcopy(primitive)
                view_index = len(payloads); payloads.append(data); views.append({'buffer': 0, 'byteLength': len(data)})
                replacement['extensions']['KHR_draco_mesh_compression'] = {'bufferView': view_index, 'attributes': ids}
                replacement['attributes'] = {}
                for key in ids:
                    accessor = copy.deepcopy(doc['accessors'][primitive['attributes'][key]])
                    accessor['count'] = len(result.points)
                    if key == 'POSITION':
                        accessor['min'] = result.points.min(axis=0).tolist(); accessor['max'] = result.points.max(axis=0).tolist()
                    replacement['attributes'][key] = len(doc['accessors']); doc['accessors'].append(accessor)
                accessor = {'componentType': 5125, 'count': int(result.faces.size), 'type': 'SCALAR'}
                replacement['indices'] = len(doc['accessors']); doc['accessors'].append(accessor)
                replacements.append(replacement)
            records.append({'nodes': names, 'flatFaces': int(mask.sum()), 'explicitNormalFaces': int((~mask).sum()),
                            'maximumFlatNormalDifferenceDegrees': float(angles[mask].max()),
                            'beforePayloadBytes': before_bytes, 'afterPayloadBytes': after_bytes})
        mesh['primitives'] = replacements
    used = sorted(set(referenced_views(doc))); mapping = {old: new for new, old in enumerate(used)}
    remap_views(doc, mapping)
    output_binary = bytearray(); output_views = []
    for index in used:
        output_binary.extend(b'\0'*(-len(output_binary) % 4))
        view = copy.deepcopy(views[index]); view['byteOffset'] = len(output_binary); view['buffer'] = 0
        output_binary.extend(payloads[index]); output_views.append(view)
    doc['bufferViews'] = output_views; doc['buffers'] = [{'byteLength': len(output_binary)}]
    output_binary.extend(b'\0'*(-len(output_binary) % 4))
    text = json.dumps(doc, separators=(',', ':')).encode(); text += b' '*(-len(text) % 4)
    result = struct.pack('<III', 0x46546C67, 2, 28+len(text)+len(output_binary))+struct.pack('<II', len(text), 0x4E4F534A)+text+struct.pack('<II', len(output_binary), 0x004E4942)+output_binary
    output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(result)
    report = {'status': 'geometry-preserving candidate; browser visuals and full validators pending',
              'input': str(source.resolve()), 'inputSha256': hashlib.sha256(raw).hexdigest(),
              'output': str(output.resolve()), 'outputSha256': hashlib.sha256(result).hexdigest(),
              'beforeBytes': len(raw), 'afterBytes': len(result), 'savedBytes': len(raw)-len(result), 'records': records,
              'prefixes': list(prefixes),
              'toolSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'records'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender-resources', type=Path, default=Path('/Applications/Blender.app/Contents/Resources'))
    parser.add_argument('--prefixes', nargs='+', choices=['Terrain_', 'Buildings_'], default=['Terrain_'])
    args = parser.parse_args()
    pack(args.input, args.output, args.blender_resources, prefixes=args.prefixes)
