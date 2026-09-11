"""Audit remaining elevated-road scope, actual meshes, topology and clearance."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import DracoPy
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from viaduct import Path as RoadPath
from validate_ground_roads import clearance
from prepare_elevated_roads import remaining, occupied_half_width
from road_solids import load as resolved_roads


def load(name):return json.loads((ROOT/name).read_text())


def decode(filename):
    raw=(ROOT/'public/models'/filename).read_bytes();size=struct.unpack_from('<I',raw,12)[0]
    model=json.loads(raw[20:20+size]);binary=28+size;groups={'top':[],'paint':[],'terrain':[]};counts={}
    nodes=model['nodes'];parent=next(n for n in nodes if n.get('name')=='ElevatedRoads')
    bridges=next(n for n in nodes if n.get('name')=='Bridges')
    assert nodes.index(parent) in bridges['children'],'Elevated roads ignore the roads layer'
    asphalt=set()
    for node in nodes:
        name=node.get('name','')
        if 'mesh' not in node:continue
        if name.startswith('Bridges_'):raise AssertionError('Legacy floating bridge strips remain')
        if not name.startswith(('ElevatedRoads_','Terrain_')):continue
        for p in model['meshes'][node['mesh']]['primitives']:
            mat=model['materials'][p['material']]['name']
            if name.startswith('ElevatedRoads_'):
                counts[mat]=counts.get(mat,0)+model['accessors'][p['indices']]['count']//3
                if mat=='Qingxiang sage asphalt':asphalt.add(p['material'])
                if mat not in ('Qingxiang sage asphalt','Qingxiang lane markings'):continue
            v=model['bufferViews'][p['extensions']['KHR_draco_mesh_compression']['bufferView']]
            a=binary+v.get('byteOffset',0);mesh=DracoPy.decode(raw[a:a+v['byteLength']])
            key='terrain' if name.startswith('Terrain_') else 'paint' if mat=='Qingxiang lane markings' else 'top'
            groups[key].append(np.asarray(mesh.points[mesh.faces],dtype=float))
    q=next(n for n in nodes if n.get('name')=='Landmark_qingxiang-viaduct')
    assert asphalt & {p['material'] for p in model['meshes'][q['mesh']]['primitives']},'Missing shared Qingxiang asphalt'
    return {k:np.concatenate(v) for k,v in groups.items()},counts,parent['extras']['planHash']


def validate_elevated_roads():
    payload=gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes());plan=json.loads(payload);digest=hashlib.sha256(payload).hexdigest()
    heights=json.loads(gzip.decompress((ROOT/'data/elevated-roads-heights.json.gz').read_bytes()))
    assert heights['planHash']==digest
    geo=load('public/data/geography.json');assert {r['roadIndex'] for r in plan['routes']}==set(remaining(geo))
    for p,h in plan['inputHashes'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,f'Stale elevated source {p}'
    paths=[RoadPath(r['points']) for r in plan['routes']]
    for profile,levels in heights['profiles'].items():
        def level(i,s):
            j,t=paths[i].section(s);return levels[i][j]*(1-t)+levels[i][j+1]*t
        for join in plan['joins']:
            z=[levels[i][j] for i,j in join['vertices']]
            assert max(z)-min(z)<1e-5,'Split/merge height seam'
        for c in plan['crossings']:
            a,b=c['upper'],c['lower'];x,y=c['point']
            assert level(a,paths[a].nearest(x,y)[1])-level(b,paths[b].nearest(x,y)[1])>.12,'Interchange layers intersect'
        for r,p,z,floor in zip(plan['routes'],paths,levels,heights['terrainFloors'][profile]):
            for j,(a,b,s,t) in enumerate(zip(z,z[1:],p.lengths,p.lengths[1:])):
                allowance=max(.18*(t-s),min(.75*(t-s),abs(floor[j+1]-floor[j])))
                if any((s if end==0 else p.length-t)<1.5 for end in r['groundEnds']):allowance=.75*(t-s)
                assert abs(a-b)<=allowance+1e-6,'Elevated grade exceeds local terrain envelope'
    road_index=STRtree([LineString(r['points']).buffer(occupied_half_width(r)) for r in geo['roads']])
    water=unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    buildings=unary_union([Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings']])
    rail=load('data/railways-plan.json')
    railways=unary_union([LineString([rail['nodes'][n]['xy'] for n in r['nodes']]).buffer(.10) for r in rail['paths']])
    for region in [water,buildings,railways]:shapely.prepare(region)
    for r,p in zip(plan['routes'],paths):
        for s in r['piers']:
            disk=Point(p.at(s)[:2]).buffer(.055)
            assert all(int(j)==r['roadIndex'] for j in road_index.query(disk,predicate='intersects')),'Pier crosses another road'
            assert not water.intersects(disk) and not buildings.intersects(disk),'Pier crosses water/building'
            assert not railways.intersects(disk),'Pier crosses railway'
    for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
        groups,counts,h=decode(filename);assert h==digest
        resolved,metadata=resolved_roads(profile)
        source=resolved['elevated'][resolved['elevatedMaterials']==0]
        expected=len(source)
        assert abs(len(groups['top'])-expected)<expected*.02,'Elevated deck triangles lost'
        projected=groups['top'][:,:,[0,2]]
        actual_area=np.abs(np.cross(projected[:,1]-projected[:,0],projected[:,2]-projected[:,0])).sum()/2
        planned_area=shapely.area(shapely.polygons(source[:,:,:2])).sum()
        assert abs(actual_area-planned_area)<planned_area*.001,'Elevated deck area lost during compression'
        gap,collapsed,total=clearance(groups['top'],groups['terrain'],profile+' elevated deck/terrain')
        assert gap>0,'Elevated deck intersects terrain'
        # Other interchange decks are intentionally above/below these markings.
        # Compare the same deck level; layer separation is independently audited.
        gap,collapsed,total=clearance(groups['paint'],groups['top'],profile+' elevated paint/deck',max_vertical_separation=.02)
        assert gap>0,'Elevated markings buried in asphalt'
        assert collapsed/total<.02,'Elevated markings erased by compression'
        print(profile,'elevated roads:',counts,flush=True)
    print(f'PASS: {len(paths)} elevated ways, {len(plan["joins"])} junctions, {len(plan["crossings"])} crossings; pier avoidance, shared material and decoded clearance.',flush=True)


if __name__=='__main__':validate_elevated_roads()
