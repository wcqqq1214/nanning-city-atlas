"""Audit a vertex-removal candidate independently of its acceptance checks.

Exact source-face provenance separates unchanged overlapping structures from the
replacement region. It never discards a face simply because errors are large.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.strtree import STRtree

from audit_terrain_reduction import audit
from prepare_building_support import TerrainSurface


def boundary_edges(triangles,materials):
    vertices,ids=np.unique(triangles.reshape(-1,3),axis=0,return_inverse=True)
    counts=Counter()
    for face,material in zip(ids.reshape(-1,3),materials):
        for a,b in zip(face,np.roll(face,-1)):
            counts[(int(material),min(a,b),max(a,b))]+=1
    return {(m,tuple(vertices[a]),tuple(vertices[b])):n for (m,a,b),n in counts.items() if n!=2}


def check(source,candidate,tolerance_meters=.05,normal_degrees=2.):
    before=np.asarray(source['triangles']);after=np.asarray(candidate['triangles'])
    bm=np.asarray(source['materials']);am=np.asarray(candidate['materials'])
    origins=np.asarray(candidate['originFaceIndices'])
    if len(origins)!=len(after) or not np.issubdtype(origins.dtype,np.integer):raise ValueError('Invalid source face indices')
    if np.any(origins < -1) or np.any(origins>=len(before)):raise ValueError('Source face index out of range')
    kept=origins[origins>=0]
    if len(set(kept))!=len(kept):raise ValueError('Repeated source face provenance')
    if not np.array_equal(after[origins>=0],before[kept]) or not np.array_equal(am[origins>=0],bm[kept]):
        raise ValueError('Claimed unchanged source faces differ')
    old_vertices={tuple(p) for p in before.reshape(-1,3)}
    if not all(tuple(p) in old_vertices for p in after.reshape(-1,3)):raise ValueError('Candidate moved or introduced a vertex')
    if boundary_edges(before,bm)!=boundary_edges(after,am):raise ValueError('Boundary or material seam topology changed')
    removed=np.setdiff1d(np.arange(len(before)),kept)
    new=after[origins<0]
    if not len(removed) or not len(new):raise ValueError('No replaced region to audit')
    result,_=audit(before[removed],new,bm[removed],am[origins<0])
    if not result['heightErrorInterpretationValid']:raise ValueError('Replaced region is not a single-valued height surface')
    if result['maximumVerticalErrorMeters']>tolerance_meters+1e-7:raise ValueError('Height error exceeds limit')
    for k in ['lostOldCoverageSquareMeters','addedCoverageSquareMeters','materialMismatchSquareMeters']:
        if result[k]>1e-5:raise ValueError(k+' exceeds roundoff tolerance')
    if result['ignoredBeforeVerticalFaces'] or result['ignoredAfterVerticalFaces']:raise ValueError('Vertical source faces were replaced')
    if result['afterSelfOverlap']['pairwiseOverlapSquareMeters']>1e-5:raise ValueError('New replacement faces overlap')
    # New geometry must also stay outside unchanged terrain and retained walls.
    unchanged=before[kept];normals=np.cross(unchanged[:,1]-unchanged[:,0],unchanged[:,2]-unchanged[:,0])
    old_shapes=shapely.polygons(unchanged[abs(normals[:,2])>1e-12,:,:2])
    new_shapes=shapely.polygons(new[:,:,:2]);tree=STRtree(old_shapes);overlap=0.
    for start in range(0,len(new_shapes),1024):
        a,b=tree.query(new_shapes[start:start+1024],predicate='intersects');a=a+start
        overlap+=float(shapely.area(shapely.intersection(new_shapes[a],old_shapes[b])).sum())
    if overlap*10000>1e-5:raise ValueError('Replacement overlaps unchanged terrain')
    # Independently compare normals over each positive-area original/new pair.
    old_surface=TerrainSurface(before[removed]);new_surface=TerrainSurface(new)
    shapes=shapely.polygons(old_surface.triangles[:,:,:2]);tree=STRtree(shapes);minimum_cos=1.
    for start in range(0,len(new_shapes),1024):
        a,b=tree.query(new_shapes[start:start+1024],predicate='intersects');a=a+start
        areas=shapely.area(shapely.intersection(new_shapes[a],shapes[b]));a,b=a[areas>1e-12],b[areas>1e-12]
        old_n=np.column_stack([-old_surface.planes[b,:2],np.ones(len(b))])
        new_n=np.column_stack([-new_surface.planes[a,:2],np.ones(len(a))])
        if len(a):minimum_cos=min(minimum_cos,float((np.sum(old_n*new_n,axis=1)/(np.linalg.norm(old_n,axis=1)*np.linalg.norm(new_n,axis=1))).min()))
    degrees=float(np.degrees(np.arccos(np.clip(minimum_cos,-1,1))))
    if degrees>normal_degrees+1e-7:raise ValueError('Normal change exceeds limit')
    return {'status':'native candidate checks passed; production sampler, compressed export and city QA pending',
            'originalTriangles':len(before),'candidateTriangles':len(after),'savedTriangles':len(before)-len(after),
            'unchangedOriginalFaces':len(kept),'replacedOriginalFaces':len(removed),'newFaces':len(new),
            'boundaryAndMaterialSeamsUnchanged':True,'allVerticesFromOriginal':True,
            'replacementUnchangedOverlapSquareMeters':overlap*10000,
            'maximumNormalAngleDegrees':degrees,'heightToleranceMeters':tolerance_meters,
            'normalToleranceDegrees':normal_degrees,'replacementAudit':result}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tolerance-meters',type=float,default=.05);p.add_argument('--normal-degrees',type=float,default=2.)
    args=p.parse_args();result=check(np.load(args.before),np.load(args.after),args.tolerance_meters,args.normal_degrees)
    result['inputs']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.before,args.after]}
    result['toolHashes']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(__file__).with_name('audit_terrain_reduction.py'),Path(__file__).with_name('prepare_building_support.py')]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
