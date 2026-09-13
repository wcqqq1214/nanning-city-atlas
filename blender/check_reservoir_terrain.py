"""Export a reservoir candidate against the city's actual base-height callbacks."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['scene-root','plan','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--baseline-plan',type=Path,help='Verify inactive-cell removal against the prior prepared surface')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.scene_root.resolve()
    sys.path.insert(0,str(root/'blender'));sys.path.insert(0,str(Path(__file__).parent))
    from reservoir_terrain import ReservoirTerrain
    from gltf_export import export_city
    import gltf_export
    from terrain_height import scene_height
    plan=ReservoirTerrain.read(args.plan);args.output.mkdir(parents=True,exist_ok=True)
    baseline=ReservoirTerrain.read(args.baseline_plan) if args.baseline_plan else None
    if baseline:
        for field in ['waterBodies','dams','protectedWaterBanks']:
            if baseline.payload[field]!=plan.payload[field]:raise ValueError('Inactive-cell optimization changed '+field)
        old_points={tuple(q):i for i,q in enumerate(baseline.payload['points'])}
        for field in ['weights','targetMeters','rawSourceMeters']:
            if plan.payload[field]!=[baseline.payload[field][old_points[tuple(q)]] for q in plan.payload['points']]:
                raise ValueError('Inactive-cell optimization changed retained '+field)
    source=root/'blender/build_city.py';tree=ast.parse(source.read_text())
    stop=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='TERRAIN_CONTEXT_ONLY')
    argv=sys.argv[:]
    try:
        sys.argv.append('--terrain-context')
        env={'__file__':str(source),'__name__':'__reservoir_context__'}
        exec(compile(ast.Module(body=tree.body[:stop],type_ignores=[]),str(source),'exec'),env)
    finally:sys.argv[:]=argv
    # The comparison callback is from the frozen, pre-activation city context.
    # Its DEM must match the candidate's input DEM; geography intentionally
    # differs only because the candidate has not yet been activated.
    assert digest(root/'public/data/terrain.json')==plan.payload['inputs']['terrain']['sha256']
    for key,color in [('reservoir_ground',(.38,.48,.33,1)),('dam_slope',(.55,.57,.43,1)),('dam_crest',(.70,.72,.66,1)),('reservoir_water',(.20,.48,.59,1))]:
        material=bpy.data.materials.new(key);material.diffuse_color=color;env['MATS'][key]=material
    report={'status':'independent native reservoir export; full city replacement and compressed audit pending',
            'planSha256':digest(args.plan),'baseCityRoot':str(root),'profiles':{},
            'baseContextHashes':{name:digest(root/name) for name in ['public/data/geography.json','public/data/terrain.json','blender/build_city.py','blender/forest_canopy.py']},
            'toolHashes':{str(p):digest(p) for p in [Path(__file__).resolve(),Path(__file__).with_name('reservoir_terrain.py'),Path(gltf_export.__file__)]}}
    if baseline:report['baselinePlanSha256']=digest(args.baseline_plan)
    for profile in ['detail','smooth']:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        surface,collapsed=plan.surface(env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth',env['coarse_terrain_surface'])
        restoration=None
        if baseline:
            old,old_collapsed=baseline.surface(env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth',env['coarse_terrain_surface'])
            if old_collapsed or collapsed:raise ValueError('Inactive-cell comparison cannot discard collapsed faces')
            key=lambda triangle:tuple(tuple(p) for p in triangle)
            retained={key(t):m for t,m in zip(surface.triangles,surface.materials)}
            previous={key(t):m for t,m in zip(old.triangles,old.materials)}
            if len(retained)!=len(surface.triangles) or len(previous)!=len(old.triangles):raise ValueError('Duplicate comparison triangle')
            if any(previous.get(k)!=m for k,m in retained.items()):raise ValueError('A retained native face or material changed')
            error=0.;centroid_change=0.;change_location=None;samples=0;removed=0
            for triangle in old.triangles:
                if key(triangle) in retained:continue
                removed+=1
                for q in triangle:
                    expected=env['coarse_terrain_surface'](q[0],q[1],env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                    error=max(error,abs(expected-q[2])*100);samples+=1
                q=np.mean(triangle,axis=0)
                expected=env['coarse_terrain_surface'](q[0],q[1],env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                change=abs(expected-q[2])*100
                if change>centroid_change:
                    centroid_change=change;change_location=[float(q[0]),float(q[1]),float(q[2]),float(expected)]
            if error>.005:raise ValueError(f'Restored base differs from removed native vertices: {error} m')
            # Dense triangulation can cut across an original base diagonal.
            # Returning to that source mesh changes the interior interpolation;
            # report it explicitly, while requiring its sampled vertices exact.
            restoration={'retainedFacesExact':len(retained),'removedFaces':removed,'restoredBaseVertexSamples':samples,
                         'maximumRemovedVertexBaseErrorMeters':error,'maximumRemovedCentroidChangeMeters':centroid_change,
                         'maximumRemovedCentroidChangeLocation':change_location}
        batch=env['Batch']('Reservoir_terrain',['reservoir_ground','dam_slope','dam_crest'])
        surface.emit(batch);batch.finish()
        # Keep each mapped water polygon and every island hole in a separate
        # mesh; Blender triangulates it from its source ring constraints.
        from mathutils.geometry import tessellate_polygon
        from mathutils import Vector
        for water_index,entry in enumerate(plan.payload['waterBodies']):
            z=scene_height(entry['levelMeters'],plan.dem)
            rings=[[Vector((x,y,z)) for x,y in ring[:-1]] for ring in entry['rings']]
            water_batch=env['Batch']('Reservoir_water_'+str(entry['geographyWaterIndex']),['reservoir_water'])
            if entry.get('waterMesh'):
                plan.water_surface(water_index).emit(water_batch);water_batch.finish();continue
            flat=[p for ring in rings for p in ring]
            for face in tessellate_polygon(rings):
                triangle=[flat[i] for i in face] if isinstance(face[0],int) else list(face)
                a,b,c=triangle
                if (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)<0:triangle.reverse()
                water_batch.face([tuple(p) for p in triangle],'reservoir_water')
            water_batch.finish()
        # Close the short vertical bank between the shared land boundary and
        # its independently estimated water level; do not leave an open gap.
        edges={};directions={}
        for triangle in surface.triangles:
            for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1;directions[key]=(a,b)
        banks=env['Batch']('Reservoir_banks',['dam_slope']);bank_count=0
        for face in plan.bank_faces(surface):
            banks.face(face,'dam_slope');bank_count+=1
        banks.finish()
        maximum=0
        for triangle in surface.triangles:
            point=np.mean(triangle,axis=0);sample=surface.sample(float(point[0]),float(point[1]))
            if sample is None:raise ValueError('Native reservoir sampler misses a triangle centroid')
            maximum=max(maximum,abs(sample-point[2])*100)
        boundary_error=0.;boundary_samples=0;city_cut_error=0.;city_cut_samples=0;bounds=plan.payload['bounds']
        open_sides=plan.payload.get('restoredCityBoundarySides',[])
        sides=['west','south','east','north']
        for side in open_sides:
            k=sides.index(side)
            if abs(bounds[k]-env['GEO']['bounds'][k])>1e-9:raise ValueError('Only an actual city cut can have a restored open boundary')
        def city_cut_edge(a,b):
            return any(abs(a[k%2]-bounds[k])<1.5e-5 and abs(b[k%2]-bounds[k])<1.5e-5
                       for k,side in enumerate(sides) if side in open_sides)
        def base_boundary_edge(a,b):
            if city_cut_edge(a,b):return False
            segments=plan.payload.get('replacementBoundarySegments')
            if not segments:
                return any(abs(a[k]-limit)<1.5e-5 and abs(b[k]-limit)<1.5e-5 for k,limit in [(0,bounds[0]),(0,bounds[2]),(1,bounds[1]),(1,bounds[3])])
            for start,end in segments:
                start=np.asarray(start);direction=np.asarray(end)-start;length2=float(direction@direction)
                if not length2:continue
                def on(point):
                    delta=np.asarray(point[:2])-start;t=np.clip(float(delta@direction)/length2,0,1)
                    return np.linalg.norm(delta-t*direction)<1.5e-5
                if on(a) and on(b):return True
            return False
        for (a,b),count in edges.items():
            if count!=1:continue
            if city_cut_edge(a,b):
                for q in [a,b,tuple((a[k]+b[k])/2 for k in range(3))]:
                    xy=list(q[:2])
                    for k,side in enumerate(sides):
                        if side in open_sides and abs(q[k%2]-bounds[k])<1.5e-5:xy[k%2]=bounds[k]
                    z=plan.sample(*xy,env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth',env['coarse_terrain_surface'])
                    if z is None:raise ValueError('City cut sampler misses the declared atlas boundary')
                    city_cut_error=max(city_cut_error,abs(z-q[2])*100);city_cut_samples+=1
            if not base_boundary_edge(a,b):continue
            for q in [a,b,tuple((a[k]+b[k])/2 for k in range(3))]:
                expected=env['coarse_terrain_surface'](q[0],q[1],env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                boundary_error=max(boundary_error,abs(expected-q[2])*100);boundary_samples+=1
        if boundary_samples==0 or boundary_error>.005:raise ValueError(f'Reservoir outer seam differs from base profile: {boundary_error} m')
        if open_sides and (not city_cut_samples or city_cut_error>.001):raise ValueError('Restored city cut differs from its shared sampler')
        protected_checks=[]
        for entry in plan.payload.get('protectedWaterBanks',[]):
            segments=[(a,b) for ring in entry['rings'] for a,b in zip(ring,ring[1:]) if a!=b]
            starts=np.asarray([a for a,b in segments]);direction=np.asarray([b for a,b in segments])-starts
            length2=np.sum(direction*direction,axis=1);lower=starts.min(axis=0)-.00005;upper=starts.max(axis=0)+.00005
            error=0.;samples=0
            for (a,b),count in edges.items():
                if count!=1:continue
                xy=(np.asarray(a[:2])+b[:2])/2
                if np.any(xy<lower) or np.any(xy>upper):continue
                delta=xy-starts;t=np.clip(np.sum(delta*direction,axis=1)/length2,0,1)
                if np.min(np.linalg.norm(delta-t[:,None]*direction,axis=1))>.00005:continue
                for fraction in [0,.25,.5,.75,1]:
                    q=np.asarray(a)*(1-fraction)+np.asarray(b)*fraction
                    expected=env['coarse_terrain_surface'](q[0],q[1],env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                    error=max(error,abs(expected-q[2])*100);samples+=1
            if not samples or error>.005:raise ValueError(f'Protected water bank {entry["geographyWaterIndex"]} differs from original profile: {error} m ({samples} samples)')
            protected_checks.append({'geographyWaterIndex':entry['geographyWaterIndex'],'samples':samples,'maximumOriginalBankErrorMeters':error})
        mesh=bpy.data.objects['Reservoir_terrain'].data;mesh.calc_loop_triangles()
        native=np.array([[tuple(mesh.vertices[i].co) for i in t.vertices] for t in mesh.loop_triangles])
        native_normals=np.array([[tuple(mesh.corner_normals[i].vector) for i in t.loops] for t in mesh.loop_triangles])
        water_triangles=[];water_indices=[];bank_triangles=[];water_normals=[];bank_normals=[]
        for obj in bpy.data.objects:
            if obj.type!='MESH':continue
            if obj.name.startswith('Reservoir_water_'):
                obj.data.calc_loop_triangles()
                for face in obj.data.loop_triangles:
                    water_triangles.append([tuple(obj.data.vertices[i].co) for i in face.vertices])
                    water_normals.append([tuple(obj.data.corner_normals[i].vector) for i in face.loops])
                    water_indices.append(int(obj.name.split('_')[-1]))
            elif obj.name=='Reservoir_banks':
                obj.data.calc_loop_triangles();bank_triangles.extend([[tuple(obj.data.vertices[i].co) for i in t.vertices] for t in obj.data.loop_triangles])
                bank_normals.extend([[tuple(obj.data.corner_normals[i].vector) for i in t.loops] for t in obj.data.loop_triangles])
        np.savez_compressed(args.output/(profile+'.npz'),triangles=native,materials=np.array([t.material_index for t in mesh.loop_triangles]),
                            cornerNormals=native_normals,waterTriangles=np.asarray(water_triangles),waterIndices=np.asarray(water_indices),bankTriangles=np.asarray(bank_triangles),
                            waterCornerNormals=np.asarray(water_normals),bankCornerNormals=np.asarray(bank_normals))
        export_city(args.output/(profile+'.glb'))
        bpy.ops.wm.save_as_mainfile(filepath=str(args.output/(profile+'.blend')))
        report['profiles'][profile]={'triangles':len(native),'waterTriangles':len(water_triangles),'bankQuads':bank_count,'collapsedFaces':collapsed,'maxSamplerErrorMeters':maximum,
                                     'boundarySamples':boundary_samples,'maximumBoundaryErrorMeters':boundary_error,
                                     'restoredCityBoundarySides':open_sides,
                                     'cityCutSamples':city_cut_samples,'maximumCityCutSamplerErrorMeters':city_cut_error,
                                     'protectedWaterBanks':protected_checks,
                                     'files':{ext:{'sha256':digest(args.output/(profile+'.'+ext)),'bytes':(args.output/(profile+'.'+ext)).stat().st_size} for ext in ['npz','glb','blend']}}
        if restoration:report['profiles'][profile]['inactiveRestoration']=restoration
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(profile,report['profiles'][profile],flush=True)


if __name__=='__main__':main()
