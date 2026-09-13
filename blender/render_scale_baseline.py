"""Render isolated current/neutral scale samples; never rebuild public assets.

blender -b --python-exit-code 1 --python blender/render_scale_baseline.py -- \
  --baseline work/urban-structure/baseline-73edbb7 --output work/urban-structure/scales
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'blender'))
import arts_landmark as arts
import zhenning_landmark as fort


class SampleMesh:
    """Small material-free collector for the production landmark generators."""
    def __init__(self):
        self.vertices, self.faces = [], []

    def face(self, vertices, key=None, normals=None):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.append(tuple(range(offset, len(self.vertices))))

    def box(self, x, y, z, w, d, h, key=None, roof=None, angle=0):
        points = [(x+u*math.cos(angle)-v*math.sin(angle),
                   y+u*math.sin(angle)+v*math.cos(angle), zz)
                  for zz in (z, z+h) for u, v in
                  [(-w/2, -d/2), (w/2, -d/2), (w/2, d/2), (-w/2, d/2)]]
        for indices in [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]:
            self.face([points[i] for i in indices])

    def beam(self, a, b, radius, key=None):
        a, b = Vector(a), Vector(b)
        axis = (b-a).normalized()
        side = axis.cross(Vector((0, 0, 1)) if abs(axis.z) < .95 else Vector((0, 1, 0))).normalized()*radius
        up = axis.cross(side).normalized()*radius
        rings = [[tuple(p+side*u+up*v) for u, v in [(-1, -1), (1, -1), (1, 1), (-1, 1)]] for p in (a, b)]
        for i in range(4):
            j = (i+1) % 4
            self.face([rings[0][i], rings[0][j], rings[1][j], rings[1][i]])
        self.face(rings[0]); self.face(rings[1])

    def cone(self, x, y, z, radius, top_radius, h, key=None, segments=7):
        rings = [[(x+math.cos(i/segments*math.tau)*r, y+math.sin(i/segments*math.tau)*r, zz)
                  for i in range(segments)] for zz, r in [(z, radius), (z+h, top_radius)]]
        for i in range(segments):
            j = (i+1) % segments
            self.face([rings[0][i], rings[0][j], rings[1][j], rings[1][i]])
        self.face(rings[1])

    def object(self, name, material):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        assert not mesh.validate(verbose=False), f'{name}: invalid geometry'
        assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
        mesh.materials.append(material)
        result = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(result)
        return result


def rectangle_inside(point, polygon):
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def intersects(a, b):
    def cross(p, q, r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if any(rectangle_inside(p, b) for p in a) or any(rectangle_inside(p, a) for p in b): return True
    for p, q in zip(a, a[1:]+a[:1]):
        for r, s in zip(b, b[1:]+b[:1]):
            if cross(p,q,r)*cross(p,q,s) < 0 and cross(r,s,p)*cross(r,s,q) < 0: return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    baseline, output = args.baseline.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((baseline/'manifest.json').read_text())
    for relative in ['blender/arts_landmark.py', 'blender/zhenning_landmark.py']:
        actual = hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
        assert actual == manifest['files'][relative]['sha256'], f'Source changed after baseline: {relative}'
    geo = json.loads((baseline/'public/data/geography.json').read_text())
    dem = json.loads((baseline/'public/data/terrain.json').read_text())
    # Source footprint comes from the frozen OSM snapshot, only for sample selection.
    osm = json.loads((ROOT/'work/geodata/osm.json').read_text())
    parcel = next(e for e in osm['elements'] if e['type'] == 'way' and e['id'] == 766539182)
    cx, cy = dem['center']; kx = 1113.2*math.cos(math.radians(cy))
    polygon = [((p['lon']-cx)*kx, (p['lat']-cy)*1113.2) for p in parcel['geometry']]
    center = ((min(p[0] for p in polygon)+max(p[0] for p in polygon))/2,
              (min(p[1] for p in polygon)+max(p[1] for p in polygon))/2)
    selected = [b for b in geo['buildings'] if b['source'] == 'procedural' and
                intersects(b['rings'][0][:-1], polygon[:-1])]
    assert len(selected) == 18, f'Unexpected baseline residential sample: {len(selected)}'
    original_arts_scale = arts.DISPLAY_SCALE
    original_fort_scale, original_height_scale = fort.DISPLAY_SCALE, fort.HEIGHT_SCALE
    original_terrain_scale = dem['verticalExaggeration']
    report = {'baselineCommit': manifest['commit'], 'baselineManifestSha256': hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest(),
              'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'parcelSourceSha256': hashlib.sha256((ROOT/'work/geodata/osm.json').read_bytes()).hexdigest(),
              'note': 'Isolated gray geometry, same camera per pair. Neutral removes known display multipliers; source shapes/heights remain approximate. Flat reference ground is not the city site. Terrain shows conditioned DSM relief above its local minimum.', 'samples': {}}

    for identity in ['residential', 'arts', 'zhenning', 'terrain']:
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        gray = bpy.data.materials.new(f'{identity} gray'); gray.diffuse_color = (.53, .58, .55, 1)
        gray.use_nodes = True
        shader = gray.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = gray.diffuse_color
        shader.inputs['Roughness'].default_value = 1
        objects, measurements = {}, {}
        for variant in ['current', 'neutral']:
            neutral = variant == 'neutral'
            batch = SampleMesh()
            if identity == 'arts':
                arts.DISPLAY_SCALE = 1 if neutral else original_arts_scale
                arts.build_arts(batch, 0, 0, 0, ground=lambda x, y: 0)
                factors = [arts.DISPLAY_SCALE]*3
            elif identity == 'zhenning':
                fort.DISPLAY_SCALE = 1 if neutral else original_fort_scale
                fort.UNIT = fort.DISPLAY_SCALE/100
                fort.HEIGHT_SCALE = 1 if neutral else original_height_scale
                fort.build_zhenning(batch, 0, 0, 0, ground_bounds=lambda x, y: (0, 0))
                factors = [fort.DISPLAY_SCALE, fort.DISPLAY_SCALE, fort.DISPLAY_SCALE*fort.HEIGHT_SCALE]
            elif identity == 'residential':
                factor = 1 if neutral else 1.55
                for building in selected:
                    ring = [(p[0]-center[0], p[1]-center[1]) for p in building['rings'][0][:-1]]
                    height = building['height']/100*factor
                    for a, b in zip(ring, ring[1:]+ring[:1]):
                        batch.face([(*a, 0), (*b, 0), (*b, height), (*a, height)])
                    batch.face([(*p, height) for p in ring])
                factors = [1, 1, factor]
            else:
                factor = 1 if neutral else original_terrain_scale
                west, south, east, north = geo['bounds']; cols, rows = dem['cols'], dem['rows']
                indices = [(i, j) for j in range(rows) for i in range(cols)
                           if 82 <= west+(east-west)*i/(cols-1) <= 94 and
                           -53 <= north-(north-south)*j/(rows-1) <= -41]
                low = min(dem['sceneHeights'][j*cols+i] for i, j in indices)
                sample = set(indices)
                for i, j in indices:
                    if not all(p in sample for p in [(i+1, j), (i+1, j+1), (i, j+1)]): continue
                    points = [(west+(east-west)*a/(cols-1)-88,
                               north-(north-south)*b/(rows-1)+47,
                               (dem['sceneHeights'][b*cols+a]-low)/100*factor)
                              for a, b in [(i, j), (i+1, j), (i+1, j+1), (i, j+1)]]
                    batch.face([points[0], points[2], points[1]])
                    batch.face([points[0], points[3], points[2]])
                factors = [1, 1, factor]
            obj = batch.object(f'{identity}_{variant}', gray)
            coordinates = [v.co for v in obj.data.vertices]
            low = [min(v[i] for v in coordinates) for i in range(3)]
            high = [max(v[i] for v in coordinates) for i in range(3)]
            obj.data.calc_loop_triangles()
            measurements[variant] = {'displayFactorsXYZ': factors, 'bounds': [low, high],
                                     'triangles': len(obj.data.loop_triangles), 'geometrySha256': hashlib.sha256(json.dumps(batch.vertices).encode()).hexdigest()}
            objects[variant] = obj
        assert measurements['current']['triangles'] == measurements['neutral']['triangles']
        low, high = measurements['current']['bounds']
        span = max(high[i]-low[i] for i in range(3))
        target = Vector(((low[0]+high[0])/2, (low[1]+high[1])/2, (low[2]+high[2])/2))
        bpy.ops.object.camera_add(location=target+Vector((1, -1.5, 1.05)).normalized()*span*3)
        camera = bpy.context.object; camera.data.type = 'ORTHO'; camera.data.ortho_scale = span*1.55
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.camera = camera
        bpy.ops.mesh.primitive_plane_add(size=span*15, location=(0, 0, -.005))
        floor = bpy.context.object; floor.name = 'Reference ground'; floor.data.materials.append(gray)
        bpy.ops.object.light_add(type='AREA', location=target+Vector((-span, -span*1.5, span*3)))
        light = bpy.context.object; light.data.energy = 650*span*span; light.data.shape = 'DISK'; light.data.size = span*1.5
        light.rotation_euler = (target-light.location).to_track_quat('-Z', 'Y').to_euler()
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'; scene.cycles.samples = 24; scene.cycles.use_denoising = True; scene.cycles.seed = 771
        scene.world.use_nodes = True; scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value = (.65, .65, .65, 1)
        scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value = .6
        scene.render.resolution_x = 1000; scene.render.resolution_y = 750; scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        for variant, obj in objects.items():
            for name, other in objects.items(): other.hide_render = name != variant; other.hide_set(name != variant)
            scene.render.filepath = str(output/f'{identity}-{variant}.png')
            bpy.ops.render.render(write_still=True)
        objects['current'].hide_render = False; objects['current'].hide_set(False)
        objects['neutral'].hide_render = True; objects['neutral'].hide_set(True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output/f'{identity}.blend'))
        report['samples'][identity] = {'camera': {'position': list(camera.location), 'target': list(target), 'orthographicScale': camera.data.ortho_scale}, 'variants': measurements}
        (output/'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(f'Scale sample complete: {identity}', flush=True)


if __name__ == '__main__': main()
