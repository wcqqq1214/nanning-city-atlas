"""Reduce native terrain while keeping every object/material boundary fixed."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely

from prepare_terrain_reduction import Reducer
from check_terrain_reduction import check


def protect_source_seams(reducer, tolerance_meters=1e-5):
    """Keep original faces at pre-existing, multi-height grid junctions.

    A coarse boundary edge may pass a finer patch's vertex at another height.
    Positive-area overlay checks do not detect that line/point discontinuity.
    Replacing either side would make the replacement sampler own an ambiguous
    location. Keep the entire incident source faces, not only their edge ends.
    """
    frozen=set();maximum=0.
    for start in range(0,len(reducer.shapes),1024):
        a,b=reducer.tree.query(reducer.shapes[start:start+1024],predicate='intersects');a=a+start
        keep=a<b;a,b=a[keep],b[keep]
        clipped=shapely.intersection(reducer.shapes[a],reducer.shapes[b])
        keep=shapely.area(clipped)<=1e-12;a,b,clipped=a[keep],b[keep],clipped[keep]
        points,indices=shapely.get_coordinates(clipped,return_index=True)
        if not len(points):continue
        planes=reducer.surface.planes[a[indices]]-reducer.surface.planes[b[indices]]
        delta=abs(planes[:,0]*points[:,0]+planes[:,1]*points[:,1]+planes[:,2])*100
        maximum=max(maximum,float(delta.max()))
        bad=np.unique(indices[delta>tolerance_meters])
        frozen.update(reducer.source_ids[np.concatenate([a[bad],b[bad]])].tolist())
    for i in frozen:reducer.protected.update(reducer.faces[i])
    return {'sourceFaces':sorted(frozen),'maximumSourceJunctionDifferenceMeters':maximum,
            'comparisonToleranceMeters':tolerance_meters}


def reduce(source, tolerance_meters, normal_degrees, progress=None):
    names = source['partitionNames'].tolist()
    owners = np.asarray(source['partitionIndices'])
    materials = np.asarray(source['materials'])
    if owners.shape != materials.shape or owners.ndim != 1 or not names or len(names) != len(set(names)):
        raise ValueError('Invalid source terrain partitions')
    if not np.issubdtype(materials.dtype, np.integer) or np.any(materials < 0):
        raise ValueError('Invalid source terrain materials')
    if not np.issubdtype(owners.dtype, np.integer) or np.any(owners < 0) or np.any(owners >= len(names)):
        raise ValueError('Unknown source terrain partition')
    # The reducer already freezes edges between material labels. A composite
    # label applies exactly the same boundary rule to object ownership too.
    labels = materials*len(names)+owners
    reducer = Reducer(source['triangles'], labels, tolerance_meters, normal_degrees)
    seams=protect_source_seams(reducer)
    faces, result_labels, origins, report = reducer.run(progress=progress)
    if not np.all(np.isin(seams['sourceFaces'],origins)):
        raise ValueError('Reduction replaced a discontinuous source junction')
    report['sourceDiscontinuousSeams']=seams
    candidate = {'triangles': faces, 'materials': result_labels//len(names),
                 'partitionIndices': result_labels % len(names),
                 'partitionNames': np.asarray(names), 'originFaceIndices': origins}
    # An independent audit treats partitions as material seams; ownership cannot
    # silently change even where adjacent partitions share the same material.
    audit = check({'triangles': source['triangles'], 'materials': labels},
                  {'triangles': faces, 'materials': result_labels, 'originFaceIndices': origins},
                  tolerance_meters, normal_degrees)
    audit['objectPartitionsUnchanged'] = True
    audit['discontinuousSourceSeamFacesRetained']=len(seams['sourceFaces'])
    return candidate, report, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tolerance-meters', type=float, default=.2)
    parser.add_argument('--normal-degrees', type=float, default=2)
    args = parser.parse_args()
    candidate, report, audit = reduce(np.load(args.input), args.tolerance_meters, args.normal_degrees,
        lambda n,a,t: print('Removed',n,'vertices;',a,'attempts;',round(t,1),'seconds',flush=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **candidate)
    audit['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.input,args.output]}
    args.output.with_suffix('.audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    report.update(independentAudit=audit,
                  input={'path': str(args.input.resolve()), 'sha256': hashlib.sha256(args.input.read_bytes()).hexdigest()},
                  outputSha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                  objectPartitions=candidate['partitionNames'].tolist())
    report['toolHashes']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                         [Path(__file__),Path(__file__).with_name('prepare_terrain_reduction.py'),
                          Path(__file__).with_name('check_terrain_reduction.py')]}
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['independentAudit','objectPartitions','toolHashes']},indent=2))


if __name__ == '__main__':
    main()
