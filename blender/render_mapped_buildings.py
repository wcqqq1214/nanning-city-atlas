"""Same-view native gray comparisons for selected ordinary courtyard buildings."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from render_block_rollout import Mesh
from mapped_buildings import build_mapped


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--ids',nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    old={b['id']:b for b in json.loads(args.before.read_text())['buildings']}
    new={b['id']:b for b in json.loads(args.candidate.read_text())['buildings']}
    records=[]
    for identity in args.ids:
        b=new[identity];xy=b['rings'][0][:-1]
        low=[min(p[k] for p in xy) for k in [0,1]];high=[max(p[k] for p in xy) for k in [0,1]]
        origin=[(a+c)/2 for a,c in zip(low,high)];extent=max(c-a for a,c in zip(low,high));top=b['height']/100*1.55
        for variant,building in [('before',old[identity]),('after',b)]:
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            mesh=Mesh(origin)
            if variant=='after':build_mapped(mesh,building,0,top,'wall')
            else:
                ring=building['rings'][0];z=building['height']/100*1.55
                for a,c in zip(ring,ring[1:]):mesh.face([(*a,0),(*c,0),(*c,z),(*a,z)],'wall')
                vertices=[Vector((*p,z)) for p in ring[:-1]]
                for triangle in tessellate_polygon([vertices]):
                    mesh.face([tuple(vertices[v] if isinstance(v,int) else v) for v in triangle],'roof')
            obj=mesh.object(identity)
            bpy.ops.mesh.primitive_plane_add(size=extent*8,location=(0,0,-.003))
            mat=bpy.data.materials.new('neutral ground');mat.diffuse_color=(.32,.34,.35,1);bpy.context.object.data.materials.append(mat)
            scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
            scene.world.color=(.15,.15,.15);scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
            scene.view_settings.view_transform='AgX'
            bpy.ops.object.light_add(type='SUN');light=bpy.context.object
            light.rotation_euler=(.45,-.6,-.5);light.data.energy=2;light.data.angle=.15
            bpy.ops.object.camera_add(location=(extent*.95,-extent*1.1,extent*1.8+top))
            camera=bpy.context.object;target=Vector((0,0,top*.3));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
            camera.data.type='ORTHO';camera.data.ortho_scale=extent*1.8;scene.camera=camera
            name=identity.replace('/','-')+'-'+variant+'.png';scene.render.filepath=str(args.output/name)
            bpy.ops.render.render(write_still=True)
            records.append({'id':identity,'variant':variant,'file':name,'camera':list(camera.location),'target':list(target),'orthoScale':camera.data.ortho_scale})
    report={'status':'isolated flat-base native geometry comparisons; not final city/site acceptance',
            'records':records,'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.before,args.candidate]},
            'tools':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'blender/mapped_buildings.py',ROOT/'blender/render_block_rollout.py']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
