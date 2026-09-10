"""Render bridge contact-sheet sources from the built editable city.

Run: blender -b --python blender/render_bridges.py
Only writes preview JPEGs; never saves or modifies the .blend file.
"""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from major_bridges import SPECS

preview='--preview' in sys.argv
bpy.ops.wm.open_mainfile(filepath=str(ROOT/('work/bridge-refinement/bridges-preview.blend' if preview else 'blender/nanning-city.blend')))
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.samples=8
scene.cycles.use_denoising=True
scene.render.resolution_x=1000
scene.render.resolution_y=650
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='JPEG'
scene.render.image_settings.quality=90
scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.8
scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.65,.78,.72,1)
water=bpy.data.materials.get('Jade water')
if water is None:
    water=bpy.data.materials.new('Jade water')
    water.diffuse_color=(.25,.48,.41,1)
    water.use_nodes=True
    water.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.19,.39,.33,1)
    water.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.7
# Display each bridge against a clean river surface to inspect structure,
# independently of nearby infill and city-wide terrain exaggeration.
for obj in scene.objects: obj.hide_render=True
for obj in scene.objects:
    if obj.type=='LIGHT':
        obj.hide_render=False
        obj.data.energy=2400
        obj.data.size=12
camera=scene.camera
camera.hide_render=False
camera.data.type='ORTHO'
output=ROOT/'work/bridge-refinement/renders'
output.mkdir(parents=True,exist_ok=True)
places={p['id']:p for p in json.loads((ROOT/('work/bridge-refinement/preview-places.json' if preview else 'public/data/landmarks.json')).read_text())}
for identity,spec in SPECS.items():
    bridge=bpy.data.objects['Landmark_'+identity]
    visible=[bridge,*bridge.children_recursive]
    for obj in visible: obj.hide_render=False
    p=places[identity]['position'];cx,cy,z=p[0],-p[2],p[1]
    length=spec['length']
    a,c=spec['points'][0],spec['points'][-1]
    dx,dy=c[0]-a[0],c[1]-a[1];norm=math.hypot(dx,dy)
    tangent=Vector((dx/norm,dy/norm,0));normal=Vector((-dy/norm,dx/norm,0))
    center=Vector((cx,cy,z+spec['displayRise']*.30))
    camera.location=center+normal*length*.85-tangent*length*.36+Vector((0,0,length*.53))
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=length*1.10
    for obj in scene.objects:
        if obj.type=='LIGHT': obj.location=center+normal*6+Vector((-3,-4,11))
    bpy.ops.mesh.primitive_plane_add(size=length*8,location=(cx,cy,.255))
    plane=bpy.context.object
    plane.data.materials.append(water)
    scene.render.filepath=str(output/(identity+'.jpg'))
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(plane,do_unlink=True)
    for obj in visible: obj.hide_render=True
    print('BRIDGE PREVIEW',identity,flush=True)
