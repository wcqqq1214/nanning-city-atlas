"""Exercise the production building exclusion, road capture and sluice emitter."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.scene_root.resolve()
    sys.path.insert(0,str(root/'blender'))
    from capture_native_terrain import capture
    from reservoir_runtime import CONTROLS,DAM_IDS
    from road_inputs import capture_building_levels
    from terrain_reduction_runtime import collect
    from terrain_mesh import NATIVE_DATA_INPUTS
    from building_placement import prepared
    from gltf_export import export_city
    if CONTROLS is None or len(CONTROLS.records)!=1:raise ValueError('This capture expects one active sluice')
    source=root/'blender/build_city.py';tree=ast.parse(source.read_text())
    visibility=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='building_visible')
    loop=next(n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)
              and [v.id for v in n.target.elts if isinstance(v,ast.Name)]==['building_index','b'])
    emit=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='water_control_records' for t in n.targets))
    water_start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='water' for t in n.targets))
    water_end=next(i for i,n in enumerate(tree.body[water_start:],water_start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                   and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name)
                   and n.value.func.value.id=='custom_water' and n.value.func.attr=='finish')
    compile_nodes=lambda nodes:compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);records={}
    for profile in ['detail','smooth']:
        env=capture(profile);geo=env['GEO'];all_dams=[b for b in geo['buildings'] if b['id'] in DAM_IDS]
        if len(all_dams)!=len(DAM_IDS):raise ValueError('Missing mapped dam records')
        sentinel=next(b for i,b in enumerate(geo['buildings']) if b['id'] not in DAM_IDS and not prepared(b) and not b.get('blockId')
                      and env['city_visibility'].building_visible(b,railway_hidden=i in env['RAILWAY_BUILDINGS']))
        hidden_ids={geo['buildings'][i]['id'] for i in env['RAILWAY_BUILDINGS']}
        saved_hidden=env['RAILWAY_BUILDINGS'];saved_rng=env['RNG'].getstate();batches=[]
        exec(compile_nodes([visibility]),env)
        for selected in [[sentinel],[sentinel,*all_dams]]:
            env['GEO']={**geo,'buildings':selected};env['RAILWAY_BUILDINGS']={i for i,b in enumerate(selected) if b['id'] in hidden_ids}
            env.update(buildings=env['Batch']('Buildings',['building','building2','building3','roof']),legacy_palette={},
                       road_building_limits={},road_building_envelopes={},mapped_buildings_batch=None,block_support=[],prepared_building_records=[])
            env['RNG'].setstate(saved_rng);exec(compile_nodes([loop]),env);batches.append(env['buildings'])
        a,b=batches
        if not a.f or a.v!=b.v or a.f!=b.f or a.mi!=b.mi:raise ValueError('Mapped dams leaked into the ordinary-building branch')
        volumes=capture_building_levels(env)
        if len(volumes)!=1 or volumes[0][0]!=0:raise ValueError('Mapped dams leaked into road building volumes')
        env['GEO']=geo;env['RAILWAY_BUILDINGS']=saved_hidden;env['RNG'].setstate(saved_rng)
        env['buildings_group']=b.finish()
        exec(compile_nodes([emit]),env);entry=env['water_control_records'][0];obj=bpy.data.objects[entry['node']]
        if obj.parent is not env['buildings_group']:raise ValueError('Sluice must follow the Buildings layer')
        positions,materials,normals=collect([obj]);folder=output/profile;folder.mkdir(exist_ok=True)
        np.savez_compressed(folder/'structure.npz',triangles=positions,materials=materials,cornerNormals=normals)
        (folder/'geometry.json').write_text(json.dumps(entry['geometry'],indent=2)+'\n')
        exec(compile_nodes(tree.body[water_start:water_end+1]),env)
        blend=output/(profile+'.blend');bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        # Export the actual production child, retaining its identity parent.
        for other in list(bpy.data.objects):
            if other.type=='MESH' and other is not obj:bpy.data.objects.remove(other,do_unlink=True)
        export_city(folder/'structure.glb')
        paths=[*[root/name for name in NATIVE_DATA_INPUTS],source,root/'blender/forest_canopy.py',root/'blender/road_inputs.py',
               root/'blender/gltf_export.py',Path(__file__)]
        report={'status':'production structural branch and 11-dam building/road exclusion audit; complete city roads/support still pending',
                'node':entry['node'],'parent':'Buildings','damIds':sorted(DAM_IDS),'ordinarySentinelId':sentinel['id'],
                'ordinaryProbeFaces':len(b.f),'roadProbeVolumes':volumes,'triangles':len(positions),
                'materialNames':[m.name for m in obj.data.materials],
                'usesFinalCitySampler':entry['geometry']['usesFinalCitySampler'],
                'inputs':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                'blendSha256':hashlib.sha256(blend.read_bytes()).hexdigest()}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n');records[profile]=report
        print(profile,len(positions),'triangles;',len(DAM_IDS),'dam exclusions',flush=True)
    if not np.array_equal(np.load(output/'detail/structure.npz')['triangles'],np.load(output/'smooth/structure.npz')['triangles']):
        raise ValueError('Structural geometry differs between profiles')
    (output/'report.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__=='__main__':main()
