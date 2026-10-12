"""Scope city detail inside a rectangular model with coarse surroundings.

Untouched Draco primitives are copied byte for byte. Boundary triangles retain
their source plane, winding and interpolated corner normals; changed primitives
use Blender's Draco bridge with decoded position/normal error checks. Canopy
positions remain lossless; structural surfaces stay within 1 cm and other
boundary geometry within 5 cm. Buildings and individual tree
parts are retained as whole connected components. The editable city and its
source geography remain full extent. Run against a separate full-city export.
"""
import argparse
import copy
import ctypes as c
import hashlib
import json
import shutil
from pathlib import Path
import struct
from types import SimpleNamespace

import DracoPy
import mapbox_earcut
import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping
from shapely.ops import transform, unary_union

from pack_flat_surfaces import Encoder, referenced_views, remap_views
from urban_scope import ROOT, UrbanScope, polygons


class ScopeEncoder(Encoder):
    """Use city-scale precision and verify every compressed face bijectively."""
    position_bits = 24
    position_limit = .01

    def encode(self, points, faces, normals=None):
        from check_reduced_terrain_exports import match_faces
        attributes = {'POSITION': np.ascontiguousarray(points, dtype='<f4'),
                      'NORMAL': np.ascontiguousarray(normals, dtype='<f4')}
        indices = np.ascontiguousarray(faces, dtype='<u4')
        handle = self.dll.encoderCreate(len(points))
        try:
            ids = {key: self.dll.encoderSetAttribute(handle, key.encode(), 5126, b'VEC3', value.ctypes.data, False)
                   for key, value in attributes.items()}
            self.dll.encoderSetIndices(handle, 5125, indices.size, indices.ctypes.data)
            self.dll.encoderSetCompressionLevel(handle, 10)
            self.dll.encoderSetQuantizationBits(handle, self.position_bits, 10, 0, 0, 0)
            if not self.dll.encoderEncode(handle, 0):
                raise ValueError('Draco encoding failed')
            buffer = c.create_string_buffer(self.dll.encoderGetByteLength(handle))
            self.dll.encoderCopy(handle, buffer)
            decoded = DracoPy.decode(buffer.raw)
            before = {'triangles': points[faces], 'cornerNormals': normals[faces], 'materials': np.zeros(len(faces), dtype=int)}
            after = {'triangles': decoded.points[decoded.faces], 'cornerNormals': decoded.normals[decoded.faces],
                     'materials': np.zeros(len(decoded.faces), dtype=int)}
            self.validation = match_faces(before, after, position_meters=self.position_limit, normal_degrees=.5)
            return buffer.raw, ids, decoded
        finally:
            self.dll.encoderRelease(handle)


def triangulate(shape):
    for poly in polygons(shape):
        rings = [np.asarray(r.coords)[:-1, :2] for r in [poly.exterior, *poly.interiors]]
        points = np.concatenate(rings)
        ends = np.cumsum([len(r) for r in rings], dtype=np.uint32)
        ids = mapbox_earcut.triangulate_float64(points, ends).reshape(-1, 3)
        yield from points[ids]


def clip_interval(vertices, axis, limit, greater):
    """Clip positions plus attributes; also works on vertical triangles."""
    result = []
    for a, b in zip(vertices, np.roll(vertices, -1, axis=0)):
        inside_a = a[axis] >= limit if greater else a[axis] <= limit
        inside_b = b[axis] >= limit if greater else b[axis] <= limit
        if inside_a:
            result.append(a)
        if inside_a != inside_b:
            result.append(a+(b-a)*((limit-a[axis])/(b[axis]-a[axis])))
    return np.asarray(result)


