"""Audit actual access/soil exports and their contact with current city roads."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union

from check_reduced_terrain_exports import match_faces
from check_site_road_support import decoded_pavement, audit as road_clearance
from prepare_block_grading import LocalSurface
from prepare_building_support import TerrainSurface
from prepare_site_access import soil_penetration
from validate_cultural_landmarks import glb
from decoded_surface import face_arrays


def decode(path,labels,allow_context=False):
    doc,load=glb(path);result={key:{'triangles':[],'materials':[],'cornerNormals':[]} for key in ['terrain','roads']}
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked access transform')
        name=node.get('name','');kind='terrain' if name.startswith('Terrain_grading_access_') else 'roads' if name.startswith('GroundRoads_access_') else None
        if kind is None:
            if allow_context:continue
            raise ValueError('Unexpected access mesh')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            data=load(primitive);faces,normal_values=face_arrays(data)
            result[kind]['triangles'].extend(faces);result[kind]['cornerNormals'].extend(normal_values)
            result[kind]['materials'].extend([labels.index(doc['materials'][primitive['material']]['name'])]*len(data.faces))
    return {kind:{k:np.asarray(v) for k,v in data.items()} for kind,data in result.items()}


def coverage(faces):
    normals=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    if np.any(normals[:,2]<=0):raise ValueError('Collapsed or reversed projected access face')
    shapes=[Polygon(t[:,:2]) for t in faces];union=unary_union(shapes)
    overlap=(sum(p.area for p in shapes)-union.area)*10000
    if abs(overlap)>1e-5:raise ValueError(f'Overlapping exported faces: {overlap} m2')
    return union,overlap


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['directory','candidate','context','plan','geography','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--integrated-directory',type=Path,help='Actual full-terrain runtime export to check against the same native access meshes')
    args=parser.parse_args();digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=json.loads((args.directory/'report.json').read_text());candidate=json.loads(args.candidate.read_text())
    plan=json.loads(args.plan.read_text());geo=json.loads(args.geography.read_text())
    if manifest['candidateSha256']!=digest(args.candidate):raise ValueError('Wrong access candidate')
    context_sources=json.loads((args.context/'sources.json').read_text())['inputHashes']
    for name,path in [('public/data/geography.json',args.geography),('data/block-grading-plan.json',args.plan)]:
        if context_sources.get(name)!=digest(path):raise ValueError('Road context uses different geography or grading')
    integrated=None
    if args.integrated_directory:
        integrated=json.loads((args.integrated_directory/'report.json').read_text())
        if integrated['candidateSha256']!=digest(args.candidate):raise ValueError('Integrated terrain uses a different candidate')
    keys=manifest['materialKeys'];paving_key=keys.index('viaduct_asphalt');wall_key=keys.index('viaduct_concrete')
    report={'status':'isolated access exports checked; full terrain replacement, runtime sampling and site visual acceptance pending','profiles':{},'inputs':{}}
    for profile in ['detail','smooth']:
        for name,record in manifest['profiles'][profile]['files'].items():
            if digest(args.directory/name)!=record['sha256']:raise ValueError('Access export changed')
        actual=decode(args.directory/(profile+'.glb'),manifest['materialLabels']);checks={}
        for kind,data in actual.items():
            checks[kind]=match_faces(dict(np.load(args.directory/f'{profile}-{kind}.npz')),data,position_meters=.0002,normal_degrees=.5)
        integrated_checks=None
        if integrated:
            path=args.integrated_directory/(profile+'.glb')
            if digest(path)!=integrated['profiles'][profile]['export']['sha256']:raise ValueError('Integrated export changed')
            decoded=decode(path,manifest['materialLabels'],allow_context=True)
            integrated_checks={kind:match_faces(dict(np.load(args.directory/f'{profile}-{kind}.npz')),data,position_meters=.0002,normal_degrees=.5) for kind,data in decoded.items()}
            doc,_=glb(path)
            old={'Terrain_grading_'+s['id'].replace('-','_')+'_0_0' for s in plan['sites']}
            if old & {node.get('name') for node in doc['nodes']}:raise ValueError('Integrated export retains old grading below access')
        terrain=actual['terrain']['triangles'];paving=actual['roads']['triangles'][actual['roads']['materials']==paving_key]
        walls=actual['roads']['triangles'][actual['roads']['materials']==wall_key]
        soil_cover,soil_overlap=coverage(terrain);road_cover,road_overlap=coverage(paving)
        tree=cKDTree(paving.reshape(-1,3));surface=TerrainSurface(terrain);existing=decoded_pavement(args.context/(profile+'.glb'))
        expected=unary_union([Polygon(np.asarray(t)[:,:2]) for site in plan['sites'] for t in candidate['sites'][site['id']][profile]['terrainTriangles']])
        if expected.symmetric_difference(soil_cover).area>1e-9:raise ValueError('Soil domain changed in export')
        sites=[]
        for site in plan['sites']:
            source=candidate['sites'][site['id']][profile]
            mouth=np.asarray(source['topPoints'][-source['columns']:]);distance,indices=tree.query(mouth)
            if distance.max()*100>.0002:raise ValueError('Cannot locate decoded access mouth')
            mouth=paving.reshape(-1,3)[indices];road=LocalSurface(existing,site['bounds'])
            road_domain=unary_union(road.shapes);height_error=0.;gap=0.
            for a,b in zip(mouth,mouth[1:]):
                for t in np.linspace(0,1,11):
                    p=a*(1-t)+b*t;height_error=max(height_error,abs(p[2]-road(*p[:2]))*100)
                    gap=max(gap,Point(p[:2]).distance(road_domain)*100)
            if height_error>.005 or gap>.005:raise ValueError(f'Access mouth mismatch: height {height_error} m, gap {gap} m')
            contact=soil_penetration({'topPoints':paving.reshape(-1,3).tolist(),'triangles':np.arange(len(paving)*3).reshape(-1,3).tolist()},terrain)
            if contact['maximumOldTerrainAbovePavementMeters']>.005:raise ValueError('Decoded soil penetrates access pavement')
            clearance=road_clearance(terrain,existing,site['bounds'])
            if not clearance['passed']:raise ValueError('New soil penetrates retained city pavement')
            buildings=[]
            for building in geo['buildings']:
                if building['id'] not in site['buildingIds']:continue
                support=surface.bounds(Polygon(building['rings'][0],building['rings'][1:]),.005)
                if support['status']!='covered' or (support['maximumSceneZ']-support['minimumSceneZ'])*100>.001:raise ValueError('Warehouse support changed')
                buildings.append({'id':building['id'],'support':support})
            sites.append({'id':site['id'],'mouthHeightErrorMeters':height_error,'mouthGapMeters':gap,'accessSoilContact':contact,'existingRoadClearance':clearance,'buildings':buildings})
        # Boundary wall normals must point away from the paved footprint.
        outward=0
        for tri in walls:
            n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);length=np.linalg.norm(n[:2])
            if length<=1e-15:raise ValueError('Horizontal boundary wall')
            center=tri[:,:2].mean(0);offset=n[:2]/length*.0001
            if road_cover.contains(Point(center+offset)):raise ValueError('Inward-facing access side wall')
            outward+=1
        report['profiles'][profile]={'geometry':checks,'soilOverlapSquareMeters':soil_overlap,'pavingOverlapSquareMeters':road_overlap,'outwardWallFaces':outward,'sites':sites,'bytes':(args.directory/(profile+'.glb')).stat().st_size}
        if integrated_checks is not None:report['profiles'][profile]['integratedGeometry']=integrated_checks
    files=[args.candidate,args.plan,args.geography,args.directory/'report.json',*[args.directory/(p+'.glb') for p in ['detail','smooth']],*[args.context/(p+'.glb') for p in ['detail','smooth']]]
    files.append(args.context/'sources.json')
    if integrated:
        files.extend([args.integrated_directory/'report.json',*[args.integrated_directory/(p+'.glb') for p in ['detail','smooth']]])
        report['status']='isolated and actual terrain-integrated access exports checked; full city and site visual acceptance pending'
    report['inputs']={str(p):digest(p) for p in files};report['toolSha256']=digest(Path(__file__))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
