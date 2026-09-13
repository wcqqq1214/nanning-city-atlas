"""Capture source-generated terrain and actual sampling with/without site grading.

The ungraded switch exists only in this audit script. It disables the optional
plan before importing the city to build a comparison from the same P5 inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ungraded',action='store_true')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    import site_grading
    selected=site_grading.PLAN
    assert selected is not None,'Prepare a source-bound grading plan first'
    if args.ungraded:site_grading.PLAN=None
    from capture_native_terrain import capture
    from terrain_reduction_runtime import collect
    from terrain_mesh import NATIVE_DATA_INPUTS
    result={'status':'native site grading audit; final roads, access and full city pending',
            'siteGradingDisabledForComparison':args.ungraded,'profiles':{},
            'inputHashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in NATIVE_DATA_INPUTS},
            'planHash':hashlib.sha256((ROOT/'data/block-grading-plan.json').read_bytes()).hexdigest()}
    for profile in ['detail','smooth']:
        env=capture(profile);triangles,materials,normals=collect(bpy.data.objects['Terrain'].children_recursive)
        output=args.output/(profile+'.npz');np.savez_compressed(output,triangles=triangles,materials=materials,cornerNormals=normals)
        record={'triangles':len(triangles),'rngState':env['RNG'].getstate(),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
        if not args.ungraded:
            maximum=0.;count=0;witness=None
            for patch,surface,dropped in selected.surfaces(env['unpatched_height'],tuple(env['GEO']['bounds']),env['COLS'],env['ROWS'],profile=='smooth',env['coarse_terrain_surface']):
                for t in surface.triangles:
                    for q in [*t,tuple(sum(v[k] for v in t)/3 for k in range(3))]:
                        z=env['terrain_surface'](q[0],q[1],env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                        difference=abs(z-q[2])*100
                        if difference>maximum:maximum=difference;witness={'point':list(q),'sampled':z}
                        count+=1
            record.update(samplerPoints=count,maximumSamplerErrorMeters=maximum,witness=witness)
            result['profiles'][profile]=record
            (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
            assert maximum<1e-5,(profile,maximum)
        result['profiles'][profile]=record
        print(profile,record['triangles'],record.get('maximumSamplerErrorMeters'),flush=True)
    result['tools']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                     [Path(__file__).resolve(),ROOT/'blender/site_grading.py',ROOT/'blender/terrain_mesh.py',ROOT/'blender/forest_canopy.py',ROOT/'blender/build_city.py',ROOT/'blender/site_access_plan.py',ROOT/'blender/nanhu_terrain.py',ROOT/'blender/nanhu_landmark.py',ROOT/'blender/reduced_surface.py']}
    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
