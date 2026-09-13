"""Measure road clearance over every intersected native grading triangle."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

from prepare_building_support import TerrainSurface, geometry_points, terrain_faces
from validate_cultural_landmarks import glb


def decoded_pavement(path):
    source=Path(__file__).resolve().parents[1]/'blender/build_city.py'
    tree=ast.parse(source.read_text())
    definition=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets))
    labels={k.value:v.args[0].value for k,v in zip(definition.keys,definition.values)}
    names={labels[k] for k in ['viaduct_asphalt','road_secondary','road_local']}
    doc,decode=glb(path);faces=[]
    for node in doc['nodes']:
        if 'mesh' not in node or not node.get('name','').startswith('GroundRoads_'):continue
        if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked road transform')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            if doc['materials'][primitive['material']]['name'] not in names:continue
            mesh=decode(primitive);triangles=np.asarray(mesh.points[mesh.faces],dtype=float)[:,:,[0,2,1]];triangles[:,:,1]*=-1
            faces.append(triangles)
    if not faces:raise ValueError('No decoded ground pavement')
    return np.concatenate(faces)


def audit(ground, roads, bounds):
    region=box(*bounds)
    def local(faces):
        xy=faces[:,:,:2];w,s,e,n=bounds
        mask=(xy[:,:,0].max(1)>=w)&(xy[:,:,0].min(1)<=e)&(xy[:,:,1].max(1)>=s)&(xy[:,:,1].min(1)<=n)
        return TerrainSurface(faces[mask])
    terrain=local(ground);paving=local(roads)
    shapes=[Polygon(t[:,:2]) for t in terrain.triangles];tree=STRtree(shapes)
    minimum=float('inf');witness=None;intersections=0;road_faces=0
    for face,plane in zip(paving.triangles,paving.planes):
        shape=Polygon(face[:,:2]).intersection(region)
        if shape.area<=1e-12:continue
        road_faces+=1
        for i in tree.query(shape,predicate='intersects'):
            clipped=shape.intersection(shapes[i])
            if clipped.area<=1e-12:continue
            points=np.asarray(geometry_points(clipped));delta=plane-terrain.planes[i]
            gaps=np.column_stack((points,np.ones(len(points))))@delta
            index=int(gaps.argmin());gap=float(gaps[index])*100
            if gap<minimum:minimum=gap;witness=points[index].tolist()
            intersections+=1
    if not intersections:raise ValueError('No road/terrain intersections in grading bounds')
    return {'roadFaces':road_faces,'terrainIntersections':intersections,
            'minimumPavementClearanceMeters':minimum,'witnessSceneXY':witness,
            'maximumPenetrationMeters':max(0.,-minimum),'penetrationLimitMeters':.005,
            'passed':minimum>=-.005}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['native','roads','plan','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--context',type=Path,help='Also check actual compressed terrain and ground pavement')
    args=parser.parse_args();plan=json.loads(args.plan.read_text())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=json.loads((args.native/'report.json').read_text())
    if report['siteGradingDisabledForComparison'] or report['planHash']!=digest(args.plan):raise ValueError('Wrong graded native capture')
    result={'status':'geometry-only audit of the supplied road snapshot; no final city acceptance',
            'profiles':{},'inputs':{str(args.plan):digest(args.plan),str(args.native/'report.json'):digest(args.native/'report.json')},
            'toolSha256':digest(Path(__file__))}
    for profile in ['detail','smooth']:
        native=args.native/(profile+'.npz');roads=args.roads/('road-solids-'+profile+'.npz');metadata=roads.with_suffix('.json')
        meta=json.loads(metadata.read_text())
        if digest(native)!=report['profiles'][profile]['sha256'] or digest(roads)!=meta['sha256']:raise ValueError('Changed capture')
        if meta['inputHashes'].get('data/block-grading-plan.json')!=digest(args.plan):raise ValueError('Roads use different grading inputs')
        result['profiles'][profile]={site['id']:audit(np.load(native)['triangles'],np.load(roads)['ground'],site['bounds']) for site in plan['sites']}
        result['inputs'].update({str(p):digest(p) for p in [native,roads,metadata]})
    result['passed']=all(r['passed'] for profile in result['profiles'].values() for r in profile.values())
    if args.context:
        manifest=args.context/'sources.json';sources=json.loads(manifest.read_text())
        if not sources['includesGround'] or sources['inputHashes'].get('data/block-grading-plan.json')!=digest(args.plan):
            raise ValueError('Context does not contain the current graded roads')
        result['inputs'][str(manifest)]=digest(manifest);result['decodedProfiles']={}
        for profile in ['detail','smooth']:
            path=args.context/(profile+'.glb');ground=terrain_faces(path);paving=decoded_pavement(path)
            result['decodedProfiles'][profile]={site['id']:audit(ground,paving,site['bounds']) for site in plan['sites']}
            result['inputs'][str(path)]=digest(path)
        result['passed'] &= all(r['passed'] for profile in result['decodedProfiles'].values() for r in profile.values())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
