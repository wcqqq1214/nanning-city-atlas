"""Same-camera native terrain comparison around the verified worst height error."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
import numpy as np


COLORS=[(.61,.67,.58,1),(.33,.48,.37,1),(.40,.54,.44,1),(.48,.58,.44,1),(.60,.60,.55,1),(.41,.48,.42,1)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['before','after','audit','output']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    audit=json.loads(args.audit.read_text())
    for f in [args.before,args.after]:
        assert audit['inputs'][str(f)]==hashlib.sha256(f.read_bytes()).hexdigest(),'Audit input mismatch'
    before=np.load(args.before);after=np.load(args.after)
    witness=audit['replacementAudit']['maximumErrorWitness']['sceneXY']
    new=after['triangles'][after['originFaceIndices']<0]
    target=Vector((*witness,float(new[:,:,2].mean())))
    # Recover the height at the witness from a containing triangle without
    # importing the venv-only geometry packages into Blender.
    for tri in new:
        a,b,c=tri;xy=np.array(witness)
        matrix=np.column_stack([b[:2]-a[:2],c[:2]-a[:2]])
        if abs(np.linalg.det(matrix))<1e-12:continue
        u,v=np.linalg.solve(matrix,xy-a[:2])
        if min(u,v,1-u-v)>=-1e-8:
            target.z=float(a[2]*(1-u-v)+b[2]*u+c[2]*v);break
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    palette=[]
    for i,color in enumerate(COLORS):
        m=bpy.data.materials.new('terrain material '+str(i));m.diffuse_color=color;palette.append(m)
    objects={}
    for name,data in [('before',before),('after',after)]:
        triangles=data['triangles'];xy=triangles[:,:,:2]
        keep=(xy[:,:,0].min(axis=1)<target.x+6)&(xy[:,:,0].max(axis=1)>target.x-6)&(xy[:,:,1].min(axis=1)<target.y+6)&(xy[:,:,1].max(axis=1)>target.y-6)
        triangles=triangles[keep];materials=data['materials'][keep]
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata(triangles.reshape(-1,3).tolist(),[],np.arange(len(triangles)*3).reshape(-1,3).tolist())
        for m in palette:mesh.materials.append(m)
        mesh.polygons.foreach_set('material_index',materials);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);objects[name]=obj
    scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
    scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.display.shading.light='STUDIO';scene.display.shading.studiolight_rotate_z=.65
    scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=False
    scene.display.shading.background_type='WORLD';scene.world.color=(.82,.84,.82)
    camera=bpy.data.objects.new('camera',bpy.data.cameras.new('camera'));bpy.context.collection.objects.link(camera)
    scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=5.;camera.data.clip_end=1000
    report={'status':'isolated native terrain visual comparison; no city dependents or Draco compression',
            'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.before,args.after,args.audit]},
            'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'target':list(target),'widthMeters':500,'views':[]}
    for mode in ['gray','materials']:
        scene.display.shading.color_type='SINGLE' if mode=='gray' else 'MATERIAL'
        scene.display.shading.single_color=(.65,.65,.65)
        for view,offset in [('top',(0,0,8)),('oblique',(3,-4,3))]:
            camera.location=target+Vector(offset);camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
            for variant,obj in objects.items():
                for other in objects.values():other.hide_render=other!=obj;other.hide_set(other!=obj)
                path=args.output/f'{mode}-{view}-{variant}.png';scene.render.filepath=str(path)
                bpy.ops.render.render(write_still=True)
                report['views'].append({'mode':mode,'view':view,'variant':variant,'cameraPosition':list(camera.location),
                                        'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'terrain-comparison.blend'))
    (args.output/'render-report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