def clip_face(values, mask):
    """Return a 3D triangle's intersection with a vertical polygon prism."""
    xy = values[:, [0, 2]] * [1, -1]  # glTF -> local east/north
    matrix = np.column_stack((xy[1]-xy[0], xy[2]-xy[0]))
    det = np.linalg.det(matrix)
    if abs(det) > 1e-12:
        clipped = Polygon(xy).intersection(mask)
        for triangle in triangulate(clipped):
            weights = np.linalg.solve(matrix, (triangle-xy[0]).T).T
            out = values[0] + weights[:, :1]*(values[1]-values[0]) + weights[:, 1:]*(values[2]-values[0])
            if np.linalg.det(np.column_stack((triangle[1]-triangle[0], triangle[2]-triangle[0]))) * det < 0:
                out = out[[0, 2, 1]]
            yield out
    else:
        # Roof/wall vertices can collapse to a line in plan. Intersect that line
        # and clip the original vertical face at each retained interval.
        axis_xy = int(np.ptp(xy, axis=0).argmax())
        order = np.argsort(xy[:, axis_xy])
        if np.ptp(xy[:, axis_xy]) < 1e-10:
            return
        cut = LineString(xy[order[[0, -1]]]).intersection(mask)
        parts = [cut] if cut.geom_type == 'LineString' else getattr(cut, 'geoms', [])
        axis = [0, 2][axis_xy]
        for part in parts:
            if part.geom_type != 'LineString' or part.length < 1e-10:
                continue
            ends = np.asarray(part.coords)[:, axis_xy] * (1 if axis == 0 else -1)
            out = clip_interval(values, axis, float(ends.min()), True)
            if len(out) < 3:
                continue
            out = clip_interval(out, axis, float(ends.max()), False)
            for i in range(1, len(out)-1):
                yield out[[0, i, i+1]]


def whole_component_mask(points, faces, mask):
    # Vertices are split at material/normal seams. Weld positions for topology
    # only; exported attributes and every retained face stay untouched.
    _, welded = np.unique(points, axis=0, return_inverse=True)
    ids = welded[faces]
    rows = ids[:, [0, 1, 2]].ravel()
    cols = ids[:, [1, 2, 0]].ravel()
    graph = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)),
                       shape=(int(welded.max())+1,)*2)
    count, labels = connected_components(graph, directed=False)
    face_labels = labels[ids[:, 0]]
    xy = points[faces][:, :, [0, 2]] * [1, -1]
    lows = np.full((count, 2), np.inf)
    highs = np.full((count, 2), -np.inf)
    np.minimum.at(lows, face_labels, xy.min(axis=1))
    np.maximum.at(highs, face_labels, xy.max(axis=1))
    selected = shapely.intersects(mask, shapely.box(lows[:, 0], lows[:, 1], highs[:, 0], highs[:, 1]))
    # Degenerate component footprints (e.g. a single wall) need a tiny buffer.
    degenerate = np.any(highs-lows < 1e-10, axis=1)
    if degenerate.any():
        selected[degenerate] = shapely.intersects(mask, shapely.box(
            lows[degenerate, 0]-1e-6, lows[degenerate, 1]-1e-6,
            highs[degenerate, 0]+1e-6, highs[degenerate, 1]+1e-6))
    return selected[face_labels]


