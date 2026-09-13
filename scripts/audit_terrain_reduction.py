"""Independent exact vertical-error audit of a terrain triangulation change.

For each old/new triangle overlap, extrema of the difference of affine planes
occur at the clipped polygon vertices. No random point sample substitutes for
the full overlay. Vertical faces are explicitly outside this height-field audit.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.strtree import STRtree

from prepare_building_support import TerrainSurface


def overlap_audit(surface, shapes, tree):
    area=0.;maximum=0.;pairs_count=0
    for start in range(0,len(shapes),1024):
        pairs=tree.query(shapes[start:start+1024],predicate='intersects')
        left=pairs[0]+start;right=pairs[1]
        keep=left<right;left,right=left[keep],right[keep]
        intersections=shapely.intersection(shapes[left],shapes[right])
        areas=shapely.area(intersections);keep=areas>1e-12
        left,right,intersections,areas=left[keep],right[keep],intersections[keep],areas[keep]
        area+=float(areas.sum());pairs_count+=len(areas)
        points,indices=shapely.get_coordinates(intersections,return_index=True)
        if len(points):
            planes=surface.planes[left[indices]]-surface.planes[right[indices]]
            delta=abs(planes[:,0]*points[:,0]+planes[:,1]*points[:,1]+planes[:,2])
            maximum=max(maximum,float(delta.max()))
    return {'overlappingFacePairs':pairs_count,'pairwiseOverlapSquareMeters':area*10000,
            'maximumOverlappingHeightDifferenceMeters':maximum*100}


def audit(before, after, before_materials=None, after_materials=None):
    before=np.asarray(before,dtype=float);after=np.asarray(after,dtype=float)
    old=TerrainSurface(before);new=TerrainSurface(after)
    old_shapes=shapely.polygons(old.triangles[:,:,:2]);new_shapes=shapely.polygons(new.triangles[:,:,:2])
    tree=STRtree(old_shapes);errors=np.zeros(len(new_shapes))
    mismatch=0.;maximum=0.;witness=None
    # Material vectors refer to the original arrays; ignore the same vertical
    # or degenerate faces removed by TerrainSurface before comparing classes.
    def valid_materials(faces, materials):
        if materials is None:return None
        normals=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
        return np.asarray(materials)[abs(normals[:,2])>1e-12]
    old_m=valid_materials(before,before_materials);new_m=valid_materials(after,after_materials)
    for start in range(0,len(new_shapes),1024):
        end=min(start+1024,len(new_shapes));pairs=tree.query(new_shapes[start:end],predicate='intersects')
        ni=pairs[0]+start;oi=pairs[1]
        overlaps=shapely.intersection(new_shapes[ni],old_shapes[oi]);areas=shapely.area(overlaps)
        keep=areas>1e-12;ni,oi,overlaps,areas=ni[keep],oi[keep],overlaps[keep],areas[keep]
        if old_m is not None and new_m is not None:mismatch+=float(areas[old_m[oi]!=new_m[ni]].sum())
        points,indices=shapely.get_coordinates(overlaps,return_index=True)
        if not len(points):continue
        planes=new.planes[ni[indices]]-old.planes[oi[indices]]
        delta=abs(planes[:,0]*points[:,0]+planes[:,1]*points[:,1]+planes[:,2])
        np.maximum.at(errors,ni[indices],delta)
        worst=int(delta.argmax())
        if delta[worst]>maximum:
            maximum=float(delta[worst]);witness={'sceneXY':points[worst].tolist(),
                'beforeFace':int(oi[indices[worst]]),'afterFace':int(ni[indices[worst]])}
    old_overlap=overlap_audit(old,old_shapes,tree)
    new_overlap=overlap_audit(new,new_shapes,STRtree(new_shapes))
    # Summing pair areas can hide a gap beneath another duplicate triangle.
    # Compare the actual unions instead; include overlap diagnostics separately.
    old_outline=shapely.union_all(old_shapes);new_outline=shapely.union_all(new_shapes)
    ambiguous=any(r['maximumOverlappingHeightDifferenceMeters']>1e-5 for r in [old_overlap,new_overlap])
    bins={str(m):int((errors*100<=m).sum()) for m in [.001,.01,.05,.1,.25,.5,1]}
    return {'status':('ambiguous overlapping height surfaces; paired differences are not reduction error' if ambiguous else
                     'height-field comparison; vertical surfaces and city dependents require separate checks'),
            'heightErrorInterpretationValid':not ambiguous,
            'beforeSelfOverlap':old_overlap,'afterSelfOverlap':new_overlap,
            'beforeTriangles':len(before),'afterTriangles':len(after),'savedTriangles':len(before)-len(after),
            'heightFieldBeforeTriangles':len(old_shapes),'heightFieldAfterTriangles':len(new_shapes),
            'ignoredBeforeVerticalFaces':old.ignoredVerticalOrDegenerateFaces,
            'ignoredAfterVerticalFaces':new.ignoredVerticalOrDegenerateFaces,
            'maximumVerticalErrorMeters':None if ambiguous else maximum*100,
            'maximumPairedHeightDifferenceMeters':maximum*100,'maximumErrorWitness':witness,
            'verticalErrorMetersP50':None if ambiguous else float(np.percentile(errors*100,50)),
            'verticalErrorMetersP95':None if ambiguous else float(np.percentile(errors*100,95)),
            'afterFacesWithinErrorMeters':None if ambiguous else bins,
            'pairedHeightDifferenceMetersP95':float(np.percentile(errors*100,95)),
            'pairedFacesWithinDifferenceMeters':bins,
            'faceIndexConvention':'indices in nonvertical filtered triangle arrays',
            'lostOldCoverageSquareMeters':float(shapely.area(shapely.difference(old_outline,new_outline))*10000),
            'addedCoverageSquareMeters':float(shapely.area(shapely.difference(new_outline,old_outline))*10000),
            'materialMismatchSquareMeters':None if ambiguous else mismatch*10000,
            'pairedMaterialMismatchSquareMeters':mismatch*10000},errors


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    old=np.load(args.before);new=np.load(args.after)
    result,errors=audit(old['triangles'],new['triangles'],old['materials'],new['materials'])
    result['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.before,args.after]}
    result['scriptSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    np.save(args.output.with_suffix('.errors.npy'),errors)
    print(json.dumps(result,indent=2),flush=True)
