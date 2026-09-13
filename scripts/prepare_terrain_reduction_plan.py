"""Package an independently checked native reduction for explicit integration."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from terrain_reduction_plan import TerrainReductionPlan,mesh_digest
from local_terrain import MATERIAL_KEYS
from site_grading import PLAN as GRADING_PLAN, MATERIAL_KEYS as GRADING_MATERIALS
MATERIAL_KEYS=MATERIAL_KEYS+(GRADING_MATERIALS if GRADING_PLAN is not None else [])


def prepare(before,after,audit,capture,profile):
    if not audit['status'].startswith('native candidate checks passed'):
        raise ValueError('Candidate has not passed independent native checks')
    kept=np.asarray(after['originFaceIndices']);removed=np.setdiff1d(np.arange(len(before['triangles'])),kept[kept>=0])
    payload={'schemaVersion':1,'metersPerUnit':100,'profile':profile,
             'status':'explicit integration candidate; final road, export and city checks pending',
             'inputHashes':capture['inputHashes'],'materialKeys':MATERIAL_KEYS,
             'originalMeshSha256':mesh_digest(before['triangles'],before['materials']),
             'candidateMeshSha256':mesh_digest(after['triangles'],after['materials']),
             'removedOriginalFaces':removed.tolist(),
             'newTriangles':after['triangles'][kept<0].tolist(),'newMaterials':after['materials'][kept<0].tolist(),
             'heightToleranceMeters':audit['heightToleranceMeters'],'normalToleranceDegrees':audit['normalToleranceDegrees'],
             'savedTriangles':audit['savedTriangles']}
    plan=TerrainReductionPlan(payload,ROOT)
    triangles,materials=plan.apply(before['triangles'],before['materials'],profile)
    if not np.array_equal(triangles,after['triangles']) or not np.array_equal(materials,after['materials']):
        raise ValueError('Packaged candidate differs from audited arrays')
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['before','after','audit','capture','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--profile',choices=['detail','smooth'],required=True);args=p.parse_args()
    audit=json.loads(args.audit.read_text());capture=json.loads(args.capture.read_text())
    if capture['input']!='native '+args.profile:raise ValueError('Capture profile mismatch')
    for path in [args.before,args.after]:
        if audit['inputs'].get(str(path))!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Audit input mismatch')
    # The capture's original archive is stored beside its manifest.
    if (args.capture.parent/'original.npz').read_bytes()!=args.before.read_bytes():raise ValueError('Capture source mismatch')
    payload=prepare(np.load(args.before),np.load(args.after),audit,capture,args.profile)
    payload['evidenceHashes']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.before,args.after,args.audit,args.capture]}
    payload['toolHashes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'blender/terrain_reduction_plan.py',ROOT/'blender/reduced_surface.py']}
    raw=(json.dumps(payload,separators=(',',':'))+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(gzip.compress(raw,mtime=0) if args.output.suffix=='.gz' else raw)
    print(json.dumps({'output':str(args.output),'bytes':args.output.stat().st_size,'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      'savedTriangles':payload['savedTriangles']},indent=2))
