"""Render the three built cultural landmarks without modifying the saved city.

blender --background --python-exit-code 1 --python blender/render_cultural.py
"""
import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'blender/nanning-city.blend'))
places={p['id']:p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
identities=['qingxiu','ethnic-museum','gx-museum']
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.72,.78,.72,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.7
for obj in list(scene.objects):
    obj.hide_render=obj.type!='LIGHT'
    if obj.type=='MESH' and obj.name not in {'Landmark_'+s for s in identities}:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
camera=scene.camera;camera.data.type='ORTHO'
for identity in identities:
    landmark=bpy.data.objects['Landmark_'+identity];landmark.hide_render=False
    x,z,y=places[identity]['position']
    low=min(v.co.z for v in landmark.data.vertices)
    high=max(v.co.z for v in landmark.data.vertices)
    center=Vector((x,-y,(low+high)/2 if identity=='qingxiu' else z+.28))
    camera.location=center+Vector((3,-5,1.1) if identity=='qingxiu' else (-3,-5,3))
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=(high-low)*1.58 if identity=='qingxiu' else (4.7 if identity=='ethnic-museum' else 3.4)
    for obj in scene.objects:
        if obj.type=='LIGHT':
            obj.location=center+Vector((-3,-4,7));obj.data.energy=750;obj.data.size=5
    scene.render.filepath=str(ROOT/f'docs/{identity}-preview.png');bpy.ops.render.render(write_still=True)
    landmark.hide_render=True
