"""Loft estimated site access to the exact boundary of resolved ground roads.

The road-top and supporting-soil meshes are separate outputs. The latter must
replace the old grading below the connector before city integration is valid.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import mapbox_earcut
from shapely import union_all
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union, polygonize
from shapely.strtree import STRtree

from prepare_block_grading import LocalSurface, NativeXYGrid, triangulate_stations
from prepare_building_support import TerrainSurface, geometry_points
from prepare_waterfront import polygons

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(root, hashes, required=()):
    if any(name not in hashes for name in required):
        raise ValueError('Missing required source bindings')
    for name, expected in hashes.items():
        path=(root/name).resolve();path.relative_to(root.resolve())
        if not path.is_file() or digest(path)!=expected:
            raise ValueError(f'Stale access source: {name}')


def load_native_surface(root, directory, grading_path, profile):
    report_path=directory/'report.json';report=json.loads(report_path.read_text())
    if report['siteGradingDisabledForComparison'] or report['planHash']!=digest(grading_path):
        raise ValueError('Access requires the current graded native terrain')
    verify_inputs(root,report.get('inputHashes',{}),['public/data/geography.json','public/data/terrain.json','data/block-grading-plan.json'])
    verify_inputs(root,report['tools'])
    path=directory/(profile+'.npz')
    if digest(path)!=report['profiles'][profile]['sha256']:
        raise ValueError('Native terrain capture changed')
    return dict(np.load(path)),{str(path):digest(path),str(report_path):digest(report_path)}


def coordinates(geometry):
    if geometry.is_empty:return []
    if hasattr(geometry,'geoms'):return [p for g in geometry.geoms for p in coordinates(g)]
    return list(geometry.coords)


def make_access(plan, road_faces, terrain, row_spacing=.05, column_spacing=.01):
    origin,end=np.asarray(plan['estimatedAccess']['points'],dtype=float)
    axis=(end-origin)/np.linalg.norm(end-origin);side=np.array([-axis[1],axis[0]])
    reach=float(np.linalg.norm(end-origin)+.3);half=plan['estimatedAccess']['widthMeters']/200
    pad=Polygon(plan['pad'][0],plan['pad'][1:])
    def xy(s,t):return origin+axis*s+side*t
    corridor=Polygon([xy(s,t) for s,t in [(0,-half),(reach,-half),(reach,half),(0,half)]])
    local=LocalSurface(road_faces,corridor.buffer(.05).bounds)
    road=unary_union(local.shapes)
    # Include mesh-border vertices: interpolation at the mouth must preserve
    # every resolved road edge and its changes of plane, not only the corners.
    offsets=list(np.linspace(-half,half,max(2,math.ceil(2*half/column_spacing)+1)))
    for triangle in local.surface.triangles:
        for p in triangle:
            t=float(np.dot(p[:2]-origin,side));s=float(np.dot(p[:2]-origin,axis))
            if -half<t<half and 0<s<reach:offsets.append(t)
    offsets=sorted(set(round(t,10) for t in offsets))
    exits=[];contacts=[]
    for t in offsets:
        ray=LineString([xy(0,t),xy(reach,t)])
        exits.append(max(float(np.dot(np.asarray(p)-origin,axis)) for p in coordinates(ray.intersection(pad))))
        hits=[float(np.dot(np.asarray(p)-origin,axis)) for p in coordinates(ray.intersection(road))]
        if not hits:raise ValueError('Estimated access misses the resolved road')
        s=min(hits);point=xy(s,t);top=local(*point)
        index=min(range(len(local.shapes)),key=lambda i:local.shapes[i].distance(Point(point)))
        derivative=float(np.dot(local.surface.planes[index,:2],axis))
        thickness=top-terrain(*point)
        if thickness < -1e-4:
            raise ValueError(f'Resolved road top lies below actual base terrain: XY={point.tolist()}, road={top}, terrain={terrain(*point)}, depthMeters={-thickness*100}')
        contacts.append({'station':s,'offset':t,'point':[float(v) for v in point],
                         'top':top,'soil':terrain(*point),'derivative':derivative,'thickness':max(0,thickness)})
    start=min(exits)-.05
    if start<=0 or start>=min(c['station'] for c in contacts):raise ValueError('No transition length')
    rows=max(2,math.ceil(max(c['station']-start for c in contacts)/row_spacing)+1)
    top_points=[];soil_points=[]
    for u in np.linspace(0,1,rows):
        h=u*u*(3-2*u)
        for c in contacts:
            length=c['station']-start;point=xy(start+u*length,c['offset'])
            # Cubic Hermite: level yard at the start, matching road normal
            # slope at the mouth. The soil meets the road's existing underside.
            z=(1-h)*plan['targetSceneZ']+h*c['top']+(u*u*u-u*u)*length*c['derivative']
            top_points.append([float(point[0]),float(point[1]),float(z)])
            soil_points.append([float(point[0]),float(point[1]),float(z-h*c['thickness'])])
    columns=len(contacts);triangles=[]
    for j in range(rows-1):
        for i in range(columns-1):
            a=j*columns+i;b=a+1;c=a+columns;d=c+1
            for ids in [[a,c,b],[b,c,d]]:
                p,q,r=[top_points[k] for k in ids]
                if np.cross(np.subtract(q,p),np.subtract(r,p))[2]<0:ids.reverse()
                triangles.append(ids)
    footprint=unary_union([Polygon([top_points[i][:2] for i in tri]) for tri in triangles])
    assert footprint.intersection(road).area<1e-8,'Connector overlaps existing road pavement'
    mouth=[]
    for a,b in zip(contacts,contacts[1:]):
        for t in np.linspace(0,1,11):
            point=(1-t)*np.array(a['point'])+t*np.array(b['point'])
            mouth.append(abs((1-t)*a['top']+t*b['top']-local(*point))*100)
    faces=np.asarray([[top_points[i] for i in tri] for tri in triangles])
    normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    slopes=np.linalg.norm(normal[:,:2],axis=1)/abs(normal[:,2])
    def slope(a,b):return abs(a[2]-b[2])/math.dist(a[:2],b[:2])
    longitudinal=max(slope(top_points[j*columns+i],top_points[(j+1)*columns+i]) for j in range(rows-1) for i in range(columns))
    transverse=max(slope(top_points[j*columns+i],top_points[j*columns+i+1]) for j in range(rows) for i in range(columns-1))
    return {'topPoints':top_points,'soilPoints':soil_points,'triangles':triangles,
            'contacts':contacts,'rows':rows,'columns':columns,'startStation':start,
            'statistics':{'triangles':len(triangles),'areaSquareMeters':footprint.area*10000,
                          'mouthMaximumHeightErrorMeters':max(mouth),'maximumSurfaceGrade':float(slopes.max()),
                          'maximumLongitudinalGrade':longitudinal,'maximumCrossGrade':transverse,
                          'maximumThicknessMeters':max((a[2]-b[2])*100 for a,b in zip(top_points,soil_points))}}


def soil_penetration(access, old_triangles):
    old=TerrainSurface(old_triangles);shapes=[Polygon(t[:,:2]) for t in old.triangles];tree=STRtree(shapes)
    roof=TerrainSurface(np.asarray([[access['topPoints'][i] for i in ids] for ids in access['triangles']]))
    worst=0;witness=None
    for tri,plane in zip(roof.triangles,roof.planes):
        shape=Polygon(tri[:,:2])
        for index in tree.query(shape,predicate='intersects'):
            for x,y in geometry_points(shape.intersection(shapes[int(index)])):
                delta=float(np.dot(old.planes[int(index)]-plane,[x,y,1]))
                if delta>worst:worst=delta;witness=[x,y]
    return {'maximumOldTerrainAbovePavementMeters':worst*100,'witnessSceneXY':witness,
            'supportReplacementRequired':True}


def triangulate_preserving_boundary(poly):
    """Earcut can omit collinear vertices; restore them before assigning Z."""
    if not poly.is_valid:
        # GEOS overlays can leave zero-width out-and-back needles after edge
        # station projection. Remove only numerically area-free defects.
        fixed=poly.buffer(0)
        if abs(fixed.area-poly.area)>1e-10:raise ValueError('Material polygon repair would change terrain coverage')
        return [t for p in polygons(fixed) for t in triangulate_preserving_boundary(p)]
    rings=[list(r.coords)[:-1] for r in [poly.exterior,*poly.interiors]]
    points=np.asarray([p for r in rings for p in r],dtype=float)
    faces=mapbox_earcut.triangulate_float64(points,np.cumsum([len(r) for r in rings],dtype=np.uint32)).reshape(-1,3).tolist()
    for index,p in enumerate(points):
        if any(index in t for t in faces):continue
        for j,t in enumerate(faces):
            found=False
            for k in range(3):
                a,b,c=t[k],t[(k+1)%3],t[(k+2)%3]
                if LineString([points[a],points[b]]).distance(Point(p))<1e-10 and min(
                    np.linalg.norm(p-points[a]),np.linalg.norm(p-points[b]))>1e-10:
                    faces[j:j+1]=[[a,index,c],[index,b,c]];found=True;break
            if found:break
    return [[points[i].tolist() for i in t] for t in faces if Polygon(points[t]).area>1e-12]


def replace_soil(access, old_triangles, road_faces, shoulder=.05, old_materials=None):
    """Replace complete intersected faces; shoulders taper to unchanged soil."""
    old=TerrainSurface(old_triangles)
    soil=TerrainSurface(np.asarray([[access['soilPoints'][i] for i in ids] for ids in access['triangles']]))
    soil_shapes=[Polygon(t[:,:2]) for t in soil.triangles];soil_tree=STRtree(soil_shapes)
    core=unary_union(soil_shapes)
    road=LocalSurface(road_faces,core.buffer(shoulder+.05).bounds)
    protected=unary_union(road.shapes)
    effect=core.buffer(shoulder,join_style=2).difference(protected)
    edge_points=list(core.exterior.coords)
    # Narrow shoulders also get an intermediate contour; long triangles cannot
    # bridge over the entire transition from lowered support to old ground.
    middle=core.buffer(shoulder/2,join_style=2).intersection(effect)
    output=[];materials=[];changed=0
    old_materials=old_materials or ['ground']*len(old.triangles)
    def soil_height(point):
        p=Point(point);nearest=core.exterior.interpolate(core.exterior.project(p))
        hits=soil_tree.query(nearest.buffer(1e-9),predicate='intersects')
        i=min((int(i) for i in hits),key=lambda i:soil_shapes[i].distance(nearest))
        return float(np.dot(soil.planes[i],[nearest.x,nearest.y,1]))
    for tri,plane,material in zip(old.triangles,old.planes,old_materials):
        shape=Polygon(tri[:,:2])
        if not shape.intersects(effect):output.append(tri.tolist());materials.append(material);continue
        changed+=1
        # Inside: overlay the existing and new triangulations, preserving the
        # exact new supporting surface rather than merely sampling its corners.
        for i in soil_tree.query(shape,predicate='intersects'):
            for poly in polygons(shape.intersection(soil_shapes[int(i)])):
                if poly.area<1e-12:continue
                for face in triangulate_preserving_boundary(poly):
                    output.append([[x,y,float(np.dot(soil.planes[int(i)],[x,y,1]))] for x,y in face])
                    materials.append(material)
        outside=shape.difference(core)
        for zone in [middle.difference(core),effect.difference(middle),shape.difference(effect)]:
            for poly in polygons(outside.intersection(zone)):
                if poly.area<1e-12:continue
                # Include each non-linear loft edge station on the shoulder.
                rings=[]
                for ring in [poly.exterior,*poly.interiors]:
                    coords=list(ring.coords);expanded=[]
                    for a,b in zip(coords,coords[1:]):
                        line=LineString([a,b])
                        if line.length<1e-12:continue
                        distances={0.0}
                        for p in edge_points:
                            if line.distance(Point(p))<1e-9:
                                t=line.project(Point(p))
                                if 1e-10<t<line.length-1e-10:distances.add(t)
                        expanded.extend(tuple(line.interpolate(t).coords[0]) for t in sorted(distances))
                    rings.append(expanded)
                poly=Polygon(rings[0],rings[1:])
                for face in triangulate_preserving_boundary(poly):
                    vertices=[]
                    for x,y in face:
                        p=Point(x,y);original=float(np.dot(plane,[x,y,1]));distance=p.distance(core)
                        if distance<1e-9:weight=1.
                        elif not effect.contains(p):weight=0.
                        else:
                            outer=p.distance(effect.boundary);v=outer/(outer+distance);weight=v*v*(3-2*v)
                        z=original if weight==0 else (1-weight)*original+weight*soil_height((x,y))
                        vertices.append([x,y,z])
                    output.append(vertices)
                    materials.append(material)
    result=np.asarray(output);expected=unary_union([Polygon(t[:,:2]) for t in old.triangles])
    coverage=unary_union([Polygon(t[:,:2]) for t in result])
    gap=coverage.symmetric_difference(expected).area*10000
    overlap=(sum(Polygon(t[:,:2]).area for t in result)-coverage.area)*10000
    if gap>1e-4 or abs(overlap)>1e-4:raise ValueError(f'Access soil coverage mismatch {gap}, {overlap}')
    shared=defaultdict(list)
    for tri in output:
        for x,y,z in tri:shared[(round(x,8),round(y,8))].append(z)
    return output,{'replacedOldFaces':changed,'triangles':len(output),'coverageDifferenceSquareMeters':gap,
                   'overlapSquareMeters':overlap,'shoulderMeters':shoulder*100,'materials':materials,
                   'maximumNearSharedVertexSpreadMeters':max(max(v)-min(v) for v in shared.values())*100}


def stabilize_soil(triangles, materials, bounds):
    """Node all edges on one float32 XY lattice and share stored vertex Zs."""
    source=TerrainSurface(np.asarray(triangles,dtype=float));grid=NativeXYGrid(bounds)
    if len(source.triangles)!=len(triangles):raise ValueError('Source overlay has undefined projected faces')
    if len(materials)!=len(triangles):raise ValueError('Missing source overlay materials')
    shapes=[Polygon(t[:,:2]) for t in source.triangles];tree=STRtree(shapes)
    original=unary_union(shapes)
    if (sum(p.area for p in shapes)-original.area)*10000>1e-4:
        raise ValueError('Source overlay already overlaps; repair it before storage')
    quantized=[grid.encode(shape) for shape in shapes]
    # Snap the actual domain once. Independently snapped thin triangles can
    # create tiny artificial holes; these are filled by the shared arrangement,
    # while holes in the original terrain domain remain explicit boundaries.
    coverage=grid.encode(original)
    network=union_all([coverage.boundary,*[p.boundary for p in quantized if not p.is_empty]],grid_size=1)
    pieces=[p for p in polygonize(network) if coverage.covers(p.representative_point())]
    pieces.sort(key=lambda p:(p.bounds,p.area,p.wkb))
    original_vertices={tuple(p[:2]):float(np.float32(p[2])) for t in source.triangles for p in t}
    vertices={};output=[];keys=[]
    def source_face(point):
        p=Point(point);hits=tree.query(p,predicate='intersects')
        if len(hits):return int(min(hits))
        return int(tree.nearest(p))
    def vertex(point):
        xy=tuple(point)
        if xy not in vertices:
            z=original_vertices.get(xy)
            if z is None:z=float(np.float32(np.dot(source.planes[source_face(xy)],[*xy,1])))
            vertices[xy]=[*xy,z]
        return vertices[xy]
    for piece in pieces:
        poly=grid.decode(piece);owner=source_face(poly.representative_point().coords[0])
        rings=[list(r.coords)[:-1] for r in [poly.exterior,*poly.interiors]]
        points=np.asarray([p for ring in rings for p in ring],dtype=float)
        ends=np.cumsum([len(ring) for ring in rings],dtype=np.uint32)
        for face in triangulate_stations(points,ends):
            tri=[vertex(points[i]) for i in face]
            a,b,c=np.asarray(tri);area=np.cross(b-a,c-a)[2]
            if area==0:raise ValueError('Native lattice triangulation collapsed')
            if area<0:tri.reverse()
            output.append(tri);keys.append(materials[owner])
    stored=np.asarray(output,dtype=np.float32).astype(float)
    if not np.array_equal(stored,np.asarray(output)):raise ValueError('Overlay is not exactly float32 representable')
    cover=unary_union([Polygon(t[:,:2]) for t in stored])
    overlap=(sum(Polygon(t[:,:2]).area for t in stored)-cover.area)*10000
    expected=grid.decode(coverage)
    difference=cover.symmetric_difference(expected).area*10000
    if abs(overlap)>1e-5 or difference>1e-6:
        raise ValueError(f'Native overlay coverage failed: overlap={overlap} m2, difference={difference} m2')
    tolerance=math.hypot(*grid.steps)
    outside=cover.difference(original.buffer(tolerance)).area*10000
    missing=original.difference(cover.buffer(tolerance)).area*10000
    if max(outside,missing)>1e-5:raise ValueError('Native overlay changed the source domain beyond its XY lattice')
    return output,keys,{'triangles':len(output),'inputTriangles':len(triangles),'nativeXYGridSceneUnits':grid.steps,
                        'overlapSquareMeters':overlap,'coverageToleranceMeters':tolerance*100,
                        'sourceCoverageDifferenceSquareMeters':cover.symmetric_difference(original).area*10000,
                        'outsideSourceBeyondToleranceSquareMeters':outside,'missingSourceBeyondToleranceSquareMeters':missing}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grading',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native-terrain',type=Path,required=True,help='Source-bound check_site_grading.py output for the current city')
    p.add_argument('--native-storage',action='store_true',help='Prepare shared float32 terrain/connector vertices before Blender import')
    args=p.parse_args();grading=json.loads(args.grading.read_text());records={};inputs={str(args.grading):digest(args.grading)}
    for plan in grading['sites']:
        records[plan['id']]={}
        for profile in ['detail','smooth']:
            path=ROOT/f'data/road-solids-{profile}.npz';meta_path=path.with_suffix('.json')
            meta=json.loads(meta_path.read_text());assert meta['sha256']==digest(path)
            verify_inputs(ROOT,meta['inputHashes'],['public/data/terrain.json','public/data/geography.json','data/block-grading-plan.json'])
            inputs.update({str(path):digest(path),str(meta_path):digest(meta_path)})
            data=np.load(path);road_faces=data['ground']
            native,bindings=load_native_surface(ROOT,args.native_terrain,args.grading,profile);inputs.update(bindings)
            centers=native['triangles'][:,:,:2].mean(axis=1);w,s,e,n=plan['bounds']
            keep=(centers[:,0]>=w)&(centers[:,0]<=e)&(centers[:,1]>=s)&(centers[:,1]<=n)
            old=native['triangles'][keep]
            terrain=LocalSurface(old,plan['bounds'])
            import sys
            sys.path.insert(0,str(ROOT/'blender'))
            from local_terrain import MATERIAL_KEYS as BASE_KEYS
            from site_grading import MATERIAL_KEYS as SITE_KEYS
            keys=BASE_KEYS+SITE_KEYS
            old_materials=[keys[int(i)] for i in native['materials'][keep]]
            result=make_access(plan,road_faces,terrain)
            if args.native_storage:
                for key in ['topPoints','soilPoints']:result[key]=np.asarray(result[key],dtype=np.float32).astype(float).tolist()
                result['statisticsBeforeNativeStorage']=result['statistics']
                top=np.asarray(result['topPoints']);soil=np.asarray(result['soilPoints']);faces=top[result['triangles']]
                normals=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]);rows=result['rows'];columns=result['columns']
                if np.any(normals[:,2]<=0):raise ValueError('Stored access pavement collapsed or reversed')
                def slope(a,b):return abs(a[2]-b[2])/math.dist(a[:2],b[:2])
                road=LocalSurface(road_faces,plan['bounds'])
                result['statistics']={'triangles':len(faces),'areaSquareMeters':sum(Polygon(t[:,:2]).area for t in faces)*10000,
                    'mouthMaximumHeightErrorMeters':max(abs(p[2]-road(*p[:2])) for p in top[-columns:])*100,
                    'maximumSurfaceGrade':float((np.linalg.norm(normals[:,:2],axis=1)/normals[:,2]).max()),
                    'maximumLongitudinalGrade':max(slope(top[j*columns+i],top[(j+1)*columns+i]) for j in range(rows-1) for i in range(columns)),
                    'maximumCrossGrade':max(slope(top[j*columns+i],top[j*columns+i+1]) for j in range(rows) for i in range(columns-1)),
                    'maximumThicknessMeters':float((top[:,2]-soil[:,2]).max()*100)}
                if result['statistics']['mouthMaximumHeightErrorMeters']>.005:raise ValueError('Stored access mouth no longer matches the road')
            result['oldTerrainAudit']=soil_penetration(result,old)
            result['terrainTriangles'],result['terrainReplacementAudit']=replace_soil(result,old,road_faces,old_materials=old_materials)
            result['terrainMaterials']=result['terrainReplacementAudit'].pop('materials')
            if args.native_storage:
                result['terrainTriangles'],result['terrainMaterials'],result['nativeStorageAudit']=stabilize_soil(result['terrainTriangles'],result['terrainMaterials'],plan['bounds'])
            result['finalTerrainAudit']=soil_penetration(result,np.asarray(result['terrainTriangles']))
            if result['finalTerrainAudit']['maximumOldTerrainAbovePavementMeters']>1e-5:
                raise ValueError('Replacement soil still penetrates the connector')
            result['finalTerrainAudit']['supportReplacementRequired']=False
            w,s,e,n=plan['bounds'];xy=road_faces[:,:,:2]
            keep=(xy[:,:,0].max(axis=1)>=w)&(xy[:,:,0].min(axis=1)<=e)&(xy[:,:,1].max(axis=1)>=s)&(xy[:,:,1].min(axis=1)<=n)
            context=TerrainSurface(road_faces[keep]);result['contextRoadTriangles']=[]
            for triangle,plane in zip(context.triangles,context.planes):
                for poly in polygons(Polygon(triangle[:,:2]).intersection(box(w,s,e,n))):
                    if poly.area<1e-12:continue
                    for face in triangulate_preserving_boundary(poly):
                        result['contextRoadTriangles'].append([[x,y,float(np.dot(plane,[x,y,1]))] for x,y in face])
            records[plan['id']][profile]=result
            print(profile,result['statistics'],result['oldTerrainAudit'],result['terrainReplacementAudit'],result['finalTerrainAudit'],flush=True)
    output={'status':'candidate connector and replaced supporting terrain; final dependency rebuild and city integration pending',
            'sites':records,'inputs':inputs,'tools':{str(p.relative_to(ROOT)):digest(p) for p in
                [Path(__file__).resolve(),ROOT/'scripts/prepare_block_grading.py',ROOT/'scripts/prepare_building_support.py']}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
