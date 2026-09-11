"""Retain remaining OSM elevated ways, topology, layers and reusable deck meshes."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import DracoPy
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from viaduct import Path as RoadPath
from zhuxi_interchange import lane_count, RAMP_WAYS
from prepare_ground_roads import triangulate


def load(path):return json.loads((ROOT/path).read_text())
def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def half_width(road, osm_id=None):
    if osm_id in RAMP_WAYS:return .0325
    if road['class'].endswith('_link'):return .0175
    return .065 if road['class'] in ('motorway','trunk','primary') else .05 if road['class']=='secondary' else .04


def occupied_half_width(road):
    if road['bridge']:return half_width(road)+.012
    return (.08 if road['class'] in ('motorway','trunk','primary') else .0525 if road['class']=='secondary' else .035 if road['class']=='tertiary' else .025)+.012


def remaining(geo):
    excluded=set(load('data/minzu-plan.json')['replacedRoads'])|set(map(int,load('data/viaduct-plan.json')['roadOverrides']))
    excluded|={i for b in load('data/bridges-plan.json')['bridges'] for i in b['roadIndices']}
    return [i for i,r in enumerate(geo['roads']) if r['bridge'] and i not in excluded and r['name']!='南宁大桥']


def orient_crossings(routes,crossings,geo):
    dedicated=set(load('data/minzu-plan.json')['replacedRoads'])|set(map(int,load('data/viaduct-plan.json')['roadOverrides']))
    dedicated|={i for i,r in enumerate(geo['roads']) if r['bridge'] and i not in {r['roadIndex'] for r in routes}}
    fixed={tuple(p) for i in dedicated for p in geo['roads'][i]['points']}
    def priority(i):
        r=routes[i];anchored=any(tuple(round(v,3) for v in r['points'][j]) in fixed for j in [0,-1])
        return (not anchored,r['class'] in ('motorway','trunk'),-i)
    for c in crossings:
        if c['inferred'] and priority(c['upper'])<priority(c['lower']):c['upper'],c['lower']=c['lower'],c['upper']


def capture_source(geo,indices):
    raw=load('work/geodata/osm.json');cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy))
    ways=[e for e in raw['elements'] if e.get('tags',{}).get('highway') and e.get('geometry')]
    classes={r['class'] for r in geo['roads']}
    ground_nodes={n for e in ways if e['tags']['highway'] in classes and e['tags'].get('bridge','no')=='no' for n in e['nodes']}
    lines=[LineString([((p['lon']-cx)*kx,(p['lat']-cy)*1113.2) for p in e['geometry']]) for e in ways]
    index=STRtree(lines);output=[];exact=defaultdict(list)
    for j,(e,line) in enumerate(zip(ways,lines)):
        exact[(*[round(v,3) for v in line.coords[0]],*[round(v,3) for v in line.coords[-1]],e['tags']['highway'])].append(j)
    for i in indices:
        road=geo['roads'][i];line=LineString(road['points'])
        choices=[int(j) for j in index.query(line.buffer(.003)) if ways[j]['tags']['highway']==road['class']
                 and ways[j]['tags'].get('bridge','no')!='no' and ways[j]['tags'].get('name','')==road['name']]
        matched=exact.get((*road['points'][0],*road['points'][-1],road['class']),[])
        j=min(matched or choices,key=lambda j:line.hausdorff_distance(lines[j].intersection(box(*geo['bounds']))))
        assert matched or line.difference(lines[j].buffer(.08)).length<.001,f'Cannot match clipped source road {i}'
        ground_ends=[end for end,k in [(0,0),(1,-1)] if ways[j]['nodes'][k] in ground_nodes and math.dist(lines[j].coords[k],road['points'][k])<.002]
        output.append({'roadIndex':i,'osmId':ways[j]['id'],'tags':ways[j]['tags'],'nodes':ways[j]['nodes'],'geometry':ways[j]['geometry'],'groundEnds':ground_ends})
    source={'osmTimestamp':geo['osmTimestamp'],'attribution':'© OpenStreetMap contributors / ODbL 1.0','ways':output}
    (ROOT/'data/elevated-roads-source.json').write_text(json.dumps(source,ensure_ascii=False,separators=(',',':'))+'\n')


def decoded_supports(filename):
    raw=(ROOT/filename).read_bytes();size=struct.unpack_from('<I',raw,12)[0]
    model=json.loads(raw[20:20+size]);binary=28+size;terrain=[];roads=[]
    for node in model['nodes']:
        name=node.get('name','')
        if 'mesh' not in node:continue
        is_terrain=name.startswith('Terrain_')
        is_road=name.startswith(('GroundRoads_','MinzuAvenue_','Landmark_','Railways_'))
        if not (is_terrain or is_road):continue
        for p in model['meshes'][node['mesh']]['primitives']:
            mat=model['materials'][p['material']]['name']
            if not is_terrain and mat not in ('Qingxiang sage asphalt','Secondary sage streets','Simple neighbourhood paving','River bridge asphalt','Railway grey ballast'):continue
            view=model['bufferViews'][p['extensions']['KHR_draco_mesh_compression']['bufferView']]
            a=binary+view.get('byteOffset',0);mesh=DracoPy.decode(raw[a:a+view['byteLength']])
            faces=np.asarray(mesh.points[mesh.faces],dtype=float)[:,:,[0,2,1]];faces[:,:,1]*=-1
            (terrain if is_terrain else roads).append(faces)
    def spatial(parts):
        faces=np.concatenate(parts);normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]);ok=np.abs(normal[:,2])>1e-10
        faces=faces[ok];normal=normal[ok]
        coefficients=np.column_stack((-normal[:,0]/normal[:,2],-normal[:,1]/normal[:,2],np.einsum('ij,ij->i',normal,faces[:,0])/normal[:,2]))
        return STRtree(shapely.polygons(faces[:,:,:2])),coefficients
    return spatial(terrain),spatial(roads)


def sample_supports(points,supports):
    index,planes=supports;result=np.full(len(points),-1000.)
    for start in range(0,len(points),5000):
        xy=np.asarray(points[start:start+5000]);pairs=index.query(shapely.points(xy),predicate='intersects')
        if not pairs.shape[1]:continue
        p=planes[pairs[1]];q=xy[pairs[0]];heights=p[:,0]*q[:,0]+p[:,1]*q[:,1]+p[:,2]
        np.maximum.at(result,pairs[0]+start,heights)
    return result


def capture_floors(routes):
    points=[];spans=[]
    for r in routes:
        path=RoadPath(r['points']);start=len(points)
        for s in path.lengths:points.extend([path.at(s,o)[:2] for o in [-r['width']-.015,0,r['width']+.015]])
        spans.append((start,len(points)));r['terrainFloors']={};r['roadFloors']={}
    for profile,filename in [('detail','work/elevated-roads/before.glb'),('smooth','work/elevated-roads/before-mobile.glb')]:
        floors,paving=decoded_supports(filename)
        terrain=sample_supports(points,floors);road=sample_supports(points,paving)
        for r,(a,b) in zip(routes,spans):
            r['terrainFloors'][profile]=[round(float(v),6) for v in terrain[a:b].reshape(-1,3).max(axis=1)]
            r['roadFloors'][profile]=[round(float(v),6) for v in road[a:b].reshape(-1,3).max(axis=1)]
        print('Captured',profile,'terrain and paving',flush=True)
    for r in routes:
        r['terrainFloor']=list(map(max,zip(*r['terrainFloors'].values())))
        r['roadFloor']=list(map(max,zip(*r['roadFloors'].values())))


def bind_paint(routes):
    """Clip each marking to a real deck face and retain barycentric support."""
    for r in routes:
        shapes=[Polygon([v[:2] for v in f]) for f in r['faces']]
        index=STRtree(shapes)
        for profile,marks in r['paint'].items():
            bound=[]
            for mark in marks:
                shape=Polygon([v[:2] for v in mark])
                for j in index.query(shape,predicate='intersects'):
                    j=int(j);a,b,c=[v[:2] for v in r['faces'][j]]
                    denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                    if abs(denominator)<1e-12:continue
                    for tri in triangulate(shape.intersection(shapes[j])):
                        points=[]
                        for x,y in tri:
                            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
                            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
                            points.append([x,y,u,v])
                        bound.append({'support':j,'points':points})
            r['paint'][profile]=bound


def prepare(capture=False):
    geo=load('public/data/geography.json');indices=remaining(geo)
    if capture or not (ROOT/'data/elevated-roads-source.json').exists():capture_source(geo,indices)
    source={r['roadIndex']:r for r in load('data/elevated-roads-source.json')['ways']}
    assert set(source)==set(indices),'Recapture after changing the set of detailed bridges'
    routes=[];nodes=defaultdict(list);ground_nodes={tuple(p) for r in geo['roads'] if not r['bridge'] for p in r['points']}
    cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy))
    for i in indices:
        road=geo['roads'][i]
        raw_points=[(round((p['lon']-cx)*kx,3),round((p['lat']-cy)*1113.2,3)) for p in source[i]['geometry']]
        raw_points=[p for j,p in enumerate(raw_points) if j==0 or p!=raw_points[j-1]]
        line=LineString(raw_points).intersection(box(*geo['bounds']))
        if line.geom_type!='LineString':line=max((p for p in shapely.get_parts(line) if p.geom_type=='LineString'),key=lambda p:p.length)
        original=list(line.coords);original[0]=road['points'][0];original[-1]=road['points'][-1]
        line=LineString(original);path=RoadPath(original)
        stations=sorted(set(round(s,7) for s in [*path.lengths,*[line.length*k/math.ceil(line.length/.20) for k in range(math.ceil(line.length/.20)+1)]]))
        w=half_width(road,source[i]['osmId']);points=[path.at(s)[:2] for s in stations]
        points[0]=road['points'][0];points[-1]=road['points'][-1]
        points=[p for j,p in enumerate(points) if j==0 or math.dist(p,points[j-1])>1e-6]
        routes.append({'roadIndex':i,'osmId':source[i]['osmId'],'name':road['name'],'class':road['class'],
                       'layer':int(source[i]['tags'].get('layer','1')),'width':w,'points':points,'stations':stations})
        for j,p in enumerate(points):nodes[tuple(round(v,6) for v in p)].append((len(routes)-1,j))
    for r in routes:
        lanes=lane_count(r['osmId'])
        if lanes is not None:r['lanes']=lanes
    paths=[RoadPath(r['points']) for r in routes]
    footprints=[LineString(r['points']).buffer(r['width'],cap_style=2,join_style=2) for r in routes]
    spatial=STRtree(footprints);line_index=STRtree([LineString(r['points']) for r in routes])
    joins=[];neighbours=defaultdict(set);joint_points=defaultdict(list)
    for xy,entries in nodes.items():
        if len(entries)>1:
            joins.append({'point':xy,'vertices':entries})
            for a,_ in entries:
                for b,_ in entries:
                    if a!=b:
                        neighbours[a].add(b);joint_points[a,b].append(Point(xy))
    # Cartographic carriageway widths can touch even when OSM keeps their nodes
    # separate. Union same-level parallel decks instead of stacking their edges.
    paired=0
    for a,footprint in enumerate(footprints):
        for b in spatial.query(footprint,predicate='intersects'):
            b=int(b)
            if b<=a or b in neighbours[a] or routes[a]['layer']!=routes[b]['layer']:continue
            if routes[a]['class'].endswith('_link') or routes[b]['class'].endswith('_link'):continue
            ca,cb=LineString(paths[a].points),LineString(paths[b].points)
            if ca.crosses(cb):continue
            overlap=footprint.intersection(footprints[b])
            if overlap.area<1e-7:continue
            for part in shapely.get_parts(overlap):
                if part.area<1e-8:continue
                q=part.representative_point();joint_points[a,b].append(q);joint_points[b,a].append(q)
            neighbours[a].add(b);neighbours[b].add(a);paired+=1
    junction_area={}
    for (a,b),points in joint_points.items():
        parts=list(shapely.get_parts(footprints[a].intersection(footprints[b])))
        junction_area[a,b]=unary_union([p for p in parts if any(p.distance(q)<.025 for q in points)]).buffer(.01)
    crossings=[]
    for a,path in enumerate(paths):
        for b in line_index.query(LineString(path.points),predicate='intersects'):
            b=int(b)
            if b<=a:continue
            cut=LineString(path.points).intersection(LineString(paths[b].points))
            for p in shapely.get_parts(cut):
                if p.geom_type!='Point':continue
                if b in neighbours[a] and junction_area[a,b].intersects(p):continue
                sa=path.nearest(p.x,p.y)[1];sb=paths[b].nearest(p.x,p.y)[1]
                # Endpoint-only contact is a junction even when importer rounding
                # has retained that vertex inside the other source way.
                if min(sa,path.length-sa,sb,paths[b].length-sb)<.015:continue
                upper,lower=(a,b) if (routes[a]['layer'],routes[a]['class'] in ('motorway','trunk'),-a)>(routes[b]['layer'],routes[b]['class'] in ('motorway','trunk'),-b) else (b,a)
                crossings.append({'upper':upper,'lower':lower,'point':[p.x,p.y],'inferred':routes[a]['layer']==routes[b]['layer']})
    orient_crossings(routes,crossings,geo)
    buildings=unary_union([Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings']])
    solids=unary_union([Polygon(p[0],p[1:]) for p in load('data/ground-roads-context.json')['obstacles']])
    obstacle=buildings.union(solids).buffer(.005)
    obstacle_parts=list(shapely.get_parts(obstacle));obstacle_index=STRtree(obstacle_parts)
    all_roads=[LineString(r['points']).buffer(occupied_half_width(r)) for r in geo['roads']]
    all_index=STRtree(all_roads);water=unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    rail=load('data/railways-plan.json')
    rail_footprints=unary_union([LineString([rail['nodes'][n]['xy'] for n in r['nodes']]).buffer(.10) for r in rail['paths']])
    for region in [obstacle,water,rail_footprints]:shapely.prepare(region)
    for a,(r,path) in enumerate(zip(routes,paths)):
        local_obstacle=unary_union([obstacle_parts[int(j)] for j in obstacle_index.query(footprints[a].buffer(.06),predicate='intersects')])
        clipped=footprints[a].difference(local_obstacle)
        for b in neighbours[a]:
            if b<a:clipped=clipped.difference(footprints[b].intersection(junction_area[a,b]))
        r['faces']=[];r['edges']=[];r['piers']=[];r['mergeStations']=[];r['paint']={}
        paint_clearance=clipped.difference(unary_union([footprints[b].buffer(.02) for b in neighbours[a]]))
        for b in neighbours[a]:
            overlap=footprints[a].intersection(footprints[b]).intersection(junction_area[a,b]).buffer(.04)
            selected=[j for j,s in enumerate(path.lengths) if overlap.intersects(Point(path.at(s)[:2]))]
            if selected:r['mergeStations'].append([b,selected])
        for s,t in zip(path.lengths,path.lengths[1:]):
            q=Polygon([path.at(s,-r['width'])[:2],path.at(t,-r['width'])[:2],path.at(t,r['width'])[:2],path.at(s,r['width'])[:2]])
            if not q.is_valid:q=shapely.make_valid(q)
            for tri in triangulate(q.intersection(clipped)):
                r['faces'].append([[round(x,6),round(y,6),round(path.nearest(x,y)[1],7)] for x,y in tri])
            for side in (-1,1):
                edge=LineString([path.at(s,side*r['width'])[:2],path.at(t,side*r['width'])[:2]])
                if any(edge.intersects(footprints[b].intersection(junction_area[a,b]).buffer(.01)) for b in neighbours[a]):continue
                if edge.intersects(local_obstacle):continue
                r['edges'].append([s,t,side])
        for profile,spacing in [('detail',.35),('smooth',.60)]:
            faces=[]
            if profile=='detail' or not r['class'].endswith('_link'):
                for k in range(1,math.floor(path.length/spacing)):
                    start_at=k*spacing;end_at=min(path.length-.05,start_at+.12)
                    if any(abs(path.lengths[j]-start_at)<.2 for _,stations in r['mergeStations'] for j in stations):continue
                    if end_at<=start_at:continue
                    cuts=[start_at,*[s for s in path.lengths if start_at<s<end_at],end_at]
                    lanes=r.get('lanes',2)
                    for offset in [-r['width']+2*r['width']*lane/lanes for lane in range(1,lanes)]:
                        for s,t in zip(cuts,cuts[1:]):
                            paint=Polygon([path.at(s,offset-.0015)[:2],path.at(t,offset-.0015)[:2],path.at(t,offset+.0015)[:2],path.at(s,offset+.0015)[:2]])
                            if not paint.is_valid:paint=shapely.make_valid(paint)
                            for tri in triangulate(paint.intersection(paint_clearance)):
                                faces.append([[round(x,6),round(y,6),round(path.nearest(x,y)[1],7)] for x,y in tri])
            r['paint'][profile]=faces
        for k in range(1,math.ceil(path.length/.40)):
            s=k*.40
            if s>path.length-.18:continue
            x,y=path.at(s)[:2];foot=Point(x,y).buffer(.055)
            others=[int(j) for j in all_index.query(foot,predicate='intersects') if int(j)!=r['roadIndex']]
            if others or obstacle.intersects(foot) or water.intersects(foot) or rail_footprints.intersects(foot):continue
            r['piers'].append(s)
        r['groundEnds']=sorted(set(source[r['roadIndex']].get('groundEnds',[]))|{end for end,p in [(0,path.points[0]),(1,path.points[-1])] if tuple(round(v,3) for v in p) in ground_nodes})
        if a%100==0:print('Deck clipping',a,'/',len(routes),flush=True)
    print(f'Prepared {len(routes)} elevated ways, {len(joins)} joints, {len(crossings)} separated crossings; sampling retained terrain.',flush=True)
    bind_paint(routes)
    capture_floors(routes)
    inputs=['public/data/geography.json','public/data/terrain.json','data/elevated-roads-source.json','data/bridges-plan.json','data/viaduct-plan.json','data/minzu-plan.json']
    plan={'sceneCenter':geo['center'],'inputHashes':{p:digest(p) for p in inputs},'contextModels':{p:digest(p) for p in ['work/elevated-roads/before.glb','work/elevated-roads/before-mobile.glb']},
          'routes':routes,'joins':joins,'crossings':crossings,'stats':{'ways':len(routes),'lengthKm':round(sum(p.length for p in paths)/10,3),'piers':sum(len(r['piers']) for r in routes),'crossings':len(crossings),'pairedDeckMerges':paired}}
    (ROOT/'data/elevated-roads-plan.json.gz').write_bytes(gzip.compress((json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n').encode(),mtime=0))
    print(plan['stats'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',action='store_true');prepare(p.parse_args().capture)
