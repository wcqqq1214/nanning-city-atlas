"""Render P5 block candidates on flat ground without touching public city assets."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from block_massing import build_compound


class Mesh:
    def __init__(self, origin):
        self.origin = origin
        self.vertices, self.faces, self.materials = [], [], []

    def face(self, points, material):
        first = len(self.vertices)
        self.vertices.extend([(x-self.origin[0], y-self.origin[1], z) for x, y, z in points])
        self.faces.append(list(range(first, len(self.vertices))))
        self.materials.append(1 if material == 'roof' else 0)

    def object(self, name):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        assert not mesh.validate(verbose=False), name
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        for label, color in [('wall', (.53, .58, .59, 1)), ('roof', (.73, .74, .70, 1))]:
            material = bpy.data.materials.new(label)
            material.diffuse_color = color
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, self.materials): polygon.material_index = index
        mesh.calc_loop_triangles()
        assert all(t.area > 1e-12 for t in mesh.loop_triangles), name
        return obj


def simple_building(batch, building):
    bottom = .012
    top = bottom+building['height']/100*building.get('displayHeightScale', 1.55)
    for ring in building['rings']:
        for a, b in zip(ring, ring[1:]):
            batch.face([(*a, bottom), (*b, bottom), (*b, top), (*a, top)], 'wall')
    if building.get('roofTriangles'):
        for triangle in building['roofTriangles']:
            batch.face([(*p, top) for p in triangle], 'roof')
    else:
        vertices = [Vector((*p, top)) for p in building['rings'][0][:-1]]
        for triangle in tessellate_polygon([vertices]):
            batch.face([tuple(vertices[p] if isinstance(p, int) else p) for p in triangle], 'roof')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    before = json.loads(args.before.read_text()); candidate = json.loads(args.candidate.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'isolated flat-ground prototype; not city acceptance', 'sites': {},
              'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.before, args.candidate]},
              'tools': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        [Path(__file__), ROOT/'blender/block_massing.py']}}
    for plan in candidate['urbanBlocks']:
        if plan['id'] not in candidate['blockRollout']['siteIds']: continue
        xs, ys = zip(*plan['boundary'][0]); center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2)
        extent = max(max(xs)-min(xs), max(ys)-min(ys))
        old = {b['id'] for b in plan['removedBuildings']}; new = set(plan['buildingIds'])
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        objects = {}; metrics = {}
        context = Mesh(center)
        for b in before['buildings']:
            if b['id'] in plan['preservedBuildingIds']: simple_building(context, b)
        context_object = context.object('retained buildings') if context.faces else None
        if context_object is not None:
            for material in context_object.data.materials:
                material.diffuse_color = (.70, .72, .73, 1)
        for variant, geo, ids in [('before', before, old), ('candidate', candidate, new)]:
            batch = Mesh(center)
            for b in geo['buildings']:
                if b['id'] not in ids: continue
                if 'massing' in b: build_compound(batch, b, (0, 0), 'wall')
                else: simple_building(batch, b)
            if batch.faces:
                obj = batch.object(variant)
                objects[variant] = obj
                metrics[variant] = {'triangles': len(obj.data.loop_triangles), 'buildings': len(ids),
                                    'maximumHeightMeters': max(v.co.z for v in obj.data.vertices)*100}
            else:
                objects[variant] = None
                metrics[variant] = {'triangles': 0, 'buildings': 0, 'maximumHeightMeters': 0}
        ground = Mesh(center)
        ring = [Vector((*p, 0)) for p in plan['boundary'][0][:-1]]
        for triangle in tessellate_polygon([ring]):
            ground.face([tuple(ring[p] if isinstance(p, int) else p) for p in triangle], 'roof')
        floor = ground.object('source boundary')
        floor.data.materials[1].diffuse_color = (.84, .85, .80, 1)
        scene = bpy.context.scene
        bpy.ops.object.camera_add()
        camera = bpy.context.object; scene.camera = camera
        camera.data.type = 'ORTHO'; camera.data.ortho_scale = extent*1.48
        target = Vector((0, 0, .2))
        camera.location = target+Vector((.6, -1.3, 1.2))*extent
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.color_type = 'MATERIAL'
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = 'BOTH'
        scene.display.shading.background_type = 'WORLD'
        scene.world.color = (.92, .92, .90)
        scene.render.resolution_x = 960; scene.render.resolution_y = 760
        scene.render.resolution_percentage = 100
        images = {}
        for variant in ['before', 'candidate']:
            for name, obj in objects.items():
                if obj is not None: obj.hide_render = name != variant
            path = args.output/f'{plan["id"]}-{variant}.png'
            scene.render.filepath = str(path.resolve())
            bpy.ops.render.render(write_still=True)
            images[variant] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        report['sites'][plan['id']] = {'metrics': metrics, 'images': images,
            'camera': {'location': list(camera.location), 'target': list(target), 'orthoScale': camera.data.ortho_scale},
            'retainedContextBuildings': len(plan['preservedBuildingIds']),
            'limitations': ['Retained buildings intersecting the site are shown in both variants; wider city surroundings are omitted',
                            'Flat reference does not validate actual terrain support, roads or trees']}
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': main()
