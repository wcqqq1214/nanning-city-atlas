"""Prepare source-bounded warehouse grading against actual P4 terrain candidates.

Stores XY topology, pad weights and an explicitly estimated target. Runtime
heights are evaluated against the selected profile's final base terrain, so
outside edges do not bake old compressed vertices into a fresh city surface.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import mapbox_earcut
import numpy as np
from shapely import set_precision, union_all
from shapely.affinity import affine_transform
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union, nearest_points, polygonize

from prepare_building_support import terrain_faces, TerrainSurface
from prepare_waterfront import polygons

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from block_grading import GradePatch


class NativeXYGrid:
    """Fixed-precision overlays on each axis's exact float32 lattice."""
    def __init__(self,bounds):
        self.steps=[float(np.spacing(np.float32(max(abs(bounds[k]),abs(bounds[k+2]))))) for k in [0,1]]
        self.steps=[v if v>0 else 2**-23 for v in self.steps]
        stored=np.asarray(bounds,dtype=np.float32).astype(float)
        for k,v in enumerate(stored):
            if v/self.steps[k%2]!=round(v/self.steps[k%2]):
                raise ValueError('Adjust grading patch bounds to a consistent native XY lattice')

    def encode(self,geometry):
        return set_precision(affine_transform(geometry,[1/self.steps[0],0,0,1/self.steps[1],0,0]),1)

    def decode(self,geometry):
        return affine_transform(geometry,[self.steps[0],0,0,self.steps[1],0,0])


def triangulate_stations(vertices,ends):
    """Retain every collinear boundary station for nonplanar terrain heights."""
    def area(face):
        a,b,c=vertices[face]
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    faces=[list(map(int,f)) for f in mapbox_earcut.triangulate_float64(vertices,ends).reshape(-1,3) if abs(area(f))>1e-12]
    for i,point in enumerate(vertices):
        updated=[]
        for face in faces:
            split=False
            if i not in face:
                for k in range(3):
                    a,b,c=face[k],face[(k+1)%3],face[(k+2)%3]
                    edge=vertices[b]-vertices[a];length2=float(edge@edge)
                    if length2<=1e-20:continue
                    t=float((point-vertices[a])@edge/length2)
                    if 1e-10<t<1-1e-10 and np.linalg.norm(point-(vertices[a]+t*edge))<1e-10:
                        updated.extend([[a,i,c],[i,b,c]]);split=True;break
            if not split:updated.append(face)
        faces=updated
    if set(range(len(vertices)))-{i for face in faces for i in face}:
        raise ValueError('Terrain triangulation omitted a boundary station')
    return np.asarray(faces,dtype=np.int64)


class LocalSurface:
    def __init__(self, faces, bounds):
        xy = faces[:, :, :2]; w, s, e, n = bounds
        keep = (xy[:, :, 0].max(axis=1)>=w)&(xy[:, :, 0].min(axis=1)<=e)&(xy[:, :, 1].max(axis=1)>=s)&(xy[:, :, 1].min(axis=1)<=n)
        self.surface = TerrainSurface(faces[keep])
        self.shapes = [Polygon(t[:, :2]) for t in self.surface.triangles]

    def __call__(self, x, y):
        p = Point(x, y)
        choices = [(i, shape.distance(p)) for i, shape in enumerate(self.shapes)
                   if shape.bounds[0]-.0005<=x<=shape.bounds[2]+.0005 and shape.bounds[1]-.0005<=y<=shape.bounds[3]+.0005]
        if not choices: raise ValueError(f'No base terrain near {(x,y)}')
        i, distance = min(choices, key=lambda v: v[1])
        if distance>.0005: raise ValueError(f'Missing base terrain at {(x,y)}: {distance*100} m')
        a, b, c = self.surface.planes[i]
        return float(a*x+b*y+c)


def rings(shape):
    return [[[float(x), float(y)] for x, y in r.coords] for r in [shape.exterior, *shape.interiors]]


