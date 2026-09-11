"""Render the built mall meshes for documentation without modifying the .blend.

Run after models:build: blender -b --python blender/render_malls.py
"""
import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'blender/nanning-city.blend'))
places = {p['id']: p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 20
scene.cycles.use_denoising = True
scene.render.resolution_x = 1400
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'AgX'
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.72,.78,.72,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .7
for obj in scene.objects:
    obj.hide_render = obj.type != 'LIGHT'
for obj in list(scene.objects):
    if obj.type == 'MESH' and obj.name not in {'Landmark_hangyang', 'Landmark_mixc'}:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
camera = scene.camera
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 5.1
for identity, view in [('hangyang',(-3,-5,3)),('mixc',(-3,5,4))]:
    landmark = bpy.data.objects['Landmark_'+identity]
    landmark.hide_render = False
    x,z,y = places[identity]['position']
    center = Vector((x,-y,z+(.65 if identity=='hangyang' else .27)))
    camera.location = center+Vector(view)
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.location = center+Vector((-3,-4 if identity=='hangyang' else 4,7))
            obj.data.energy = 750
            obj.data.size = 5
    scene.render.filepath = str(ROOT/f'docs/{identity}-preview.png')
    bpy.ops.render.render(write_still=True)
    landmark.hide_render = True
