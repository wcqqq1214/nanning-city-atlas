"""Export a source-bound sluice against both actual lake/terrain profiles."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['scene-root','source','lake-plan','output']:p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.scene_root.resolve()
    sys.path.insert(0,str(root/'blender'));sys.path.insert(0,str(Path(__file__).parent))
    from water_control_structures import WaterControlStructure
    from reservoir_terrain import ReservoirTerrain
    from gltf_export import export_city
    source=root/'blender/build_city.py';tree=ast.parse(source.read_text())
    stop=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='TERRAIN_CONTEXT_ONLY')
    argv=sys.argv[:]
    try:
        sys.argv.append('--terrain-context');env={'__file__':str(source),'__name__':'__sluice_context__'}
        exec(compile(ast.Module(body=tree.body[:stop],type_ignores=[]),str(source),'exec'),env)
    finally:sys.argv[:]=argv
    lake=ReservoirTerrain.read(args.lake_plan);geo_path=Path(lake.payload['inputs']['geography']['path'])
    geo=json.loads(geo_path.read_text());spec=json.loads(args.source.read_text());model=WaterControlStructure(spec,geo)
    surfaces=[lake.surface(env['unpatched_height'],geo['bounds'],env['COLS'],env['ROWS'],light,env['coarse_terrain_surface'])[0] for light in [False,True]]
    result=model.geometry_on_surfaces(surfaces,lake.water_level)
    args.output.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    batch=env['Batch']('Reservoir_control_linglong',['viaduct_concrete','viaduct_metal'])
    for part in result['parts']:
        for face in part['faces']:batch.face(face,part['material'])
    batch.finish();obj=bpy.data.objects['Reservoir_control_linglong'];mesh=obj.data;mesh.calc_loop_triangles()
    native={'triangles':np.asarray([[tuple(mesh.vertices[i].co) for i in t.vertices] for t in mesh.loop_triangles]),
            'materials':np.asarray([t.material_index for t in mesh.loop_triangles]),
            'cornerNormals':np.asarray([[tuple(mesh.corner_normals[i].vector) for i in t.loops] for t in mesh.loop_triangles])}
    np.savez_compressed(args.output/'structure.npz',**native)
    export_city(args.output/'structure.glb')
    # The source member metadata permits an independent aperture and footprint
    # audit; the actual GLB is matched separately to the captured native mesh.
    (args.output/'geometry.json').write_text(json.dumps(result,indent=2)+'\n')
    structure=obj.copy();structure.data=obj.data.copy()
    for key,color in [('reservoir_ground',(.38,.48,.33,1)),('dam_slope',(.55,.57,.43,1)),('dam_crest',(.70,.72,.66,1)),('reservoir_water',(.20,.48,.59,1))]:
        material=bpy.data.materials.new(key);material.diffuse_color=color;env['MATS'][key]=material
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    for profile,surface in zip(['detail','smooth'],surfaces):
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        obj=structure.copy();obj.data=structure.data.copy();bpy.context.collection.objects.link(obj)
        terrain=env['Batch']('Reservoir_terrain',['reservoir_ground','dam_slope','dam_crest']);surface.emit(terrain);terrain.finish()
        banks=env['Batch']('Reservoir_banks',['dam_slope'])
        for face in lake.bank_faces(surface):banks.face(face,'dam_slope')
        banks.finish()
        water=env['Batch']('Reservoir_water_3',['reservoir_water'])
        entry=next(w for w in lake.payload['waterBodies'] if w['geographyWaterIndex']==spec['waterIndex'])
        if entry.get('waterMesh'):
            index=lake.payload['waterBodies'].index(entry)
            for face in lake.water_surface(index).triangles:water.face(face,'reservoir_water')
        else:
            rings=[[Vector((x,y,result['waterHeight'])) for x,y in r[:-1]] for r in entry['rings']];flat=[v for r in rings for v in r]
            for face in tessellate_polygon(rings):
                vertices=[flat[i] for i in face] if isinstance(face[0],int) else face
                a,b,c=vertices
                if (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)<0:vertices=list(reversed(vertices))
                water.face([tuple(v) for v in vertices],'reservoir_water')
        water.finish();bpy.ops.wm.save_as_mainfile(filepath=str(args.output/(profile+'.blend')))
    report={'status':'independent sluice on two candidate terrain profiles; city activation pending',
            'triangles':len(native['triangles']),'parts':len(result['parts']),
            'materialNames':[env['MATS'][key].name for key in ['viaduct_concrete','viaduct_metal']],
            'shorelineSupportSnapCount':result['shorelineSupportSnapCount'],'maximumShorelineSupportSnapMeters':result['maximumShorelineSupportSnapMeters'],
            'inputs':{str(p.resolve()):sha(p) for p in [args.source,args.lake_plan,geo_path,source,root/'public/data/terrain.json',
                       root/'blender/forest_canopy.py',Path(__file__),*[Path(__file__).with_name(n) for n in ['water_control_structures.py','reservoir_terrain.py','reduced_surface.py','gltf_export.py']]]},
            'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in args.output.iterdir() if p.suffix in ['.glb','.blend','.npz']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