def crop_geometry(points, normals, faces, mask, whole=False):
    xy = points[:, [0, 2]] * [1, -1]
    face_xy = xy[faces]
    if whole:
        keep = whole_component_mask(points, faces, mask)
        cut = np.zeros(len(faces), dtype=bool)
    else:
        low, high = face_xy.min(axis=1), face_xy.max(axis=1)
        # A zero-width Polygon is invalid in GEOS and can miss a boundary
        # crossing. Pad only the broad-phase boxes; exact clipping stays on the
        # original plane, including east/west-facing railway retaining walls.
        boxes = shapely.box(low[:, 0]-1e-8, low[:, 1]-1e-8,
                            high[:, 0]+1e-8, high[:, 1]+1e-8)
        cut = shapely.intersects(mask.boundary, boxes)
        center = face_xy.mean(axis=1)
        keep = ~cut & shapely.intersects_xy(mask, center[:, 0], center[:, 1])
    pieces = []
    attributes = np.concatenate([points, normals], axis=1).astype(float)
    for index in np.flatnonzero(cut):
        pieces.extend(clip_face(attributes[faces[index]], mask))
    kept = attributes[faces[keep]]
    extra = np.asarray(pieces, dtype='<f4').reshape(-1, 3, 6)
    if len(extra):
        # Remove only newly created zero-area slivers; preserve source faces.
        area = np.linalg.norm(np.cross(extra[:, 1, :3]-extra[:, 0, :3], extra[:, 2, :3]-extra[:, 0, :3]), axis=1)
        extra = extra[area > 1e-12]
        lengths = np.linalg.norm(extra[:, :, 3:], axis=2, keepdims=True)
        extra[:, :, 3:] /= np.maximum(lengths, 1e-30)
    if keep.all():
        return points, normals, faces, {'kept': len(faces), 'cut': 0, 'created': 0, 'removed': 0}
    # Some already-quantized source primitives contain coincident vertices.
    # Welding them would turn a source face into repeated indices, which Draco
    # drops. Account explicitly for these zero-area faces before re-encoding.
    source_area = np.linalg.norm(np.cross(kept[:, 1, :3]-kept[:, 0, :3],
                                         kept[:, 2, :3]-kept[:, 0, :3]), axis=1)
    collapsed = int((source_area == 0).sum())
    kept = kept[source_area > 0]
    values = np.concatenate([kept, extra]).astype('<f4')
    stats = {'kept': len(kept), 'cut': int(cut.sum()), 'created': len(extra),
             'sourceDegenerateFacesRemoved': collapsed,
             'removed': int((~keep & ~cut).sum())}
    if not len(values):
        return None, None, None, stats
    unique, indices = np.unique(values.reshape(-1, 6), axis=0, return_inverse=True)
    return unique[:, :3], unique[:, 3:], indices.reshape(-1, 3), stats


