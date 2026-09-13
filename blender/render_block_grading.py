"""Compare the same warehouse candidate before/after actual-terrain grading."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from block_grading import GradePatch
from block_massing import build_compound

COLORS={'ground':(.31,.39,.32,1),'block_paving':(.61,.61,.56,1),
        'block_retaining':(.40,.44,.43,1),'wall':(.66,.69,.67,1),'roof':(.79,.81,.78,1),
        'road':(.20,.24,.25,1)}


class Mesh:
    def __init__(self,origin):self.origin=origin;self.vertices=[];self.faces=[];self.materials=[]
    def face(self,points,material):
        first=len(self.vertices);self.vertices.extend([(x-self.origin[0],y-self.origin[1],z) for x,y,z in points])
        self.faces.append(list(range(first,len(self.vertices))));self.materials.append(material)
    def object(self,name):
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(self.vertices,[],self.faces);mesh.update()
        assert not mesh.validate(),name
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
        for key,color in COLORS.items():
            mat=bpy.data.materials.get(key) or bpy.data.materials.new(key);mat.diffuse_color=color;mesh.materials.append(mat)
        keys=list(COLORS)
        for polygon,key in zip(mesh.polygons,self.materials):polygon.material_index=keys.index(key)
        mesh.calc_loop_triangles()
        collapsed={t.polygon_index for t in mesh.loop_triangles if t.area==0}
        if collapsed:
            # Tiny overlay needles can collapse at Blender's float32 storage.
            # Drop only triangles with exactly zero rendered area, and record it.
            if any(len(mesh.polygons[i].vertices)!=3 for i in collapsed):raise ValueError('Collapsed non-triangle')
            faces=[face for i,face in enumerate(self.faces) if i not in collapsed]
            keys_kept=[key for i,key in enumerate(self.materials) if i not in collapsed]
            mesh.clear_geometry();mesh.from_pydata(self.vertices,[],faces);mesh.update()
            for polygon,key in zip(mesh.polygons,keys_kept):polygon.material_index=keys.index(key)
            obj['float32CollapsedTriangles']=len(collapsed)
            mesh.calc_loop_triangles()
        assert all(t.area>0 for t in mesh.loop_triangles),name
        return obj


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['plan','geography','support','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--access',type=Path,help='Road-edge connector and replaced supporting terrain')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    result=json.loads(args.plan.read_text());geo=json.loads(args.geography.read_text())
    support={r['id']:r for r in json.loads(args.support.read_text())['records']}
    access=json.loads(args.access.read_text()) if args.access else None
    report={'status':'isolated warehouse grading comparison; city roads and surrounding city omitted',
            'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.plan,args.geography,args.support]},
            'tools':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                     [Path(__file__).resolve(),ROOT/'blender/block_grading.py',ROOT/'blender/block_massing.py']},'views':[]}
    if access:
        report['inputs'][str(args.access)]=hashlib.sha256(args.access.read_bytes()).hexdigest()
        report['status']='isolated warehouse/access candidate with resolved P4 road context; not final city acceptance'
    for plan in result['sites']:
        origin=[(plan['bounds'][i]+plan['bounds'][i+2])/2 for i in [0,1]]
        buildings=[b for b in geo['buildings'] if b['id'] in plan['buildingIds']]
        for profile,metrics in result['profiles'][plan['id']].items():
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            objects={}
            connector=access['sites'][plan['id']][profile] if access else None
            if connector:
                roads=Mesh(origin)
                for triangle in connector['contextRoadTriangles']:roads.face(triangle,'road')
                roads.object('retained resolved road context')
            base={tuple(p):z for p,z in zip(plan['points'],metrics['baseVertexLevels'])}
            for variant in ['before','graded']:
                ground=Mesh(origin);batch=Mesh(origin)
                if variant=='graded' and connector:
                    for triangle,material in zip(connector['terrainTriangles'],connector['terrainMaterials']):
                        if material=='base':material='ground'
                        elif material=='ground':
                            a,b,c=map(Vector,triangle);normal=(b-a).cross(c-a)
                            if abs(normal.z)>1e-12 and Vector((normal.x,normal.y)).length/abs(normal.z)>plan['retainingFaceGradeThreshold']:
                                material='block_retaining'
                        ground.face(triangle,material)
                    edges={}
                    for ids in connector['triangles']:
                        batch.face([connector['topPoints'][i] for i in ids],'road')
                        for a,b in zip(ids,ids[1:]+ids[:1]):
                            key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
                    for (a,b),count in edges.items():
                        if count==1:
                            upper=[connector['topPoints'][i] for i in [a,b]]
                            lower=[connector['soilPoints'][i] for i in [a,b]]
                            for triangle in [[upper[0],lower[0],upper[1]],[upper[1],lower[0],lower[1]]]:
                                va,vb,vc=map(Vector,triangle)
                                if (vb-va).cross(vc-va).length>1e-12:batch.face(triangle,'road')
                elif variant=='graded':GradePatch(plan).build(ground,lambda x,y:base[(x,y)],lambda x,y:'ground')
                else:
                    for ids in plan['triangles']:
                        ground.face([(*plan['points'][i],metrics['baseVertexLevels'][i]) for i in ids],'ground')
                for b in buildings:
                    levels=[plan['targetSceneZ']]*2 if variant=='graded' else support[b['id']]['groundRangeSceneZ']
                    build_compound(batch,b,levels,'wall')
                objects[variant]=[ground.object(variant+' terrain'),batch.object(variant+' warehouses')]
                if variant=='graded':report.setdefault('retainingFaces',{})[profile]=Counter(ground.materials)['block_retaining']
            camera=bpy.data.objects.new('camera',bpy.data.cameras.new('camera'));bpy.context.collection.objects.link(camera)
            scene=bpy.context.scene;scene.camera=camera;scene.render.engine='BLENDER_WORKBENCH'
            scene.display.shading.light='STUDIO';scene.display.shading.studio_light='paint.sl'
            scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
            scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH'
            scene.display.shading.background_type='WORLD';scene.world.color=(.82,.84,.82)
            scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
            camera.data.type='ORTHO';camera.data.ortho_scale=6.1;camera.data.clip_end=100
            target=Vector((0,0,plan['targetSceneZ']))
            views=[('west',(-5,-6,5)),('east',(6,-4,3.7))]
            if connector:views.append(('access',(-1.6,-2,1.4)))
            for view,offset in views:
                focus=target.copy();camera.data.ortho_scale=6.1
                if view=='access':
                    mouth=connector['contacts'][len(connector['contacts'])//2]
                    focus=Vector((mouth['point'][0]-origin[0]+.18,mouth['point'][1]-origin[1],mouth['top']))
                    camera.data.ortho_scale=1.4
                camera.location=focus+Vector(offset);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler()
                for variant,shown in objects.items():
                    for group in objects.values():
                        for obj in group:obj.hide_render=obj not in shown;obj.hide_set(obj not in shown)
                    path=args.output/f'{plan["id"]}-{profile}-{view}-{variant}.png'
                    scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
                    report['views'].append({'profile':profile,'view':view,'variant':variant,'path':str(path),
                                            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                            'float32CollapsedTriangles':sum(o.get('float32CollapsedTriangles',0) for o in shown),
                                            'triangles':sum(len(o.data.loop_triangles) for o in shown)})
            bpy.ops.wm.save_as_mainfile(filepath=str(args.output/f'{plan["id"]}-{profile}.blend'))
    (args.output/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
