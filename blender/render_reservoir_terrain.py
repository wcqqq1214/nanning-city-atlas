"""Fixed Workbench views of the exported reservoir candidate, with no city claim."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['plan','exports','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--terrain-context',action='store_true',help='Label captures of the production terrain and water, without complete city layers')
    parser.add_argument('--adaptive-height',action='store_true',help='Aim each camera at the nearest actual terrain vertex height instead of the legacy fixed height')
    parser.add_argument('--no-shadows',action='store_true',help='Disable Workbench shadow artifacts for geometry inspection; cavity shading remains enabled')
    parser.add_argument('--extra-views',type=Path,help='Source-derived additional fixed cameras for pools and water transitions')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);plan=json.loads(args.plan.read_text());args.output.mkdir(parents=True,exist_ok=True)
    views=[]
    for profile in ['detail','smooth']:
        path=args.exports/(profile+'.blend');bpy.ops.wm.open_mainfile(filepath=str(path))
        scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';shading=scene.display.shading
        shading.light='STUDIO';shading.studio_light='paint.sl';shading.color_type='MATERIAL'
        shading.show_shadows=not args.no_shadows;shading.show_cavity=True;shading.cavity_type='BOTH'
        shading.background_type='WORLD';scene.world.color=(.82,.84,.82)
        scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
        camera=bpy.data.objects.new('reservoir_camera',bpy.data.cameras.new('reservoir_camera'));bpy.context.collection.objects.link(camera)
        scene.camera=camera;camera.data.type='ORTHO';camera.data.clip_end=200
        height_tree=None;terrain_positions=[]
        if args.adaptive_height:
            for obj in bpy.data.objects:
                if obj.type=='MESH' and (obj.name.startswith('Reservoir_terrain') or obj.name.startswith('Terrain_reservoir_')):
                    terrain_positions.extend([obj.matrix_world@v.co for v in obj.data.vertices])
            if not terrain_positions:raise ValueError('Adaptive camera requires the actual reservoir terrain mesh')
            height_tree=KDTree(len(terrain_positions))
            for index,p in enumerate(terrain_positions):height_tree.insert((p.x,p.y,0),index)
            height_tree.balance()
        bounds=plan['bounds'];cx,cy=(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2
        default_offset=(.8,-1,.95)
        targets=[('overview',Vector((cx,cy,1)),max(bounds[2]-bounds[0],bounds[3]-bounds[1])*1.15,default_offset)]
        for dam in plan['dams']:
            ring=dam['footprint']['coordinates'][0][:-1]
            x=sum(p[0] for p in ring)/len(ring);y=sum(p[1] for p in ring)/len(ring)
            scale=max(max(p[0] for p in ring)-min(p[0] for p in ring),max(p[1] for p in ring)-min(p[1] for p in ring))+1.3
            targets.append((dam['sourceRef'].split('/')[-1],Vector((x,y,.8)),scale,default_offset))
        if args.extra_views:
            extra=json.loads(args.extra_views.read_text())
            if extra['planSha256']!=hashlib.sha256(args.plan.read_bytes()).hexdigest():raise ValueError('Extra views reference a different plan')
            targets.extend((v['name'],Vector(v['target']),v['orthoScale'],v.get('cameraOffsetFactors',default_offset)) for v in extra['views'])
        for name,target,scale,offset in targets:
            if len(offset)!=3 or not all(math.isfinite(v) for v in offset) or sum(v*v for v in offset)==0:
                raise ValueError('Camera offset must be a finite nonzero XYZ vector')
            if height_tree is not None:
                _,index,_=height_tree.find((target.x,target.y,0));target.z=terrain_positions[index].z
            camera.data.ortho_scale=scale;camera.location=target+Vector([scale*v for v in offset])
            camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
            output=args.output/(profile+'-'+name+'.png');scene.render.filepath=str(output);bpy.ops.render.render(write_still=True)
            views.append({'profile':profile,'view':name,'blendSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                          'image':str(output),'imageSha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                          'cameraLocation':list(camera.location),'target':list(target),'orthoScale':scale,
                          'targetHeightMethod':'nearest actual terrain vertex' if args.adaptive_height else 'legacy fixed height'})
            status='production terrain and water; complete city, roads and canopy omitted' if args.terrain_context else 'independent exported candidate; roads/canopy/city omitted'
            (args.output/'views.json').write_text(json.dumps({'status':status,'workbenchShadows':not args.no_shadows,'views':views},indent=2)+'\n')


if __name__=='__main__':main()