def explicit_surface(mesh):
    """Match the browser's per-face normals for compact flat primitives.

    Shared positions cannot hold both normals at a crease. Expand these faces
    only when doing geometry work; untouched compressed payloads are still copied.
    """
    if mesh.normals is not None:
        return mesh
    triangles = mesh.points[mesh.faces].astype(float)
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    if (lengths <= 1e-15).any():
        raise ValueError('Degenerate flat primitive has no defined normal')
    return SimpleNamespace(points=triangles.reshape(-1, 3).astype('<f4'),
        faces=np.arange(triangles.size//3).reshape(-1, 3),
        normals=np.repeat(normals/lengths[:, None], 3, axis=0).astype('<f4'))


class CityGLB:
    def __init__(self, path):
        raw = path.read_bytes()
        if struct.unpack_from('<III', raw) != (0x46546C67, 2, len(raw)):
            raise ValueError('Invalid GLB')
        size, kind = struct.unpack_from('<II', raw, 12)
        if kind != 0x4E4F534A:
            raise ValueError('Invalid GLB JSON')
        self.doc = json.loads(raw[20:20+size])
        binary = raw[28+size:]
        self.views = self.doc.pop('bufferViews')
        self.payloads = [binary[v.get('byteOffset', 0):v.get('byteOffset', 0)+v['byteLength']]
                         for v in self.views]
        for node in self.doc['nodes']:
            if any(k in node for k in ['matrix', 'translation', 'rotation', 'scale']):
                raise ValueError('Scope export requires baked city transforms')
        self.sha = hashlib.sha256(raw).hexdigest()
        self.bytes = len(raw)

    def decode(self, primitive):
        extension = primitive['extensions']['KHR_draco_mesh_compression']
        return explicit_surface(DracoPy.decode(self.payloads[extension['bufferView']]))

    def primitive(self, template, points, normals, faces, encoder):
        payload, ids, decoded = encoder.encode(points, faces, normals)
        primitive = copy.deepcopy(template)
        view = len(self.payloads)
        self.payloads.append(payload)
        self.views.append({'buffer': 0, 'byteLength': len(payload)})
        primitive['extensions'] = {'KHR_draco_mesh_compression': {'bufferView': view, 'attributes': ids}}
        primitive['attributes'] = {}
        for key in ids:
            accessor = {'componentType': 5126, 'count': len(decoded.points), 'type': 'VEC3'}
            if key == 'POSITION':
                accessor.update(min=decoded.points.min(axis=0).tolist(), max=decoded.points.max(axis=0).tolist())
            primitive['attributes'][key] = len(self.doc['accessors'])
            self.doc['accessors'].append(accessor)
        primitive['indices'] = len(self.doc['accessors'])
        self.doc['accessors'].append({'componentType': 5125, 'count': int(decoded.faces.size), 'type': 'SCALAR'})
        return primitive

    def add_surface(self, name, layer, geometry, material, encoder):
        self.doc['materials'].append(material)
        template = {'material': len(self.doc['materials'])-1, 'mode': 4}
        primitive = self.primitive(template, *geometry, encoder)
        node = {'name': name, 'mesh': len(self.doc['meshes'])}
        parent = next(n for n in self.doc['nodes'] if n.get('name') == layer)
        parent.setdefault('children', []).append(len(self.doc['nodes']))
        self.doc['nodes'].append(node)
        self.doc['meshes'].append({'name': name, 'primitives': [primitive]})

    def write(self, output):
        doc = self.doc
        used_meshes = {n['mesh'] for n in doc['nodes'] if 'mesh' in n and doc['meshes'][n['mesh']]['primitives']}
        mesh_map = {old: new for new, old in enumerate(sorted(used_meshes))}
        doc['meshes'] = [doc['meshes'][i] for i in sorted(used_meshes)]
        for node in doc['nodes']:
            if 'mesh' in node:
                old = node.pop('mesh')
                if old in mesh_map:
                    node['mesh'] = mesh_map[old]
        primitives = [p for m in doc['meshes'] for p in m['primitives']]
        used_accessors = sorted({a for p in primitives for a in [p['indices'], *p['attributes'].values()]})
        accessors = {old: new for new, old in enumerate(used_accessors)}
        doc['accessors'] = [doc['accessors'][i] for i in used_accessors]
        for p in primitives:
            p['indices'] = accessors[p['indices']]
            p['attributes'] = {k: accessors[v] for k, v in p['attributes'].items()}
        used = sorted(set(referenced_views(doc)))
        remap_views(doc, {old: new for new, old in enumerate(used)})
        binary = bytearray()
        views = []
        for i in used:
            binary.extend(b'\0'*(-len(binary) % 4))
            views.append({**self.views[i], 'buffer': 0, 'byteOffset': len(binary)})
            binary.extend(self.payloads[i])
        doc['bufferViews'] = views
        doc['buffers'] = [{'byteLength': len(binary)}]
        binary.extend(b'\0'*(-len(binary) % 4))
        text = json.dumps(doc, separators=(',', ':')).encode()
        text += b' '*(-len(text) % 4)
        raw = struct.pack('<III', 0x46546C67, 2, 28+len(text)+len(binary)) + struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(binary), 0x004E4942) + binary
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'triangles': sum(doc['accessors'][p['indices']]['count']//3 for p in primitives),
                'meshes': len(doc['meshes'])}


def boundary_samples(points, faces, mask):
    xy = points[:, [0, 2]] * [1, -1]
    close = shapely.distance(shapely.points(xy), mask.boundary) < .001
    indices = np.unique(faces[np.any(close[faces], axis=1)].ravel())
    indices = indices[close[indices]]
    return [(mask.exterior.project(shapely.Point(*xy[i])), float(points[i, 1])) for i in indices]