def prepare_site(geo, dem, config, surfaces):
    if config['targetMethod']!='median-existing-two-profile-pad-samples':
        raise ValueError('Unsupported platform target method')
    site = next(s for s in geo['urbanBlocks'] if s['id']==config['id'])
    buildings = [b for b in geo['buildings'] if b.get('blockId')==site['id']]
    boundary = Polygon(site['boundary'][0], site['boundary'][1:])
    occupied = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in buildings])
    court = unary_union([Polygon(s['rings'][0], s['rings'][1:]) for s in site['reservedSpaces'] if s['kind']=='loading-space'])
    # Join the reserved loading strip to the dock faces, retaining the site's
    # concave outline rather than taking a convex hull across its parcel notch.
    pad = occupied.union(court.buffer(config['loadingApronMeters']/100, join_style=2)).buffer(
        config['padApronMeters']/100, join_style=2)
    roads = [r for r in geo['roads'] if r.get('name')==config['accessRoadName'] and not r.get('bridge')]
    road = min(roads, key=lambda r: LineString(r['points']).distance(court.centroid))
    start, end = nearest_points(court.centroid, LineString(road['points']))
    access = LineString([start, end])
    assert not access.intersects(occupied), 'Estimated access crosses a warehouse'
    assert boundary.covers(pad), 'Pad apron exceeds source site'
    protected_roads = unary_union([LineString(r['points']).buffer(.19 if r['class'] in ['primary','trunk','motorway'] else
                                .135 if r['class']=='secondary' else .10)
                                  for r in geo['roads'] if not r.get('bridge') and LineString(r['points']).distance(boundary)<.6])
    water = unary_union([Polygon(r[0], r[1:]) for r in geo['water']])
    protected = water.union(unary_union([Polygon(r[0], r[1:]) for r in geo['parks']]))
    protected = protected.union(protected_roads)
    neighbors = [Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']
                 if b.get('blockId')!=site['id'] and Polygon(b['rings'][0]).distance(boundary)<.6]
    protected = protected.union(unary_union(neighbors).buffer(.03))
    allowed = boundary.union(access.buffer((config['accessWidthMeters']/2+config['accessShoulderMeters'])/100)).difference(protected)
    assert allowed.contains(pad), 'Pad intersects a protected object or lacks transition space'
    drive = access.buffer(config['accessWidthMeters']/200, cap_style=2).difference(protected)
    w, s, e, n = geo['bounds']; dx=(e-w)/(dem['cols']-1);dy=(n-s)/(dem['rows']-1)
    a,b,c,d = allowed.buffer(config['patchMarginMeters']/100).bounds
    ir=[math.floor((a-w)/dx/2)*2,math.ceil((c-w)/dx/2)*2]
    jr=[math.floor((n-d)/dy/2)*2,math.ceil((n-b)/dy/2)*2]
    bounds=[w+ir[0]*dx,n-jr[1]*dy,w+ir[1]*dx,n-jr[0]*dy]
    patch = box(*bounds)
    assert patch.covers(allowed)
    native=NativeXYGrid(bounds)
    qpad,qallowed,qdrive,qwater,qpatch=[native.encode(p) for p in [pad,allowed,drive,water,patch]]
    # All grade break lines partition the mesh. Every pad triangle therefore
    # has weight 1, including long footprint edges and the loading court.
    retaining_width=config.get('retainingWidthMeters')
    collar=None
    if retaining_width is not None:
        if not 0<retaining_width<config['patchMarginMeters']:raise ValueError('Invalid retaining collar width')
        collar=native.encode(pad.buffer(retaining_width/100,join_style=2))
        if not qallowed.covers(collar):raise ValueError('Retaining collar exceeds available site')
    bands = []; previous = qpad
    if collar is not None:bands.append(collar.difference(qpad));previous=collar
    for distance in [5, 15, 30]:
        expanded = native.encode(pad.buffer(distance/100, join_style=2)).intersection(qallowed)
        bands.append(expanded.difference(previous)); previous = expanded
    bands.append(qallowed.difference(previous))
    zones = [('block_paving', qpad)]
    for band in bands:
        zones += [('block_paving', band.intersection(qdrive)), ('ground', band.difference(qdrive))]
    zones += [('base', qpatch.difference(qallowed).difference(qwater))]
    pad,allowed=native.decode(qpad),native.decode(qallowed)
    sub = config['meshSubdivisions']; sx,sy=dx/sub,dy/sub
    cols,rows=(ir[1]-ir[0])*sub,(jr[1]-jr[0])*sub
    points=[];lookup={};triangles=[];materials=[];cells={}
    def vertex(p):
        key=tuple(float(v) for v in p)
        if key not in lookup:lookup[key]=len(points);points.append(list(key))
        return lookup[key]
    linework=[qpatch.difference(qwater).boundary]
    for j in range(rows):
        for i in range(cols):
            x,y=bounds[0]+i*sx,bounds[1]+j*sy
            # Same NE-SW diagonal as the city north-origin terrain grid.
            halves=[Polygon([(x,y),(x+sx,y),(x,y+sy)]),Polygon([(x+sx,y),(x+sx,y+sy),(x,y+sy)])]
            for material, zone in zones:
                for half in halves:
                    for quantized in polygons(zone.intersection(native.encode(half))):
                        linework.append(quantized.boundary)
    # Node the entire arrangement together. Independent cell/zone overlays can
    # snap a shared T-junction differently and leave microscopic overlaps.
    network=union_all(linework,grid_size=1)
    land=qpatch.difference(qwater)
    pieces=[p for p in polygonize(network) if land.covers(p.representative_point())]
    pieces.sort(key=lambda p:(p.bounds,p.area,p.wkb))
    pad_parts=[];allowed_parts=[]
    for quantized in pieces:
        point=quantized.representative_point();on_pad=qpad.covers(point);in_allowed=qallowed.covers(point)
        if on_pad:pad_parts.append(quantized)
        if in_allowed:allowed_parts.append(quantized)
        material='block_paving' if on_pad else 'block_retaining' if collar is not None and collar.covers(point) else 'block_paving' if in_allowed and qdrive.covers(point) else 'ground' if in_allowed else 'base'
        poly=native.decode(quantized)
        if poly.area<1e-12:continue
        outlines=[list(r.coords)[:-1] for r in [poly.exterior,*poly.interiors]]
        vertices=np.asarray([v for ring in outlines for v in ring],dtype=np.float64)
        ends=np.cumsum([len(r) for r in outlines],dtype=np.uint32)
        for face in triangulate_stations(vertices,ends):
            ids=[vertex(vertices[k]) for k in face]
            if Polygon([points[k] for k in ids]).area<1e-12:continue
            a,b,c=[points[k] for k in ids]
            if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:ids.reverse()
            x,y=[sum(points[v][k] for v in ids)/3 for k in [0,1]]
            i=min(cols-1,max(0,int((x-bounds[0])/sx)));j=min(rows-1,max(0,int((y-bounds[1])/sy)))
            cells.setdefault(f'{i},{j}',[]).append(len(triangles));triangles.append(ids);materials.append(material)
    pad=native.decode(union_all(pad_parts,grid_size=1))
    allowed=native.decode(union_all(allowed_parts,grid_size=1))
    if collar is not None:collar=native.decode(collar)
    weights=[]
    for point in points:
        p=Point(point)
        if p.distance(pad)<1e-8:weight=1.0
        elif collar is not None:
            if not collar.contains(p):weight=0.0
            else:
                outer=p.distance(collar.boundary);inner=p.distance(pad)
                weight=outer/(outer+inner)
        elif not allowed.contains(p):weight=0.0
        else:
            outer=p.distance(allowed.boundary);inner=p.distance(pad)
            v=outer/(outer+inner);weight=v*v*(3-2*v)
        weights.append(weight)
    # Fixed regular samples avoid weighting a target toward the denser mesh at
    # polygon corners. A platform is a display estimate, not a surveyed level.
    samples=[];a,b,c,d=pad.bounds
    for x in np.arange(a,c+.00001,.1):
        for y in np.arange(b,d+.00001,.1):
            if pad.covers(Point(x,y)):
                samples.extend(surface(float(x),float(y)) for surface in surfaces.values())
    target=round(float(np.median(samples)),6)
    return {'id':site['id'],'bounds':bounds,'columnRange':ir,'rowRange':jr,
            'nativeXYGridSceneUnits':native.steps,
            'grid':{'columns':cols,'rows':rows,'dx':sx,'dy':sy},'points':points,'triangles':triangles,
            'materials':materials,'cells':cells,'weights':weights,'targetSceneZ':target,
            'retainingFaceGradeThreshold':config['retainingFaceGradeThreshold'],
            'retainingWidthMeters':retaining_width,
            'targetMethod':config['targetMethod'],'targetSampleCount':len(samples),'boundary':rings(boundary),
            'pad':rings(pad),'gradingArea':[rings(p) for p in polygons(allowed)],
            'estimatedAccess':{'points':[list(p) for p in access.coords],'widthMeters':config['accessWidthMeters'],
                               'roadName':road['name'],'lengthMeters':access.length*100,'surveyed':False},
            'buildingIds':[b['id'] for b in buildings],'notes':config['notes']}


