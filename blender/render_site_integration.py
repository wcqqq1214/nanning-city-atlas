"""Inspect compound candidates on imported, actually compressed city context.

This is a staging review of the supplied context and warehouse candidates.
An optional original road context contributes roads without its old terrain.
Other city buildings and vegetation remain separate work.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from block_massing import build_compound
from building_support_plan import BuildingSupportPlan
from render_block_grading import Mesh


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['context','geography','plan','support','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--road-context',type=Path,help='Import surrounding roads while excluding their original terrain')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True,exist_ok=True)
    geo=json.loads(args.geography.read_text());plan=json.loads(args.plan.read_text())
    support=json.loads(args.support.read_text())
    placement=BuildingSupportPlan.read(args.support,Path(__file__).resolve().parents[1])
    if support['inputs']['geography']['sha256']!=digest(args.geography):raise ValueError('Stale building support geography')
    report={'status':'compound candidates on actual decoded contexts; full city and site visual acceptance pending',
            'views':[],'buildings':{},'inputs':{str(p):digest(p) for p in [args.geography,args.plan,args.support]},
            'tools':{p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('block_massing.py'),Path(__file__).with_name('building_support_plan.py'),Path(__file__).with_name('render_block_grading.py')]}}
    for profile in ['detail','smooth']:
        context=args.context/(profile+'.glb')
        if support['inputs'][profile]['sha256']!=digest(context):raise ValueError('Stale building support context')
        report['inputs'][str(context)]=digest(context)
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(context))
        if args.road_context:
            road_context=args.road_context/(profile+'.glb')
            sources=json.loads((args.road_context/'sources.json').read_text())['inputHashes']
            if sources['public/data/geography.json']!=digest(args.geography):raise ValueError('Surrounding roads use different geography')
            report['inputs'][str(road_context)]=digest(road_context)
            before=set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(road_context))
            for obj in set(bpy.data.objects)-before:
                if obj.type=='MESH' and obj.name.startswith('Terrain'):
                    mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
                    if mesh.users==0:bpy.data.meshes.remove(mesh)
        for site in plan['sites']:
            buildings=[b for b in geo['buildings'] if b['id'] in site['buildingIds']]
            if len(buildings)!=len(site['buildingIds']):raise ValueError('Missing site buildings')
            batch=Mesh((0,0));placed=[]
            for building in buildings:
                placed.append(build_compound(batch,building,placement.bounds(building),'wall'))
            batch.object(site['id']+' candidates')
            report['buildings'][profile+'/'+site['id']]=placed
            w,s,e,n=site['bounds'];target=Vector(((w+e)/2,(s+n)/2,site['targetSceneZ']))
            camera=bpy.data.objects.new('review camera',bpy.data.cameras.new('review camera'))
            bpy.context.collection.objects.link(camera);scene=bpy.context.scene;scene.camera=camera
            camera.data.type='ORTHO';camera.data.clip_end=1000
            scene.render.engine='BLENDER_WORKBENCH';shade=scene.display.shading
            shade.light='STUDIO';shade.studio_light='paint.sl';shade.show_shadows=True
            shade.show_cavity=True;shade.cavity_type='BOTH';shade.background_type='WORLD'
            scene.world.color=(.82,.84,.82)
            scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
            for view,offset,scale in [('west',(-5,-6,5),6.1),('north',(2,5,3),6.1),('top',(0,0,8),6.1)]:
                camera.data.ortho_scale=scale;camera.location=target+Vector(offset)
                camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
                for mode in ['gray','materials']:
                    shade.color_type='SINGLE' if mode=='gray' else 'MATERIAL';shade.single_color=(.64,.66,.65)
                    path=args.output/f'{site["id"]}-{profile}-{view}-{mode}.png'
                    scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
                    report['views'].append({'profile':profile,'site':site['id'],'view':view,'mode':mode,
                        'camera':{'location':list(camera.location),'target':list(target),'orthoScale':scale},
                        'path':str(path),'sha256':digest(path)})
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
