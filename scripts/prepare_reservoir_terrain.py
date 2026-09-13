"""Prepare a source-bound reservoir, bank and estimated dam surface on one mesh.

This writes an independent plan. Runtime activation must replace the selected
base cells, use the same height sampler, remove ordinary dam buildings, and
rebuild downstream roads, vegetation, supports and reduction plans.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import gaussian_filter, map_coordinates
from shapely import union_all
from shapely.geometry import Polygon, LineString, Point, box, mapping, shape
from shapely.ops import polygonize, unary_union,nearest_points,substring
from shapely.strtree import STRtree
from prepare_block_grading import NativeXYGrid, triangulate_stations
from prepare_waterfront import polygons
from prepare_building_shorelines import digest
from reservoir_interfaces import audit_interfaces
from reservoir_connections import connect_water_fields,protected_banks,protection_weights,protected_bank_lines
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reservoir_water import WaterLevelField


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(value):
    value = np.clip(value, 0, 1)
    return value*value*(3-2*value)


def nearest_shore_level(field,polygon,point):
    # MultiLineString.interpolate(project(...)) can clamp to its first ring.
    # Query the actual nearest location across the exterior and every island.
    closest=nearest_points(polygon.boundary,point)[0]
    return field.meters(closest.x,closest.y)


def restoration_boundary_sides(bounds,city_bounds,enabled=False):
    """Only the atlas cut can omit blending to an adjacent old terrain cell."""
    names=['west','south','east','north']
    return [name for k,name in enumerate(names) if enabled and abs(bounds[k]-city_bounds[k])<1e-9]


def restoration_edge_distance(point,bounds,open_sides):
    distances=dict(zip(['west','south','east','north'],[point[0]-bounds[0],point[1]-bounds[1],bounds[2]-point[0],bounds[3]-point[1]]))
    return min((v for k,v in distances.items() if k not in open_sides),default=float('inf'))*100


def water_mesh_lines(entry,polygon,native):
    regions=[Polygon(r['rings'][0],r['rings'][1:]) for r in entry['levelRegions']]
    combined=unary_union(regions)
    if (combined.symmetric_difference(polygon).area*10000>1e-5
            or abs(sum(p.area for p in regions)-combined.area)*10000>1e-5):
        raise ValueError('Water level regions must cover the source lake exactly without overlap')
    qp=native.encode(polygon);step=entry['waterMeshSpacingMeters']/100
    if not 0<step<=entry['transitionWidthMeters']/100:raise ValueError('Water mesh must resolve the transition width')
    lines=[qp.boundary]
    lines.extend(native.encode(r.boundary).intersection(qp) for r in regions)
    a,b,c,d=polygon.bounds
    for x in np.arange(math.floor(a/step)*step,c+step,step):
        lines.append(native.encode(LineString([(x,b),(x,d)])).intersection(qp))
    for y in np.arange(math.floor(b/step)*step,d+step,step):
        lines.append(native.encode(LineString([(a,y),(c,y)])).intersection(qp))
    transition_spacing=entry.get('transitionMeshSpacingMeters')
    if transition_spacing is not None:
        regions=[Polygon(r['rings'][0],r['rings'][1:]) for r in entry.get('levelInfluenceRegions',entry['levelRegions'])]
        fine=transition_spacing/100
        if not 0<fine<step:raise ValueError('Transition mesh spacing must be finer than the water mesh')
        width=entry['transitionWidthMeters']/100
        # The level field blends wherever another source region is within
        # its support radius, including around the ends of a mapped join.
        zone=unary_union([part for i,left in enumerate(regions) for right in regions[i+1:]
                          for part in [left.buffer(width).intersection(right),right.buffer(width).intersection(left)]]).intersection(polygon)
        if not zone.is_empty:
            # Cover the native snapping margin along the source shore too;
            # otherwise a sub-millimetre strip can retain a long coarse face.
            qzone=native.encode(zone.buffer(2*max(native.steps))).intersection(qp);lines.append(qzone.boundary)
            a,b,c,d=zone.bounds
            for x in np.arange(math.floor(a/fine)*fine,c+fine,fine):
                lines.append(native.encode(LineString([(x,b),(x,d)])).intersection(qzone))
            for y in np.arange(math.floor(b/fine)*fine,d+fine,fine):
                lines.append(native.encode(LineString([(a,y),(c,y)])).intersection(qzone))
    return lines


def prepare_water_mesh(entry,polygon,native,shore_network,prepared_cells=None):
    """Use one native XY lattice and preserve every land-side shoreline station."""
    qp=native.encode(polygon);field=WaterLevelField(entry)
    lines=water_mesh_lines(entry,polygon,native)
    if prepared_cells is None:
        prepared_cells=polygonize(union_all(lines+[shore_network],grid_size=1))
    # Reuse the land arrangement verbatim. Re-intersecting its snapped edges
    # with the original boundary drops stations that moved by one lattice unit.
    cells=[p for p in prepared_cells if qp.covers(p.representative_point())]
    points=[];lookup={};faces=[]
    for cell in sorted(cells,key=lambda p:(p.bounds,p.area,p.wkb)):
        cell=native.decode(cell);rings=[list(r.coords)[:-1] for r in [cell.exterior,*cell.interiors]]
        xy=np.asarray([p for r in rings for p in r]);ends=np.cumsum([len(r) for r in rings],dtype=np.uint32)
        for triangle in triangulate_stations(xy,ends):
            ids=[]
            for point in xy[triangle]:
                key=tuple(map(float,point))
                if key not in lookup:lookup[key]=len(points);points.append(list(key))
                ids.append(lookup[key])
            a,b,c=[points[i] for i in ids];area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if area==0:continue
            if area<0:ids.reverse()
            faces.append(ids)
    return {'points':points,'targetMeters':[field.meters(*p) for p in points],'triangles':faces,
            'method':'source-region display estimates blended continuously over the declared transition width; not a hydraulic model'}


def crest_polygon(footprint, width_meters, inset_meters, inset_mode='footprint'):
    if width_meters <= 0 or inset_meters <= 0:
        raise ValueError('Positive estimated crest width/end inset required')
    corners = np.asarray(footprint.minimum_rotated_rectangle.exterior.coords[:-1])
    edges = np.roll(corners, -1, axis=0)-corners
    edge = edges[np.argmax(np.linalg.norm(edges, axis=1))]
    center = corners.mean(axis=0)
    line = LineString([center-edge, center+edge])
    if inset_mode == 'axis':
        # End setbacks trim the mapped centreline, independently of the dam's
        # transverse width. Eroding the entire footprint shortens tapered dams.
        axis = line.intersection(footprint)
        if axis.geom_type != 'LineString' or axis.length*100 <= 2*inset_meters+width_meters:
            raise ValueError('Mapped dam has no continuous axis for the selected end setbacks')
        axis = substring(axis, inset_meters/100, axis.length-inset_meters/100)
    elif inset_mode == 'footprint':
        # Existing source plans retain their explicitly estimated envelope.
        # Individual dams can migrate to axis setbacks after visual review.
        axis = line.intersection(footprint.buffer(-inset_meters/100))
    else:
        raise ValueError('Unknown crest inset mode')
    if axis.is_empty or axis.length*100 < width_meters:
        raise ValueError('Mapped footprint is too narrow for the selected crest estimate')
    crest = axis.buffer(width_meters/200, cap_style=2, join_style=2)
    if inset_mode == 'axis' and not footprint.buffer(1e-12).covers(crest):
        raise ValueError('Selected crest width extends outside the mapped dam')
    crest = crest.intersection(footprint)
    if crest.is_empty or not footprint.covers(crest):
        raise ValueError('Estimated crest is outside its mapped dam')
    return crest


def replacement_ranges(bounds,cols,rows,focus,margin_meters,clip_to_city=False):
    w,s,e,n=bounds;dx=(e-w)/(cols-1);dy=(n-s)/(rows-1)
    a,b,c,d=focus.buffer(margin_meters/100).bounds
    ir=[math.floor((a-w)/dx/2)*2,math.ceil((c-w)/dx/2)*2]
    jr=[math.floor((n-d)/dy/2)*2,math.ceil((n-b)/dy/2)*2]
    clipped=False
    if ir[0]<0 or jr[0]<0 or ir[1]>=cols or jr[1]>=rows:
        if not clip_to_city:raise ValueError('Reservoir replacement exceeds city grid')
        if (cols-1)%2 or (rows-1)%2 or focus.difference(box(*bounds)).area>1e-10:
            raise ValueError('Boundary-clipped reservoir must stay inside a two-profile city grid')
        ir=[max(0,ir[0]),min(cols-1,ir[1])];jr=[max(0,jr[0]),min(rows-1,jr[1])]
        clipped=True
    return ir,jr,clipped


def trim_inactive_south_rows(plan,city_bounds,city_rows,maximum_row):
    """Remove complete unmodified border cells without recomputing retained heights."""
    if (not isinstance(maximum_row,int) or maximum_row%2
            or not plan['rowRange'][0]<maximum_row<plan['rowRange'][1]):
        raise ValueError('Inactive border trim must end on an interior two-profile row')
    native=NativeXYGrid(plan['bounds']);north=city_bounds[3]
    raw_y=north-maximum_row*(north-city_bounds[1])/(city_rows-1)
    cut_y=native.decode(native.encode(Point(plan['bounds'][0],raw_y))).y
    points=np.asarray(plan['points']);faces=np.asarray(plan['triangles']);ys=points[faces,1]
    if np.any((ys.min(axis=1)<cut_y)&(ys.max(axis=1)>cut_y)):
        raise ValueError('Border trim crosses an existing triangle')
    keep=ys.min(axis=1)>=cut_y;used=sorted(set(faces[keep].ravel().tolist()))
    removed=set(range(len(points)))-set(used)
    boundary=[i for i in used if points[i,1]==cut_y]
    if not boundary or any(plan['weights'][i]!=0 for i in removed|set(boundary)):
        raise ValueError('Cannot trim modified terrain or make an active-height seam')
    remap={old:new for new,old in enumerate(used)}
    record={'originalBounds':plan['bounds'][:],'originalRowRange':plan['rowRange'][:],
            'removedTriangles':int((~keep).sum()),'removedPoints':len(removed),
            'boundaryPoints':len(boundary),'removedAndBoundaryWeightsAreZero':True}
    plan['triangles']=[[remap[i] for i in face] for face,k in zip(plan['triangles'],keep) if k]
    plan['materials']=[m for m,k in zip(plan['materials'],keep) if k]
    for key in ['points','weights','targetMeters','rawSourceMeters']:plan[key]=[plan[key][i] for i in used]
    plan['bounds'][1]=raw_y;plan['rowRange'][1]=maximum_row
    land=native.encode(shape(plan['landGeometry'])).intersection(native.encode(box(*plan['bounds'])))
    plan['landGeometry']=mapping(native.decode(land));plan['inactiveBorderTrim']=record
    plan['statistics'].update(points=len(used),triangles=len(plan['triangles']),
                              patchAreaSquareMeters=native.decode(native.encode(box(*plan['bounds']))).area*10000,
                              landAreaSquareMeters=native.decode(land).area*10000)
    return plan


def inactive_base_cells(plan,geo,cols,rows,existing=()):
    """Find whole native cells whose dense land can return to both base profiles.

    Source water, even unselected water, is protected. Tests use the preparation
    lattice, so a cell that would split any retained triangle is never selected.
    """
    native=NativeXYGrid(plan['bounds']);w,s,e,n=geo['bounds']
    dx=(e-w)/(cols-1);dy=(n-s)/(rows-1)
    # Vertices are already native. Re-running polygon snap-rounding can erase
    # a narrow, valid triangle whose integer vertices are almost collinear.
    lattice=np.asarray(plan['points'])/np.asarray(native.steps)
    faces=[Polygon(lattice[face]) for face in plan['triangles']]
    tree=STRtree(faces)
    vertices=[native.encode(Point(p)) for p in plan['points']];vertex_tree=STRtree(vertices)
    waters=STRtree([native.encode(Polygon(r[0],r[1:])) for r in geo['water']])
    land=native.encode(shape(plan['landGeometry']))
    active=[any(plan['weights'][i]!=0 for i in face) or material!='reservoir_ground'
            for face,material in zip(plan['triangles'],plan['materials'])]
    cells=[];removed=set()
    for j in range(*plan['rowRange'],2):
        for i in range(*plan['columnRange'],2):
            if any(v['columnRange'][0]<=i<v['columnRange'][1] and v['rowRange'][0]<=j<v['rowRange'][1] for v in existing):continue
            cell=native.encode(box(w+i*dx,n-(j+2)*dy,w+(i+2)*dx,n-j*dy))
            if not land.covers(cell) or len(waters.query(cell,predicate='intersects')):continue
            # Integer endpoints can still produce fractional intersections.
            # Rounding those again would hide tiny faces crossing a cell edge.
            ids=[int(k) for k in tree.query(cell,predicate='intersects') if faces[k].intersection(cell,grid_size=0).area]
            if len(ids)<=8 or any(active[k] or not cell.covers(faces[k]) for k in ids):continue
            # Touching vertices also form the new seam, even where the adjacent
            # triangle has no positive-area intersection with this cell.
            if any(plan['weights'][int(k)]!=0 for k in vertex_tree.query(cell,predicate='intersects')):continue
            cells.append((i,j));removed.update(ids)
    # Merge horizontal runs and then identical runs in consecutive rows. This
    # keeps runtime ownership checks small without expanding the selected set.
    rectangles=[];previous={}
    for j in sorted({j for i,j in cells}):
        columns=sorted(i for i,row in cells if row==j);runs=[]
        for i in columns:
            if runs and runs[-1][1]==i:runs[-1][1]=i+2
            else:runs.append([i,i+2])
        current={}
        for run in runs:
            key=tuple(run);old=previous.get(key)
            if old is not None and old['rowRange'][1]==j:old['rowRange'][1]=j+2;current[key]=old
            else:
                item={'columnRange':run,'rowRange':[j,j+2]};rectangles.append(item);current[key]=item
        previous=current
    return rectangles,{'cells':len(cells),'denseTriangles':len(removed),
                       'detailBaseTriangles':len(cells)*8,'smoothBaseTriangles':len(cells)*2,
                       'selection':'whole native cells; zero weights; all source water protected'}


def exclude_inactive_cells(plan,geo_bounds,cols,rows,exclusions):
    """Reserve prior patches using complete, unmodified two-profile grid cells."""
    native=NativeXYGrid(plan['bounds']);w,s,e,n=geo_bounds;dx=(e-w)/(cols-1);dy=(n-s)/(rows-1)
    rectangles=[]
    for item in exclusions:
        ir,jr=item['columnRange'],item['rowRange']
        if (len(ir)!=2 or len(jr)!=2 or any(type(v) is not int or v%2 for v in ir+jr)
                or not 0<=ir[0]<ir[1]<cols or not 0<=jr[0]<jr[1]<rows):raise ValueError('Cell exclusion must align with both profiles')
        rectangles.append(native.encode(box(w+ir[0]*dx,n-jr[1]*dy,w+ir[1]*dx,n-jr[0]*dy)))
    excluded=unary_union(rectangles);domain=native.encode(box(*plan['bounds'])).difference(excluded)
    points=np.asarray(plan['points']);faces=np.asarray(plan['triangles']);keep=[]
    lattice=points/np.asarray(native.steps)
    for face in faces:
        triangle=Polygon(lattice[face]);cut=triangle.intersection(excluded,grid_size=0)
        if cut.area and cut.area!=triangle.area:raise ValueError('Cell exclusion crosses a prepared face')
        keep.append(cut.area==0)
    keep=np.asarray(keep);used=sorted(set(faces[keep].ravel().tolist()));removed=set(range(len(points)))-set(used)
    boundary=[i for i in used if excluded.boundary.distance(native.encode(Point(points[i])))<.1]
    if any(plan['weights'][i]!=0 for i in removed|set(boundary)):
        raise ValueError('Cannot exclude modified reservoir cells or make an active seam')
    if any(m!='reservoir_ground' for m,k in zip(plan['materials'],keep) if not k):raise ValueError('Cannot exclude mapped dam faces')
    remap={old:new for new,old in enumerate(used)}
    plan['triangles']=[[remap[i] for i in face] for face,k in zip(plan['triangles'],keep) if k]
    plan['materials']=[m for m,k in zip(plan['materials'],keep) if k]
    for key in ['points','weights','targetMeters','rawSourceMeters']:plan[key]=[plan[key][i] for i in used]
    # The prepared shore is already on the native lattice. A second fixed-
    # precision overlay can snap close shoreline edges together even far from
    # the excluded cells. Clip in decoded coordinates to preserve those edges.
    land=shape(plan['landGeometry']).difference(native.decode(excluded));plan['landGeometry']=mapping(land)
    plan['cellExclusions']=exclusions
    plan['replacementBoundarySegments']=[[[float(x),float(y)] for x,y in (a,b)]
        for p in polygons(native.decode(domain)) for ring in [p.exterior,*p.interiors] for a,b in zip(ring.coords,list(ring.coords)[1:])]
    plan['inactiveCellExclusionReport']={'removedTriangles':int((~keep).sum()),'removedPoints':len(removed),'newBoundaryPoints':len(boundary),'removedAndBoundaryWeightsAreZero':True}
    plan['statistics'].update(points=len(used),triangles=len(plan['triangles']),patchAreaSquareMeters=native.decode(domain).area*10000,landAreaSquareMeters=land.area*10000)
    return plan


def dam_boundary_vertices(triangles, materials):
    """Return the actual noded dam perimeter, excluding internal crest seams."""
    edges = {}
    for face, material in zip(triangles, materials):
        if material not in ('dam_slope', 'dam_crest'):
            continue
        for a, b in zip(face, face[1:]+face[:1]):
            key = tuple(sorted((a, b)))
            edges[key] = edges.get(key, 0)+1
    if any(count > 2 for count in edges.values()):
        raise ValueError('Non-manifold dam surface')
    return {i for edge, count in edges.items() if count == 1 for i in edge}


def prepare(geo, dem, source, raster_path):
    if geo['center'] != source['center'] or source['metersPerUnit'] != 100:
        raise ValueError('Reservoir/city coordinate mismatch')
    config = source['mesh']; lakes = []
    if not 0<=config['nativeFullRestoreMeters']<config['nativeRestoreMeters']:
        raise ValueError('Reservoir restore band must have a positive transition width')
    for entry in source['waterBodies']:
        rings = geo['water'][entry['geographyWaterIndex']]
        if digest(rings) != entry['expectedPolygonSha256']:
            raise ValueError('Reconcile reservoir source after shoreline changes')
        lakes.append((entry, Polygon(rings[0], rings[1:])))
    lakes=connect_water_fields(lakes,source.get('connectedWaterGroups',[]))
    buildings = {b['id']: b for b in geo['buildings']}
    water = unary_union([Polygon(r[0], r[1:]) for r in geo['water']])
    dams = []
    for entry in source['dams']:
        b = buildings[entry['id']]
        if b.get('use') != 'dam' or b['sourceRef'] != entry['sourceRef'] or digest(b['rings']) != entry['expectedFootprintSha256']:
            raise ValueError('Reconcile mapped dam identity/footprint')
        if entry['isEngineeringDesign'] is not False:
            raise ValueError('This generator only implements explicitly estimated embankments')
        footprint = Polygon(b['rings'][0], b['rings'][1:])
        if footprint.intersection(water).area*10000>1e-6:
            raise ValueError('Mapped overwater dam needs a dedicated structure, not an embankment surface')
        crest = crest_polygon(footprint, entry['crestWidthMeters'], entry['crestEndInsetMeters'],
                              entry.get('crestEndInsetMode', 'footprint'))
        lake_level = next(level for level, _ in lakes if level['geographyWaterIndex'] == entry['waterIndex'])
        dams.append((entry, footprint, crest, lake_level['levelMeters']+entry['crestMinimumAboveWaterMeters']))
    focus = unary_union([p for _, p in lakes]+[p for _, p, _, _ in dams])
    w, s, e, n = geo['bounds'];dx=(e-w)/(dem['cols']-1);dy=(n-s)/(dem['rows']-1)
    ir,jr,clipped_to_city=replacement_ranges(geo['bounds'],dem['cols'],dem['rows'],focus,
                                            config['patchMarginMeters'],config.get('clipPatchToCityBounds',False))
    # Crossing a float32 power-of-two boundary changes the XY lattice step.
    # Expand by whole two-profile cells until every outer corner belongs to the
    # common lattice; never move a seam off the original city grid.
    for _ in range(32):
        bounds=[w+ir[0]*dx,n-jr[1]*dy,w+ir[1]*dx,n-jr[0]*dy]
        steps=[float(np.spacing(np.float32(max(abs(bounds[k]),abs(bounds[k+2]))))) for k in [0,1]]
        bad=[k for k,v in enumerate(np.asarray(bounds,dtype=np.float32)) if float(v)/steps[k%2]!=round(float(v)/steps[k%2])]
        if not bad:break
        if 0 in bad:ir[0]-=2
        if 1 in bad:jr[1]+=2
        if 2 in bad:ir[1]+=2
        if 3 in bad:jr[0]-=2
    else:raise ValueError('Cannot align reservoir boundary to the common float32 lattice')
    if ir[0]<0 or jr[0]<0 or ir[1]>=dem['cols'] or jr[1]>=dem['rows']:
        raise ValueError('Lattice-aligned reservoir replacement exceeds city grid')
    open_sides=restoration_boundary_sides(bounds,geo['bounds'],config.get('restoreAtCityBoundary',False))
    native=NativeXYGrid(bounds);qpatch=native.encode(box(*bounds));qwater=native.encode(water)
    land=qpatch.difference(qwater)
    banks=protected_banks(geo,lakes,native,qpatch,config)
    qdams=[(entry,native.encode(p),native.encode(crest),level) for entry,p,crest,level in dams]
    linework=[land.boundary]
    linework.extend(protected_bank_lines(banks,native,land,geo['bounds'],dem['cols'],dem['rows']))
    sub=config['subdivisions'];sx,sy=dx/sub,dy/sub
    cols,rows=(ir[1]-ir[0])*sub,(jr[1]-jr[0])*sub
    # One noded arrangement for grid, water, dam footprint and crest boundaries.
    # This keeps a single shared vertex at every zone/cell intersection.
    for i in range(1,cols):
        x=bounds[0]+i*sx
        linework.append(native.encode(LineString([(x,bounds[1]),(x,bounds[3])])).intersection(land))
    for j in range(1,rows):
        y=bounds[1]+j*sy
        linework.append(native.encode(LineString([(bounds[0],y),(bounds[2],y)])).intersection(land))
    for entry,footprint,crest,_ in qdams:
        linework.extend([footprint.boundary,crest.boundary])
        detail=native.encode(native.decode(footprint).buffer(.15)).intersection(land)
        a,b,c,d=native.decode(detail).bounds;step=config['damGridMeters']/100
        for x in np.arange(math.floor(a/step)*step,c+step,step):
            linework.append(native.encode(LineString([(x,b),(x,d)])).intersection(detail))
        for y in np.arange(math.floor(b/step)*step,d+step,step):
            linework.append(native.encode(LineString([(a,y),(c,y)])).intersection(detail))
    # Node the varying water grid into land boundaries as well. Both sides
    # must retain identical shoreline stations when water heights vary.
    for entry,polygon in lakes:
        if entry.get('levelRegions'):linework.extend(water_mesh_lines(entry,polygon,native))
    network=union_all(linework,grid_size=1)
    cells=list(polygonize(network))
    pieces=[p for p in cells if land.covers(p.representative_point())]
    pieces.sort(key=lambda p:(p.bounds,p.area,p.wkb))
    points=[];lookup={};triangles=[];materials=[]
    def vertex(point):
        key=tuple(map(float,point))
        if key not in lookup:lookup[key]=len(points);points.append(list(key))
        return lookup[key]
    for polygon in pieces:
        p=polygon.representative_point();material='reservoir_ground'
        for _,footprint,crest,_ in qdams:
            if crest.covers(p):material='dam_crest';break
            if footprint.covers(p):material='dam_slope';break
        poly=native.decode(polygon)
        rings=[list(r.coords)[:-1] for r in [poly.exterior,*poly.interiors]]
        coordinates=np.asarray([p for ring in rings for p in ring]);ends=np.cumsum([len(r) for r in rings],dtype=np.uint32)
        for face in triangulate_stations(coordinates,ends):
            ids=[vertex(coordinates[k]) for k in face]
            a,b,c=[points[i] for i in ids]
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if area==0:continue
            if area<0:ids.reverse()
            triangles.append(ids);materials.append(material)
    xy=np.asarray(points);cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy))
    lon=cx+xy[:,0]/kx;lat=cy+xy[:,1]/1113.2
    with rasterio.open(raster_path) as raster:
        window=from_bounds(lon.min()-.004,lat.min()-.004,lon.max()+.004,lat.max()+.004,raster.transform).round_offsets().round_lengths()
        grid=raster.read(1,window=window,masked=True).astype(float).filled(np.nan);transform=raster.window_transform(window)
        indices=[(lat-transform.f)/transform.e-.5,(lon-transform.c)/transform.a-.5]
        raw=map_coordinates(grid,indices,order=1,mode='constant',cval=np.nan)
        native_z=map_coordinates(gaussian_filter(grid,config['nativeGaussianSigmaPixels']),indices,order=1,mode='constant',cval=np.nan)
    if not np.isfinite(raw).all() or not np.isfinite(native_z).all():
        raise ValueError('Missing source raster elevations')
    qlake_shapes=[native.decode(native.encode(p)) for _,p in lakes]
    water_fields=[WaterLevelField(entry) for entry,_ in lakes]
    target=[];weights=[];protection=protection_weights(points,banks)
    dam_perimeter=dam_boundary_vertices(triangles,materials)
    for point_index,(point,z,protected_weight) in enumerate(zip(points,native_z,protection)):
        p=Point(point);distances=[p.distance(shape) for shape in qlake_shapes]
        edge=restoration_edge_distance(point,bounds,open_sides)
        restore=smooth(max(0,min(distances)*100-config['nativeFullRestoreMeters'])/
                       (config['nativeRestoreMeters']-config['nativeFullRestoreMeters']))
        weight=float(smooth(edge/config['edgeBlendMeters'])*(1-restore)*protected_weight)
        strengths=[float(1-smooth(distance*100/config['shoreBlendMeters'])) for distance in distances]
        contributors=[]
        for strength,distance,field,polygon in zip(strengths,distances,water_fields,qlake_shapes):
            if strength<=0:continue
            contributors.append((strength/max(distance,1e-8)**2,nearest_shore_level(field,polygon,p)+config['bankAboveWaterMeters']))
        if contributors:
            shore=sum(q*level for q,level in contributors)/sum(q for q,_ in contributors)
            blend=max(strengths);z=z*(1-blend)+shore*blend
        for entry,footprint,crest,minimum in qdams:
            # Noding on the native lattice can put a perimeter station slightly
            # inside the source polygon. Its geometric distance then leaks a
            # crest-dependent lift into adjoining non-dam triangles. The actual
            # shared perimeter must retain the underlying shoreline/ground target.
            if point_index in dam_perimeter:continue
            qp=native.encode(p)
            if not footprint.covers(qp):continue
            foot=native.decode(footprint);top=native.decode(crest)
            outer=p.distance(foot.boundary);inner=p.distance(top)
            blend=1.0 if inner<1e-8 else float(smooth(outer/max(outer+inner,1e-8)))
            z=z+(max(z,minimum)-z)*blend
            # Keep the same continuous restoration weight on both sides of a
            # mapped dam boundary; a per-building weight override makes cliffs.
        target.append(float(z));weights.append(weight)
    result={'id':source['id'],'status':'independent reservoir surface candidate; city activation pending',
            'center':geo['center'],'bounds':bounds,'columnRange':ir,'rowRange':jr,'clippedToCityBoundary':clipped_to_city,
            'restoredCityBoundarySides':open_sides,
            'nativeXYGridSceneUnits':native.steps,'points':points,'triangles':triangles,'materials':materials,
            'targetMeters':target,'weights':weights,'rawSourceMeters':raw.tolist(),
            'waterBodies':[{**entry,'rings':geo['water'][entry['geographyWaterIndex']],
                            **({'waterMesh':prepare_water_mesh(entry,polygon,native,network,cells)} if entry.get('levelRegions') else {})}
                           for entry,polygon in lakes],
            'dams':[{**entry,'footprint':mapping(native.decode(footprint)), 'crest':mapping(native.decode(crest)),
                     'minimumCrestMeters':minimum} for entry,footprint,crest,minimum in qdams],
            'landGeometry':mapping(native.decode(land)),'source':source,
            'protectedWaterBanks':[entry for entry,polygon in banks],
            'statistics':{'points':len(points),'triangles':len(triangles),'patchAreaSquareMeters':native.decode(qpatch).area*10000,
                          'landAreaSquareMeters':native.decode(land).area*10000,
                          'damCrestTriangles':materials.count('dam_crest'),'damSlopeTriangles':materials.count('dam_slope')}}
    if 'inactiveBorderRowMaximum' in config:
        result=trim_inactive_south_rows(result,geo['bounds'],dem['rows'],config['inactiveBorderRowMaximum'])
    exclusions=list(config.get('inactiveCellExclusions',[]))
    if config.get('preserveInactiveBaseCells',False):
        automatic,report=inactive_base_cells(result,geo,dem['cols'],dem['rows'],exclusions)
        exclusions+=automatic;result['inactiveBaseCellReport']=report
    if exclusions:
        result=exclude_inactive_cells(result,geo['bounds'],dem['cols'],dem['rows'],exclusions)
    result['waterInterfaceAudit']=audit_interfaces(result,geo)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['geography','terrain','source','raster','output']:
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--runtime-root',type=Path,help='Bind activation to the actual city geography and terrain under this root')
    args=parser.parse_args();geo,dem,source=[json.loads(getattr(args,key).read_text()) for key in ['geography','terrain','source']]
    if sha(args.raster)!=dem['sourceSha256'] or sha(args.raster)!=source['sourceReferences']['rasterSha256']:
        raise ValueError('Reservoir raster provenance mismatch')
    result=prepare(geo,dem,source,args.raster)
    result['inputs']={key:{'path':str(getattr(args,key).resolve()),'sha256':sha(getattr(args,key))} for key in ['geography','terrain','source','raster']}
    if args.runtime_root is not None:
        root=args.runtime_root.resolve()
        for key in ['geography','terrain']:
            if getattr(args,key).resolve()!=root/'public/data'/ (key+'.json'):
                raise ValueError('Prepare from the active runtime '+key)
        result['runtimeInputs']={str(getattr(args,key).resolve().relative_to(root)):sha(getattr(args,key)) for key in ['geography','terrain','source']}
    result['tools']={str(Path(__file__).with_name(name).resolve()):sha(Path(__file__).with_name(name))
                     for name in ['prepare_reservoir_terrain.py','prepare_block_grading.py','prepare_waterfront.py','prepare_building_shorelines.py','reservoir_interfaces.py','reservoir_connections.py']}
    helper=Path(__file__).resolve().parents[1]/'blender/reservoir_water.py';result['tools'][str(helper)]=sha(helper)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(result['statistics']),flush=True)


if __name__=='__main__':main()
