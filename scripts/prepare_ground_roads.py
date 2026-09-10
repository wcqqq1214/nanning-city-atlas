"""Prepare disjoint, terrain-conforming ground streets; preserve elevated roads."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import DracoPy
import mapbox_earcut
import numpy as np
from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union, nearest_points
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from zhenning_landmark import terrain_patch

INPUTS = ['public/data/geography.json','public/data/terrain.json','data/landmarks.json',
          'data/nanhu-plan.json','data/minzu-plan.json','data/viaduct-plan.json',
          'blender/minzu_avenue.py','blender/viaduct.py']


def polygons(shape):
    if shape.geom_type == 'Polygon': yield shape
    elif hasattr(shape,'geoms'):
        for child in shape.geoms: yield from polygons(child)


def rings(shape):
    return [[[round(x,6),round(y,6)] for x,y in r.coords] for r in [shape.exterior,*shape.interiors]]


def triangulate(shape):
    for p in polygons(shape):
        if p.area < 1e-11: continue
        rs = [list(r.coords)[:-1] for r in [p.exterior,*p.interiors]]
        pts = np.asarray([v for r in rs for v in r], dtype=np.float64)
        ids = mapbox_earcut.triangulate_float64(pts,np.cumsum([len(r) for r in rs],dtype=np.uint32))
        for tri in ids.reshape(-1,3):
            vertices = [tuple(pts[i]) for i in tri]
            if Polygon(vertices).area > 1e-11: yield vertices


def load(name): return json.loads((ROOT/name).read_text())


def width(road):
    # Cartographic widths stay inside the previous exclusion corridors. Small
    # streets get an unmarked 5 m surface instead of a 9.5 m generic strip.
    return .16 if road['class'] in ['primary','trunk','motorway'] else .105 if road['class']=='secondary' else .07 if road['class']=='tertiary' else .05


def capture_context(geo, minzu, viaduct):
    raw = (ROOT/'public/models/nanning-city.glb').read_bytes()
    size = struct.unpack_from('<I',raw,12)[0]; model = json.loads(raw[20:20+size]); binary = 28+size
    road_landmarks={'Landmark_'+p['id'] for p in load('data/landmarks.json') if p.get('layer')=='roads'}
    selected_ground = [LineString(r['points']).buffer(r['width']/2+.015,cap_style=2) for r in minzu['paths'] if not r['bridge']]
    selected_ground += [LineString(r['points']).buffer(.20,cap_style=2) for i,r in enumerate(geo['roads'])
                        if str(i) in viaduct['roadOverrides'] and not r['bridge']]
    ground_mask = unary_union(selected_ground)
    solid, road_faces, bridge_faces = [], [], []
    for node in model['nodes']:
        name = node.get('name','')
        if 'mesh' not in node: continue
        is_road = name.startswith('MinzuAvenue_') and not name.startswith('MinzuAvenue_Details') or name=='Landmark_qingxiang-viaduct'
        is_solid = name.startswith('Landmark_') and name not in road_landmarks and name not in ['Landmark_qingxiang-viaduct','Landmark_bridge','Landmark_nanhu']
        is_bridge=name.startswith('Bridges_')
        if not (is_road or is_solid or is_bridge): continue
        assert not any(k in node for k in ['matrix','translation','rotation','scale']), 'Capture requires world-space meshes'
        for p in model['meshes'][node['mesh']]['primitives']:
            if is_road and model['materials'][p['material']]['name'] != 'Qingxiang sage asphalt': continue
            ext = p['extensions']['KHR_draco_mesh_compression']; view = model['bufferViews'][ext['bufferView']]
            start = binary+view.get('byteOffset',0); mesh = DracoPy.decode(raw[start:start+view['byteLength']])
            for face in mesh.points[mesh.faces]:
                verts = [(float(x),float(-z),float(y)) for x,y,z in face]
                shape = Polygon([p[:2] for p in verts])
                if shape.area < 1e-10: continue
                if is_solid: solid.append(shape)
                elif is_bridge: bridge_faces.append(verts)
                elif ground_mask.covers(shape.representative_point()): road_faces.append(verts)
    # Existing hand-built paths own the garden; do not lay generic streets over them.
    nh = load('data/nanhu-plan.json'); cx,cy=geo['center']; kx=1113.2*math.cos(math.radians(cy))
    nx,ny=(nh['center'][0]-cx)*kx,(nh['center'][1]-cy)*1113.2
    for key in ['paths','square']:
        for mesh in nh[key]:
            for tri in mesh['triangles']:
                solid.append(Polygon([(nx+mesh['points'][i][0],ny+mesh['points'][i][1]) for i in tri]))
    excluded=set(minzu['replacedRoads']) | {int(i) for i in viaduct['roadOverrides']}
    endpoints={tuple(p) for i,r in enumerate(geo['roads']) if i not in excluded and not r['bridge'] for p in r['points']}
    bridge_index=STRtree([Polygon([p[:2] for p in f]) for f in bridge_faces])
    bridge_ports=[]
    for i,r in enumerate(geo['roads']):
        if not r['bridge'] or i in excluded or r['name']=='南宁大桥':continue
        w=.13 if r['class'] in ['primary','trunk','motorway'] else .085 if r['class']=='secondary' else .0475
        for endpoint,neighbour in [(r['points'][0],r['points'][1]),(r['points'][-1],r['points'][-2])]:
            if tuple(endpoint) not in endpoints:continue
            x,y=endpoint;ux,uy=x-neighbour[0],y-neighbour[1];length=math.hypot(ux,uy)
            if length<.001:continue
            ux,uy=ux/length,uy/length
            face=bridge_faces[int(bridge_index.nearest(Point(x,y)))]
            bridge_ports.append({'edge':[[x-uy*w,y+ux*w],[x+uy*w,y-ux*w]],'outward':[ux,uy],'face':face})
    context = {'origin':'Boundary snapshot of existing detailed models before ground-road replacement.',
               'sourceModelSha256':hashlib.sha256(raw).hexdigest(),
               'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in INPUTS},
               'obstacles':[rings(p) for p in polygons(unary_union(solid))], 'roadFaces':road_faces,'bridgePorts':bridge_ports}
    (ROOT/'data/ground-roads-context.json').write_text(json.dumps(context,ensure_ascii=False,separators=(',',':'))+'\n')
    print('Captured detailed boundaries:',len(road_faces),'road faces;',len(context['obstacles']),'solid footprints',flush=True)


def prepare(capture=False):
    geo,dem,minzu,viaduct = [load(p) for p in ['public/data/geography.json','public/data/terrain.json','data/minzu-plan.json','data/viaduct-plan.json']]
    if capture: capture_context(geo,minzu,viaduct)
    context = load('data/ground-roads-context.json')
    for path,digest in context['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, f'Recapture detailed road boundaries after changing {path}'
    excluded = set(minzu['replacedRoads']) | {int(i) for i in viaduct['roadOverrides']}
    roads = [(i,r) for i,r in enumerate(geo['roads']) if i not in excluded and not r['bridge']]
    tiers = [[],[],[]]; lines = []; indices = []
    for i,r in roads:
        line = LineString(r['points']); indices.append(i); lines.append(line)
        tier = 0 if r['class'] in ['primary','trunk','motorway'] else 1 if r['class'] in ['secondary','tertiary'] else 2
        tiers[tier].append(line.buffer(width(r)/2,cap_style=2,join_style=2,mitre_limit=2))
    water = unary_union([Polygon(p[0],p[1:]) for p in geo['water']]).buffer(.004,join_style=2)
    buildings = unary_union([Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings']]).buffer(.005,join_style=2)
    solids = unary_union([Polygon(p[0],p[1:]) for p in context['obstacles']]).buffer(.005,join_style=2)
    detailed_faces = [Polygon([v[:2] for v in f]) for f in context['roadFaces']]
    detailed = unary_union(detailed_faces)
    exclusion = unary_union([water,buildings,solids,detailed])
    used = Polygon(); surfaces=[]
    for tier,shapes in enumerate(tiers):
        area = make_valid(unary_union(shapes).difference(exclusion).difference(used)).intersection(box(*geo['bounds']))
        surfaces.append(area); used=used.union(area)
        print('Road tier',tier,'area km²',round(area.area/100,3),flush=True)
    # A single restrained dashed divider on primary roads. Every crossing and
    # split is left clear, including intersections introduced by the union.
    line_index=STRtree(lines); marks=[]
    for index,(i,r) in enumerate(roads):
        if r['class'] not in ['primary','trunk','motorway']: continue
        line=lines[index]
        for j in range(1,math.floor(line.length/.45)):
            s=j*.45
            if s>line.length-.20: continue
            p=line.interpolate(s)
            blocked=False
            for other in line_index.query(p.buffer(.20)):
                if other==index: continue
                if p.distance(lines[other]) < width(roads[other][1])/2+.055:
                    blocked=True;break
            if blocked: continue
            a,b=line.interpolate(s-.065),line.interpolate(s+.065)
            if a.distance(b)<.005: continue
            marks.append(LineString([a,b]).buffer(.0017,cap_style=2))
    marking_area=unary_union(marks).intersection(surfaces[0])
    print('Road markings:',len(marks),'dashes',flush=True)
    # Exact displayed terrain triangles, including the fine Nanhu replacement
    # and the retained Zhenning refinement in the smooth profile.
    nh=load('data/nanhu-plan.json'); cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy))
    nx,ny=(nh['center'][0]-cx)*kx,(nh['center'][1]-cy)*1113.2
    west,south,east,north=geo['bounds'];cols,rows=dem['cols'],dem['rows'];dx=(east-west)/(cols-1);dy=(north-south)/(rows-1)
    patch=nh['terrainPatch']; zi0,zj0,zi1,zj1=terrain_patch(tuple(geo['bounds']),cols,rows,tuple(geo['center']))
    road_index=STRtree(detailed_faces)
    ports=[LineString(p['edge']) for p in context['bridgePorts']]
    port_index=STRtree(ports)
    def nearest_join(x,y):
        p=Point(x,y);near=int(road_index.nearest(p));shape=detailed_faces[near];distance=p.distance(shape)
        result=None
        if distance<=.65:
            q=nearest_points(p,shape)[1]
            result=[near,round(q.x,6),round(q.y,6),round(distance,6)]
        for index in port_index.query(p.buffer(.65)):
            port=context['bridgePorts'][int(index)];edge=ports[index]
            cx,cy=edge.centroid.coords[0];ux,uy=port['outward']
            if (x-cx)*ux+(y-cy)*uy<-.002:continue
            gap=p.distance(edge)
            if gap>.65 or result is not None and gap>=result[3]:continue
            q=nearest_points(p,edge)[1]
            result=[-int(index)-1,round(q.x,6),round(q.y,6),round(gap,6)]
        return result
    def terrain_triangles(lightweight):
        step=2 if lightweight else 1
        for j in range(0,rows-1,step):
            for i in range(0,cols-1,step):
                if patch['columnRange'][0]<=i<patch['columnRange'][1] and patch['rowRange'][0]<=j<patch['rowRange'][1]:continue
                ii,jj=min(i+step,cols-1),min(j+step,rows-1)
                refined=lightweight and zi0<=i<zi1 and zj0<=j<zj1
                xs=list(range(i,ii+1)) if refined else [i,ii];ys=list(range(j,jj+1)) if refined else [j,jj]
                for c0,c1 in zip(xs,xs[1:]):
                    for r0,r1 in zip(ys,ys[1:]):
                        v=[(west+c*dx,north-r*dy,c,r) for c,r in [(c0,r0),(c1,r0),(c1,r1),(c0,r1)]]
                        for ids in [(0,2,1),(0,3,2)]:yield [v[k] for k in ids],refined
        for mesh in patch['meshes']:
            for ids in mesh['triangles']:yield [(nx+mesh['points'][k][0],ny+mesh['points'][k][1],-1,-1) for k in ids],False
    surface_parts=[];surface_tiers=[]
    for tier,area in enumerate(surfaces):
        for p in polygons(area):surface_parts.append(p);surface_tiers.append(tier)
    spatial=STRtree(surface_parts)
    meshes={}
    for profile in ['detail','smooth']:
        pts=[];lookup={};faces=[];materials=[];supports=[];point_support=[];joins={}
        for support,refined in terrain_triangles(profile=='smooth'):
            triangle=Polygon([p[:2] for p in support]); candidates=spatial.query(triangle,predicate='intersects')
            if len(candidates)==0: continue
            sid=len(supports);supports.append({'vertices':support,'refined':refined})
            for candidate in candidates:
                area=surface_parts[candidate].intersection(triangle)
                for verts in triangulate(area):
                    tri=[]
                    for x,y in verts:
                        key=(round(float(x),6),round(float(y),6))
                        if key not in lookup:
                            index=len(pts);lookup[key]=index;pts.append(key);point_support.append(sid)
                            join=nearest_join(*key)
                            if join:joins[str(index)]=join
                        tri.append(lookup[key])
                    if len(set(tri))<3 or Polygon([pts[k] for k in tri]).area<1e-10:continue
                    faces.append(tri);materials.append(surface_tiers[candidate])
        # Clip paint to the actual road triangles and remember its support face;
        # barycentric height keeps every marking exactly on its paved surface.
        road_triangles=[Polygon([pts[i] for i in tri]) for tri in faces]
        tri_index=STRtree(road_triangles);paint_pts=[];paint_faces=[]
        for p in polygons(marking_area):
            for candidate in tri_index.query(p,predicate='intersects'):
                if materials[candidate]!=0:continue
                for verts in triangulate(p.intersection(road_triangles[candidate])):
                    start=len(paint_pts)
                    paint_pts.extend([[round(float(x),6),round(float(y),6),int(candidate)] for x,y in verts])
                    paint_faces.append([start,start+1,start+2])
        meshes[profile]={'points':pts,'triangles':faces,'materials':materials,'supports':supports,
                         'pointSupports':point_support,'joins':joins,'paintPoints':paint_pts,'paintTriangles':paint_faces}
        print(profile,len(pts),'vertices;',len(faces),'road triangles;',len(paint_faces),'paint triangles',flush=True)
    trees=STRtree([Point(x,y).buffer(r*1.1+.015,quad_segs=4) for x,y,r in geo['trees']])
    removed=set()
    for p in polygons(used): removed.update(int(i) for i in trees.query(p,predicate='intersects'))
    inputs=INPUTS+['data/ground-roads-context.json']
    plan={'version':1,'sceneCenter':geo['center'],'bbox':geo['bbox'],'roadIndices':indices,
          'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
          'surfaces':[[rings(p) for p in polygons(area)] for area in surfaces],
          'removedTrees':sorted(removed),'meshes':meshes,
          'stats':{'groundWays':len(roads),'preservedBridgeWays':sum(r['bridge'] for r in geo['roads']),
                   'surfaceAreaKm2':round(used.area/100,4),'markedDashes':len(marks),'removedTreeCandidates':len(removed)},
          'assumptions':{'widthMeters':{'major':16,'secondary':10.5,'tertiary':7,'local':5},
                         'roadLiftMeters':.8,'paintLiftMeters':.12,'junctionClearanceMeters':5.5}}
    payload=(json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    (ROOT/'data/ground-roads-plan.json.gz').write_bytes(gzip.compress(payload,compresslevel=9,mtime=0))
    print(plan['stats'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',action='store_true');prepare(p.parse_args().capture)