def plinth_geometry(mask, samples):
    # Sort the actual clipped terrain/water endpoints along the outer boundary;
    # the skirt therefore follows its varying elevation instead of exposing a
    # vertical gap. Only the rectangular perimeter gets a skirt.
    heights = {}
    for distance, height in samples:
        key = round(distance, 5)
        heights[key] = max(heights.get(key, -np.inf), height)
    if len(heights) < 3:
        raise ValueError('No terrain boundary for the city plinth')
    top = []
    for distance, height in sorted(heights.items()):
        p = mask.exterior.interpolate(distance)
        top.append([p.x, height, -p.y])
    bottom = -2.6
    triangles = []
    for a, b in zip(top, top[1:]+top[:1]):
        aa, bb = [a[0], bottom, a[2]], [b[0], bottom, b[2]]
        triangles.extend([[a, aa, bb], [a, bb, b]])
    for t in triangulate(mask):
        triangles.append([[x, bottom, -y] for x, y in t])
    tri = np.asarray(triangles, dtype='<f4')
    normal = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    good = np.linalg.norm(normal, axis=1) > 1e-10
    tri, normal = tri[good], normal[good]
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    return tri.reshape(-1, 3), np.repeat(normal, 3, axis=0), np.arange(tri.size//3, dtype=np.uint32).reshape(-1, 3)


def crop_model(source, output, scope, encoder):
    city = CityGLB(source)
    if city.doc.get('extras', {}).get('urbanScope'):
        raise ValueError('Already scoped: use the preserved full-city export, not a cropped model')
    records = []
    samples = []
    seam_samples = []
    source_terrain = []
    source_water = []
    canopy_meshes = []
    for mesh in city.doc['meshes']:
        name = mesh['name']
        if name.startswith('Vegetation') and '_canopy' in name:
            canopy_meshes.append(mesh)
            continue
        encoder.position_bits = (0 if '_canopy' in name else
                                 24 if name.startswith('Terrain') or name == 'Water' else
                                 22 if 'Road' in name or 'Avenue' in name else
                                 20 if name.startswith('Railway') else 18)
        encoder.position_limit = .01 if encoder.position_bits >= 20 else .05
        if '_canopy' in name:
            encoder.position_limit = 1e-7
        if name == 'Plinth':
            continue
        mask = scope.mask_for(name)
        whole = name.startswith('Buildings') or (name.startswith('Vegetation') and '_canopy' not in name)
        replacements = []
        for index, primitive in enumerate(mesh['primitives']):
            decoded = None
            if name.startswith('Terrain') or name == 'Water':
                decoded = city.decode(primitive)
                (source_terrain if name.startswith('Terrain') else source_water).append(decoded.points[decoded.faces])
            accessor = city.doc['accessors'][primitive['attributes']['POSITION']]
            low, high = accessor['min'], accessor['max']
            footprint = box(low[0], -high[2], high[0], -low[2])
            before = city.doc['accessors'][primitive['indices']]['count']//3
            record = {'mesh': name, 'primitive': index, 'before': before}
            if name.startswith('Landmark') and not scope.core.covers(footprint):
                raise ValueError('Landmark mesh crosses the approved core: ' + name)
            if mask.covers(footprint):
                replacements.append(primitive)
                record.update(action='copy', after=before)
                if name.startswith('Terrain') or name == 'Water':
                    # At the old data edge the entire primitive may be inside.
                    if footprint.distance(scope.context.boundary) < .001:
                        d = decoded
                        samples.extend(boundary_samples(d.points, d.faces, scope.context))
                    if name.startswith('Terrain') and footprint.distance(scope.transition.boundary) < .001:
                        seam_samples.extend(boundary_samples(decoded.points, decoded.faces, scope.transition))
            elif not mask.intersects(footprint):
                record.update(action='remove', after=0)
            else:
                d = decoded if decoded is not None else city.decode(primitive)
                points, normals, faces, counts = crop_geometry(d.points, d.normals, d.faces, mask, whole)
                record.update(counts, action='whole-components' if whole else 'clip', after=0 if points is None else len(faces))
                if points is not None:
                    if counts['kept'] == before and not counts['cut']:
                        replacements.append(primitive)
                        record['action'] = 'copy'
                    else:
                        replacements.append(city.primitive(primitive, points, normals, faces, encoder))
                        record['compressionValidation'] = encoder.validation
                    if name.startswith('Terrain') or name == 'Water':
                        samples.extend(boundary_samples(points, faces, scope.context))
                    if name.startswith('Terrain'):
                        seam_samples.extend(boundary_samples(points, faces, scope.transition))
            records.append(record)
        mesh['primitives'] = replacements
        if any(r['action'] != 'copy' for r in records if r['mesh'] == name):
            print(f"{source.name}: {name} -> {sum(r['after'] for r in records if r['mesh'] == name):,} triangles", flush=True)
    from city_context import TerrainSampler, build_context, fade_canopy
    terrain, roads, context_stats = build_context(scope, np.concatenate(source_terrain),
                                                 np.concatenate(source_water), seam_samples)
    def context_material(name, color):
        srgb = np.array([int(color[i:i+2], 16)/255 for i in (0, 2, 4)])
        linear = np.where(srgb <= .04045, srgb/12.92, ((srgb+.055)/1.055)**2.4)
        return {'name': name, 'pbrMetallicRoughness': {'baseColorFactor': [*linear.tolist(), 1],
                'metallicFactor': 0, 'roughnessFactor': 1}, 'doubleSided': True}
    for name, layer, geometry, color in [('Terrain_context', 'Terrain', terrain, 'b9c0ab'),
                                         ('GroundRoads_context', 'Roads', roads, 'a3aaa3')]:
        if geometry[0] is None:
            continue
        encoder.position_bits = 24
        encoder.position_limit = .01
        city.add_surface(name, layer, geometry, context_material(name, color), encoder)
        records.append({'mesh': name, 'primitive': 0, 'before': 0, 'after': len(geometry[2]),
                        'action': 'coarse-context', 'compressionValidation': encoder.validation})
    # Canopy outside the city follows the final (possibly coarser) terrain.
    # Keep core primitives unchanged and taper the peripheral relief to earth.
    source_ground = TerrainSampler(np.concatenate(source_terrain))
    displayed = []
    for mesh in city.doc['meshes']:
        if mesh['name'].startswith('Terrain'):
            for primitive in mesh['primitives']:
                d = city.decode(primitive)
                displayed.append(d.points[d.faces])
    display_ground = TerrainSampler(np.concatenate(displayed))
    encoder.position_bits = 0
    encoder.position_limit = 1e-7
    for mesh in canopy_meshes:
        replacements = []
        for index, primitive in enumerate(mesh['primitives']):
            a = city.doc['accessors'][primitive['attributes']['POSITION']]
            lo, hi = a['min'], a['max']
            footprint = box(lo[0], -hi[2], hi[0], -lo[2])
            before = city.doc['accessors'][primitive['indices']]['count']//3
            record = {'mesh': mesh['name'], 'primitive': index, 'before': before}
            if scope.core.covers(footprint):
                replacements.append(primitive)
                record.update(action='copy', after=before)
            elif not scope.landscape.intersects(footprint):
                record.update(action='remove', after=0)
            else:
                d = city.decode(primitive)
                p, n, f, counts = crop_geometry(d.points, d.normals, d.faces, scope.landscape)
                record.update(counts, action='taper-canopy', after=0 if f is None else len(f))
                if p is not None:
                    geometry = fade_canopy(p, n, f, scope, source_ground, display_ground)
                    record['after'] = len(geometry[2])
                    replacements.append(city.primitive(primitive, *geometry, encoder))
                    record['compressionValidation'] = encoder.validation
            records.append(record)
        mesh['primitives'] = replacements
    samples.extend(boundary_samples(terrain[0], terrain[2], scope.context))
    print(f'{source.name}: rectangular context {context_stats}', flush=True)
    plinth = next(m for m in city.doc['meshes'] if m['name'] == 'Plinth')
    template = plinth['primitives'][0]
    old_plinth = city.doc['accessors'][template['indices']]['count']//3
    points, normals, faces = plinth_geometry(scope.context, samples)
    encoder.position_bits = 20
    encoder.position_limit = .05
    plinth['primitives'] = [city.primitive(template, points, normals, faces, encoder)]
    records.append({'mesh': 'Plinth', 'primitive': 0, 'before': old_plinth, 'after': len(faces),
                    'action': 'rebuild-skirt', 'compressionValidation': encoder.validation})
    city.doc.setdefault('extras', {})['urbanScope'] = scope.source['id']
    result = city.write(output)
    return {'input': str(source), 'inputSha256': city.sha, 'beforeBytes': city.bytes,
            'beforeTriangles': sum(r['before'] for r in records), **result,
            'context': context_stats, 'records': records}


def run(input_root, output_root, resources, report_path):
    if input_root.resolve() == output_root.resolve():
        raise ValueError('Keep source and scoped export in separate directories')
    scope = UrbanScope.read()
    scope.require_approved()
    encoder = ScopeEncoder(resources)
    reports = {}
    overview = json.loads((input_root/'data/overview.json').read_text())
    if overview.get('urbanScope'):
        raise ValueError('Overview is already scoped')
    for profile, filename in [('detail', 'nanning-city.glb'), ('smooth', 'nanning-city-mobile.glb')]:
        reports[profile] = crop_model(input_root/'models'/filename, output_root/'models'/filename, scope, encoder)
        overview['models'][profile] = {'file': filename, 'bytes': reports[profile]['bytes']}
    overview['sourceBounds'] = overview['bounds']
    overview['sourceBbox'] = overview['bbox']
    overview['sourceStats'] = overview['stats']
    overview['bounds'] = list(scope.context.bounds)
    overview['bbox'] = list(transform(scope.inverse, scope.context).bounds)
    overview['urbanScope'] = {
        'id': scope.source['id'], 'outline': 'rectangle',
        'core': mapping(scope.core), 'transition': mapping(scope.transition), 'context': mapping(scope.context),
        'coreBounds': list(scope.core.bounds), 'contextWidthMeters': scope.source['contextWidthMeters'],
        'coreAreaKm2': round(scope.core.area/100, 2), 'contextAreaKm2': round(scope.context.area/100, 2),
        'landscapeFadeMeters': scope.source['landscapeFadeMeters'],
        'deferredAreaKm2': round(scope.proposed.difference(scope.coverage).area/100, 2),
        'wholeCrossingFootprints': len(scope.crossing_buildings),
        'deferredSites': ['园博园'], 'sourceBoundarySha256': hashlib.sha256((ROOT/'data/urban-core-boundary-source.json').read_bytes()).hexdigest(),
    }
    forest = json.loads((ROOT/'data/forest-plan.json').read_text())
    woodland = unary_union([shapely.make_valid(Polygon(p[0], p[1:]))
                            for region in forest['regions'] for p in region['woodland']])
    # This small mask preserves natural woodland outlines in the cheap ground
    # treatment after the raised canopy has tapered away.
    woodland = woodland.intersection(scope.context).simplify(.25, preserve_topology=True)
    overview['urbanScope']['woodland'] = mapping(MultiPolygon(list(polygons(woodland))))
    selected = [scope.geo['buildings'][i] for i in scope.retained_buildings]
    overview['stats'] = {**overview['stats'],
                         'mappedBuildings': sum(b['source'] == 'osm' for b in selected),
                         'infillBuildings': sum(b['source'] != 'osm' for b in selected),
                         'roadSegments': sum((scope.transition.intersects(LineString(r['points'])) or
                             r['class'].removesuffix('_link') in ('motorway', 'trunk', 'primary', 'secondary') and
                             scope.context.intersects(LineString(r['points']))) for r in scope.geo['roads'])}
    # Count bounded single-tree meshes after component retention. Forest crowns
    # and dedicated landmark vegetation have separate source statistics.
    for profile, per_tree in [('detail', 30), ('smooth', 8)]:
        singles = sum(r['after'] for r in reports[profile]['records']
                      if r['mesh'].startswith('Vegetation_') and r['mesh'].split('_')[1].lstrip('-').isdigit())
        if singles % per_tree:
            raise ValueError('Scope split an individual city tree')
        if profile == 'detail':
            overview['stats']['trees'] = singles//per_tree
        else:
            overview['mobileTrees'] = singles//per_tree
    overview['water'] = [list(map(list, [p.exterior.coords, *[r.coords for r in p.interiors]]))
                         for rings in overview['water']
                         for p in polygons(Polygon(rings[0], rings[1:]).intersection(scope.context))]
    (output_root/'data').mkdir(parents=True, exist_ok=True)
    (output_root/'data/overview.json').write_text(json.dumps(overview, ensure_ascii=False, separators=(',', ':')))
    (output_root/'data/landmarks.json').write_bytes((input_root/'data/landmarks.json').read_bytes())
    manifest = {'version': 1, 'scopeSourceSha256': overview['urbanScope']['sourceBoundarySha256'],
                'geographySha256': hashlib.sha256((ROOT/'public/data/geography.json').read_bytes()).hexdigest(),
                'forestSourceSha256': hashlib.sha256((ROOT/'data/forest-plan.json').read_bytes()).hexdigest(),
                'models': {}}
    for profile, filename in [('detail', 'nanning-city.glb'), ('smooth', 'nanning-city-mobile.glb')]:
        original = CityGLB(input_root/'models'/filename)
        protected = {}
        for mesh in original.doc['meshes']:
            if mesh['name'].startswith('Landmark_'):
                protected[mesh['name']] = [hashlib.sha256(original.payloads[p['extensions']['KHR_draco_mesh_compression']['bufferView']]).hexdigest()
                                           for p in mesh['primitives']]
        r = reports[profile]
        manifest['models'][profile] = {k: r[k] for k in ['inputSha256', 'beforeBytes', 'beforeTriangles', 'sha256', 'bytes', 'triangles', 'meshes']}
        manifest['models'][profile]['context'] = r['context']
        manifest['models'][profile]['protectedLandmarkPayloads'] = protected
        manifest['models'][profile]['copiedPrimitives'] = sum(v['action'] == 'copy' for v in r['records'])
        manifest['models'][profile]['maximumCompressionPositionErrorMeters'] = max(v.get('compressionValidation', {}).get('maximumVertexDisplacementMeters', 0) for v in r['records'])
        manifest['models'][profile]['maximumCompressionNormalErrorDegrees'] = max(v.get('compressionValidation', {}).get('maximumCornerNormalAngleDegrees', 0) for v in r['records'])
    (output_root/'data/urban-scope-models.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    report = {'status': 'scoped export; run check_urban_scope_exports.py and browser review',
              'scope': overview['urbanScope'], 'models': reports,
              'toolSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({p: {k: v for k, v in r.items() if k != 'records'} for p, r in reports.items()}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, default=ROOT/'work/full-city')
    parser.add_argument('--output-root', type=Path, default=ROOT/'work/urban-scope-review/latest-candidate')
    parser.add_argument('--publish', action='store_true', help='Validate the complete candidate before replacing public models and metadata')
    parser.add_argument('--blender-resources', type=Path, default=Path('/Applications/Blender.app/Contents/Resources'))
    parser.add_argument('--report', type=Path, default=ROOT/'work/urban-scope-review/implementation/export.json')
    args = parser.parse_args()
    if args.output_root.resolve() == (ROOT/'public').resolve():
        parser.error('Use a separate candidate directory and --publish')
    run(args.input_root, args.output_root, args.blender_resources, args.report)
    from check_urban_scope_exports import validate
    validate(args.output_root, args.input_root)
    if args.publish:
        for relative in ['models/nanning-city.glb', 'models/nanning-city-mobile.glb',
                         'data/overview.json', 'data/landmarks.json', 'data/urban-scope-models.json']:
            target = ROOT/'public'/relative
            staging = target.with_suffix(target.suffix+'.tmp')
            shutil.copyfile(args.output_root/relative, staging)
            staging.replace(target)
        print('Validated scoped models and metadata published to public/', flush=True)
