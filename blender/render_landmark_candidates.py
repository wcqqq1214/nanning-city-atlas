"""Compare P3 and P4 source-sized candidates on an isolated flat reference.

This never saves the city or exports public assets. The actual city sites,
platforms, replacement boundaries and interaction still need P4 acceptance.
Run with Blender --background --python-exit-code 1 --python this_file.py.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from render_scale_baseline import SampleMesh
import arts_landmark as arts
import zhenning_landmark as fort
from diwang_landmark import build_diwang


def main():
    output = ROOT/'work/urban-structure/p4/candidates'
    output.mkdir(exist_ok=True, parents=True)
    source = json.loads((ROOT/'data/landmark-calibration-plan.json').read_text())
    frozen = json.loads((ROOT/'work/urban-structure/baseline-p3/manifest.json').read_text())
    originals = {}
    for identity in ['arts_landmark', 'zhenning_landmark']:
        path = ROOT/'work/urban-structure/p4/baseline-sources'/f'{identity}.py'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == frozen['files'][f'blender/{identity}.py']['sha256']
        spec = importlib.util.spec_from_file_location(f'previous_{identity}', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        originals[identity] = module

    report = {'note': 'Isolated flat reference, not city-site acceptance. Same camera in each pair.',
              'baselineManifestSha256': hashlib.sha256((ROOT/'work/urban-structure/baseline-p3/manifest.json').read_bytes()).hexdigest(),
              'planSha256': hashlib.sha256((ROOT/'data/landmark-calibration-plan.json').read_bytes()).hexdigest(),
              'samples': {}}
    for identity in ['arts-center', 'zhenning', 'diwang']:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        gray = bpy.data.materials.new('neutral gray')
        gray.diffuse_color = (.52,.57,.54,1)
        meshes = {}
        params = source['sites'][identity]
        for variant in ['p3', 'candidate']:
            batch = SampleMesh()
            if identity == 'arts-center':
                module = originals['arts_landmark'] if variant=='p3' else arts
                kwargs = {} if variant=='p3' else {'display_scale':params['displayScale']}
                module.build_arts(batch,0,0,0,ground=lambda x,y:0,**kwargs)
            elif identity == 'zhenning':
                module = originals['zhenning_landmark'] if variant=='p3' else fort
                kwargs = {} if variant=='p3' else {'display_scale':params['displayScale'], 'height_scale':params['heightScale']}
                module.build_zhenning(batch,0,0,0,ground_bounds=lambda x,y:(0,0),**kwargs)
            elif variant=='p3':
                batch.box(0,0,0,.64,.64,4.25)
                batch.box(0,0,3.8,.42,.42,.8)
                batch.cone(0,0,4.6,.28,0,.46,segments=4)
            else:
                build_diwang(batch,0,0,0)
            meshes[variant] = batch.object(variant,gray)
            if variant=='p3' and identity in ['arts-center','zhenning']:
                check = SampleMesh()
                if identity=='arts-center': arts.build_arts(check,0,0,0,ground=lambda x,y:0)
                else: fort.build_zhenning(check,0,0,0,ground_bounds=lambda x,y:(0,0))
                assert batch.vertices == check.vertices and batch.faces == check.faces, 'Default geometry changed before integration'
        measurements = {}
        for variant,obj in meshes.items():
            obj.data.calc_loop_triangles()
            measurements[variant] = {
                'boundsMeters': [[min(v.co[i] for v in obj.data.vertices)*100 for i in range(3)],
                                 [max(v.co[i] for v in obj.data.vertices)*100 for i in range(3)]],
                'triangles':len(obj.data.loop_triangles),
                'zeroAreaTriangles':sum(t.area<1e-12 for t in obj.data.loop_triangles)}
        assert measurements['candidate']['zeroAreaTriangles']==0, identity
        candidate = meshes['candidate']
        if identity=='diwang':
            assert abs(max(v.co.z for v in candidate.data.vertices)*100-276)<.0001
            assert measurements['candidate']['triangles']<1800
        if identity=='zhenning':
            assert abs(max(v.co.x for v in candidate.data.vertices)*100-20.5)<.0001
            for side in [-1,1]:
                for u in [-.9,0,.9]:
                    hit,*_ = candidate.ray_cast(Vector((u/100,side*.20,.015)),Vector((0,-side,0)),distance=.083)
                    assert not hit, 'Candidate gate blocked'
            for angle in [0,math.pi/2,math.pi,3*math.pi/2]:
                hit,point,*_ = candidate.ray_cast(Vector((.08*math.cos(angle),.08*math.sin(angle),.062)),Vector((0,0,-1)),distance=.02)
                assert hit and .047<point.z<.051, 'Candidate bridge missing'
            for angle in [math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4]:
                hit,point,*_ = candidate.ray_cast(Vector((.08*math.cos(angle),.08*math.sin(angle),.10)),Vector((0,0,-1)),distance=.11)
                assert hit and abs(point.z)<.00002, 'Candidate courtyard covered'
        high = max(max(v.co.z for v in obj.data.vertices) for obj in meshes.values())
        extent = max(max(v.co[i] for obj in meshes.values() for v in obj.data.vertices)-
                     min(v.co[i] for obj in meshes.values() for v in obj.data.vertices) for i in range(3))
        target = Vector((0,0,high*.48))
        bpy.ops.object.camera_add(location=(0,-extent*2,extent))
        camera = bpy.context.object
        camera.data.type='ORTHO';camera.data.ortho_scale=extent*1.35
        scene=bpy.context.scene;scene.camera=camera
        scene.render.engine='BLENDER_WORKBENCH'
        scene.display.shading.light='STUDIO'
        scene.display.shading.color_type='MATERIAL'
        scene.display.shading.show_shadows=True
        scene.display.shading.show_cavity=True
        scene.display.shading.cavity_type='BOTH'
        scene.display.shading.background_type='WORLD'
        scene.world.color=(.86,.88,.85)
        scene.render.resolution_x=800;scene.render.resolution_y=700;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG'
        cameras={}
        for view,direction in [('front',(0,-2,0)),('side',(2,0,0)),('back',(0,2,0)),('above',(1,-1,2))]:
            camera.location=target+Vector(direction)*extent
            camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
            cameras[view]={'position':list(camera.location),'target':list(target),'orthographicScale':camera.data.ortho_scale}
            for variant in ['p3','candidate']:
                for name,obj in meshes.items(): obj.hide_render=name!=variant
                scene.render.filepath=str(output/f'{identity}-{variant}-{view}.png')
                bpy.ops.render.render(write_still=True)
        report['samples'][identity]={'geometry':measurements,'cameras':cameras}
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(f'PASS: {identity} candidate geometry and four paired views',flush=True)


if __name__=='__main__': main()
