"""Exercise the real city sampler and native emitter with an explicit reduction."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from capture_native_terrain import capture
from terrain_reduction_runtime import configure,apply_existing,collect
from terrain_reduction_plan import suspended


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True,exist_ok=True);env=capture('smooth')
    state=env['RNG'].getstate();plan=configure(env,args.plan)
    assert state==env['RNG'].getstate(),'Reduction prepass changed palette RNG'
    group=apply_existing(env,'smooth',bpy.data.objects['Terrain'])
    triangles,materials,normals=collect(group.children_recursive)
    np.savez_compressed(args.output/'native.npz',triangles=triangles,materials=materials,cornerNormals=normals)
    def query(x,y,m):return env['terrain_surface'](x,y,env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],m)
    error=0.;legacy_difference=0.;legacy_witness=None;detail_difference=0.;count=0
    points=[p for triangle in plan.surface.triangles for p in [*triangle,tuple(sum(v[k] for v in triangle)/3 for k in range(3))]]
    with suspended():
        old_smooth=[query(p[0],p[1],True) for p in points]
        old_detail=[query(p[0],p[1],False) for p in points]
    for p,previous,detail in zip(points,old_smooth,old_detail):
        actual=query(p[0],p[1],True);error=max(error,abs(actual-p[2])*100)
        difference=abs(actual-previous)*100
        if difference>legacy_difference:legacy_difference=difference;legacy_witness=list(p)
        detail_difference=max(detail_difference,abs(query(p[0],p[1],False)-detail)*100);count+=1
    assert error<1e-5 and detail_difference==0
    env['export_city'](args.output/'terrain.glb')
    report={'status':'explicit runtime terrain/sampler candidate checked; roads, paths, buildings and full city pending',
            'nativeTriangles':len(triangles),'samples':count,'maximumFinalSamplerErrorMeters':error,
            'maximumDetailSamplerChangeMeters':detail_difference,'paletteRngPreserved':True,
            'maximumChangeFromLegacySamplerMeters':legacy_difference,'legacySamplerDifferenceWitness':legacy_witness,
            'planSha256':hashlib.sha256(args.plan.read_bytes()).hexdigest(),
            'files':{name:{'bytes':(args.output/name).stat().st_size,'sha256':hashlib.sha256((args.output/name).read_bytes()).hexdigest()} for name in ['native.npz','terrain.glb']},
            'toolHashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'blender/terrain_reduction_runtime.py',ROOT/'blender/terrain_reduction_plan.py',ROOT/'blender/forest_canopy.py',ROOT/'blender/terrain_mesh.py',ROOT/'blender/build_city.py']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
