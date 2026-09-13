"""Independent scope, coverage and pad checks for native site integration."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union

from prepare_block_grading import LocalSurface
from prepare_building_support import TerrainSurface


def exterior_signatures(mesh,inside):
    rows=np.column_stack((mesh['triangles'][~inside].reshape(-1,9),mesh['materials'][~inside],mesh['cornerNormals'][~inside].reshape(-1,9)))
    return np.sort(np.ascontiguousarray(rows).view(np.dtype((np.void,rows.dtype.itemsize*rows.shape[1]))).ravel())


def audit(before,after,plan,geography,before_report,after_report):
    result={};patches=[box(*p['bounds']) for p in plan['sites']];region=unary_union(patches)
    masks=[]
    for mesh in [before,after]:
        centers=mesh['triangles'][:,:,:2].mean(axis=1)
        mask=np.zeros(len(centers),dtype=bool)
        for w,s,e,n in [p['bounds'] for p in plan['sites']]:
            mask|=(centers[:,0]>=w-1e-7)&(centers[:,0]<=e+1e-7)&(centers[:,1]>=s-1e-7)&(centers[:,1]<=n+1e-7)
        masks.append(mask)
    old,new=[exterior_signatures(mesh,mask) for mesh,mask in zip([before,after],masks)]
    assert np.array_equal(old,new),'Unreplaced geometry, materials or normals changed'
    assert before_report['rngState']==after_report['rngState'],'Grading changed later palette choices'
    water=unary_union([Polygon(r[0],r[1:]) for r in geography['water']])
    faces=after['triangles'][masks[1]];polygons=[Polygon(t[:,:2]) for t in faces]
    cover=unary_union(polygons);expected=region.difference(water)
    # A 5 mm XY tolerance accommodates native float32 vertices at city scale.
    tolerance=.005/100
    assert expected.difference(cover.buffer(tolerance)).area<1e-9,'Missing replacement coverage'
    assert cover.difference(expected.buffer(tolerance)).area<1e-9,'Replacement exceeds source boundary'
    overlap=(sum(p.area for p in polygons)-cover.area)*10000
    assert overlap<.00001,('Overlapping native replacement faces',overlap)
    surface=TerrainSurface(faces);sites=[]
    for site in plan['sites']:
        pad=Polygon(site['pad'][0],site['pad'][1:]);support=surface.bounds(pad,.005)
        assert support['status']=='covered',site['id']
        relief=(support['maximumSceneZ']-support['minimumSceneZ'])*100
        assert relief<.001,(site['id'],relief)
        baseline=LocalSurface(before['triangles'],site['bounds'])
        edge=box(*site['bounds']).boundary
        points={tuple(p) for t in faces for p in t if Point(p[:2]).distance(edge)<=tolerance}
        differences=[abs(p[2]-baseline(*p[:2]))*100 for p in points]
        assert points and max(differences)<.005,site['id']
        sites.append({'id':site['id'],'padReliefMeters':relief,'padSupport':support,
                      'boundaryVertices':len(points),'maximumBoundaryHeightDifferenceMeters':max(differences)})
    result.update(outsideTriangles=len(old),outsideGeometryMaterialsNormalsIdentical=True,paletteRngPreserved=True,
                  originalPatchTriangles=int(masks[0].sum()),replacementTriangles=int(masks[1].sum()),
                  netTriangles=int(masks[1].sum()-masks[0].sum()),replacementOverlapSquareMeters=overlap,
                  nativeCoverageToleranceMeters=.005,sites=sites,
                  samplerPoints=after_report['samplerPoints'],maximumSamplerErrorMeters=after_report['maximumSamplerErrorMeters'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['before','after','plan','geography','output']:p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();plan=json.loads(args.plan.read_text());geo=json.loads(args.geography.read_text())
    before=json.loads((args.before/'report.json').read_text());after=json.loads((args.after/'report.json').read_text())
    assert before['siteGradingDisabledForComparison'] and not after['siteGradingDisabledForComparison']
    digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    assert before['planHash']==after['planHash']==digest(args.plan)
    results={}
    for profile in ['detail','smooth']:
        for path,report in [(args.before,before),(args.after,after)]:
            assert digest(path/(profile+'.npz'))==report['profiles'][profile]['sha256']
        results[profile]=audit(np.load(args.before/(profile+'.npz')),np.load(args.after/(profile+'.npz')),plan,geo,
                               before['profiles'][profile],after['profiles'][profile])
    report={'status':'native scope, single coverage, flat pad and sampler checks passed; final access and compressed city pending',
            'profiles':results,'inputs':{str(f):digest(f) for f in [args.plan,args.geography,args.before/'report.json',args.after/'report.json']},
            'toolSha256':digest(Path(__file__))}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