def profile_report(plan, surface):
    patch=GradePatch(plan);levels=patch.levels(surface)
    triangles=np.array([[(*plan['points'][i],levels[i]) for i in t] for t in plan['triangles']])
    measured=TerrainSurface(triangles)
    a=triangles[:,1]-triangles[:,0];b=triangles[:,2]-triangles[:,0]
    normal=np.cross(a,b);grade=np.linalg.norm(normal[:,:2],axis=1)/np.abs(normal[:,2])
    native=NativeXYGrid(plan['bounds'])
    boundary=native.decode(native.encode(box(*plan['bounds']))).boundary
    edge=[i for i,p in enumerate(plan['points']) if Point(p).distance(boundary)<1e-8]
    access=LineString(plan['estimatedAccess']['points'])
    stops=np.linspace(0,access.length,max(2,math.ceil(access.length/.05)))
    path=[(float(s),patch.sample(*access.interpolate(s).coords[0],levels)) for s in stops]
    grades=[abs(q[1]-p[1])/(q[0]-p[0]) for p,q in zip(path,path[1:])]
    pad=Polygon(plan['pad'][0],plan['pad'][1:])
    base_levels=[surface(x,y) for x,y in plan['points']]
    changes=np.asarray(levels)-np.asarray(base_levels)
    return {'triangles':len(triangles),'pad':measured.bounds(pad),
            'baseVertexLevels':base_levels, 'gradedVertexLevels':levels,
            'maximumCutMeters':float(max(0,-changes.min())*100),'maximumFillMeters':float(max(0,changes.max())*100),
            'boundaryMaximumChangeMeters':max(abs(levels[i]-surface(*plan['points'][i]))*100 for i in edge),
            'maximumSurfaceGrade':float(grade.max()),'facesSteeperThanOneToOne':int((grade>1).sum()),
            'estimatedAccessMaximumGrade':max(grades),'estimatedAccessSamples':path}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geography',type=Path,required=True);p.add_argument('--terrain',type=Path,required=True)
    p.add_argument('--detail',type=Path,required=True);p.add_argument('--smooth',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();source=ROOT/'data/block-grading-source.json'
    geo=json.loads(args.geography.read_text());dem=json.loads(args.terrain.read_text());config=json.loads(source.read_text())
    faces={}
    for name in ['detail','smooth']:
        print('Decoding',name,flush=True);faces[name]=terrain_faces(getattr(args,name))
    sites=[];reports={}
    for spec in config['sites']:
        site=next(s for s in geo['urbanBlocks'] if s['id']==spec['id'])
        bounds=Polygon(site['boundary'][0]).buffer(2).bounds
        surfaces={name:LocalSurface(f,bounds) for name,f in faces.items()}
        plan=prepare_site(geo,dem,spec,surfaces);sites.append(plan)
        reports[spec['id']]={name:profile_report(plan,surface) for name,surface in surfaces.items()}
    result={'status':'candidate; steep edges, access, final base terrain and city integration require validation',
            'sites':sites,'profiles':reports,'inputs':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                [args.geography,args.terrain,args.detail,args.smooth,source]},
            'tools':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                     [Path(__file__).resolve(),ROOT/'blender/block_grading.py',ROOT/'scripts/prepare_building_support.py']}}
    result['runtimeInputs']={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in
                            [('public/data/geography.json',args.geography),('public/data/terrain.json',args.terrain),
                             ('data/block-grading-source.json',source)]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({i:{p:{k:v for k,v in r.items() if k not in ['estimatedAccessSamples','baseVertexLevels','gradedVertexLevels']} for p,r in profiles.items()}
                      for i,profiles in reports.items()},ensure_ascii=False,indent=2),flush=True)
