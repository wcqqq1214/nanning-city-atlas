"""Prepare source-sampled mountain relief and mapped park paths, without editing DEM arrays."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import mapbox_earcut
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, Point, LineString, box
from shapely import contains_xy
from shapely.ops import unary_union
from prepare_forest_canopy import woodland_geometry, polygons

ROOT = Path(__file__).resolve().parents[1]


def rings(shape):
    return [[[round(x,7),round(y,7)] for x,y in r.coords] for r in [shape.exterior,*shape.interiors]]


def smooth(t):
    t=max(0,min(1,t));return t*t*(3-2*t)


def prepare(output=None):
    load=lambda p:json.loads((ROOT/p).read_text())
    source=load('data/qingxiu-terrain-source.json');paths_source=load('data/qingxiu-paths-source.json')
    water_sources={r['geographyWaterIndex']:r for r in load('data/qingxiu-water-source.json')['matches']}
    geo=load('public/data/geography.json');dem=load('public/data/terrain.json')
    cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy))
    xy=lambda lon,lat:((lon-cx)*kx,(lat-cy)*1113.2)
    west,south,east,north=geo['bounds'];dx=(east-west)/(dem['cols']-1);dy=(north-south)/(dem['rows']-1)
    a,b,c,d=source['requestedBoundsSceneXY']
    ir=[math.floor((a-west)/dx/2)*2,math.ceil((c-west)/dx/2)*2]
    jr=[math.floor((north-d)/dy/2)*2,math.ceil((north-b)/dy/2)*2]
    bounds=[west+ir[0]*dx,north-jr[1]*dy,west+ir[1]*dx,north-jr[0]*dy]
    patch=box(*bounds);water=unary_union([Polygon(r[0],r[1:]) for r in geo['water']])
    land=patch.difference(water)
    feature=next(e for e in load('data/forest-source.json')['elements'] if e['type']=='relation' and e['id']==11922560)
    woods=woodland_geometry(feature,xy,patch)
    tower=next(p for p in load('data/landmarks.json') if p['id']=='qingxiu')
    center=xy(tower['lon'],tower['lat']);platform=Point(center).buffer(source['tower']['platformRadiusMeters']/100,resolution=8)
    structures=[Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings'] if Polygon(b['rings'][0]).intersects(patch)]
    structures+=[Polygon([xy(p['lon'],p['lat']) for p in e['geometry']]) for e in paths_source['elements'] if e.get('tags',{}).get('building')]
    buildings=unary_union(structures).buffer(.003,join_style=2)
    existing=unary_union([LineString(r['points']).buffer((.16 if r['class'] in ['primary','trunk','motorway'] else .105 if r['class']=='secondary' else .07 if r['class']=='tertiary' else .05)/2,cap_style=2,join_style=2)
                         for r in geo['roads'] if not r['bridge'] and LineString(r['points']).intersects(patch)])
    used=Polygon();path_records=[];path_areas={k:[] for k in ['steps','walk','service']}
    for e in paths_source['elements']:
        tags=e.get('tags',{});kind=tags.get('highway')
        if kind not in source['pathWidthMeters'] or tags.get('bridge','no')!='no' or tags.get('tunnel','no')!='no':continue
        line=LineString([xy(p['lon'],p['lat']) for p in e['geometry']])
        line=line.intersection(patch).intersection(woods.buffer(.5)).difference(water)
        if line.is_empty:continue
        width=source['pathWidthMeters'][kind];width_source='estimate'
        try:
            measured=float(tags.get('width','').removesuffix(' m'))
            if .8<=measured<=12:width=measured;width_source='OSM width'
        except ValueError:pass
        area=line.buffer(width/200,cap_style=2,join_style=2).intersection(land).difference(buildings).difference(existing)
        if area.area<1e-8:continue
        key='steps' if kind=='steps' else 'service' if kind in ['service','track'] else 'walk'
        path_areas[key].append(area)
        path_records.append({'osmId':e['id'],'tags':tags,'widthMeters':width,'widthSource':width_source,
                             'lengthMeters':round(line.length*100,3),'footprint':[rings(p) for p in polygons(area)]})
    zones=[]
    for key in ['steps','walk','service']:
        area=unary_union(path_areas[key]).difference(used);used=used.union(area);zones.append((key,area))
    zones.append(('platform',platform.intersection(land).difference(used)));used=used.union(platform)
    zones.extend([('forest',woods.intersection(land).difference(used)),('ground',land.difference(woods).difference(used))])
    div=source['gridSubdivisions'];cols=(ir[1]-ir[0])*div;rows=(jr[1]-jr[0])*div;sx=dx/div;sy=dy/div
    points=[];lookup={};triangles=[];materials=[];cells={}
    def vertex(p):
        key=tuple(round(float(v),7) for v in p)
        if key not in lookup:lookup[key]=len(points);points.append(list(key))
        return lookup[key]
    for j in range(rows):
        for i in range(cols):
            x0,y0=bounds[0]+i*sx,bounds[1]+j*sy;x1,y1=x0+sx,y0+sy;cell=[]
            for half in [Polygon([(x0,y0),(x1,y0),(x0,y1)]),Polygon([(x1,y0),(x1,y1),(x0,y1)])]:
                for key,area in zones:
                    for shape in polygons(area.intersection(half)):
                        if shape.area<1e-11:continue
                        rr=[list(r.coords)[:-1] for r in [shape.exterior,*shape.interiors]]
                        coords=np.asarray([p for ring in rr for p in ring]);ends=np.cumsum([len(r) for r in rr],dtype=np.uint32)
                        for face in mapbox_earcut.triangulate_float64(coords,ends).reshape(-1,3):
                            ids=[vertex(coords[k]) for k in face]
                            if Polygon([points[k] for k in ids]).area<1e-11:continue
                            cell.append(len(triangles));triangles.append(ids);materials.append(key)
            if cell:cells[f'{i},{j}']=cell
    # Earcut may omit a collinear boundary vertex on only one side of an edge.
    # Insert every such shared vertex before assigning nonlinear raster heights;
    # otherwise a flat XY T-junction becomes a vertical crack on the hillside.
    tree=cKDTree(points);edge_cache={};xy_points=np.asarray(points)
    def edge_points(a,b):
        key=tuple(sorted((a,b)))
        if key not in edge_cache:
            u,v=xy_points[list(key)];direction=v-u;length=np.linalg.norm(direction)
            candidates=tree.query_ball_point((u+v)/2,length/2+2e-7)
            points_on=[]
            for k in candidates:
                t=float(np.dot(xy_points[k]-u,direction)/(length*length))
                if 2e-7/length<t<1-2e-7/length and np.linalg.norm(xy_points[k]-u-t*direction)<2e-7:points_on.append((t,k))
            edge_cache[key]=[k for t,k in sorted(points_on)]
        return edge_cache[key] if a<b else list(reversed(edge_cache[key]))
    conformed=[];conformed_materials=[];mapping={};split_faces=0
    for index,(ids,material) in enumerate(zip(triangles,materials)):
        boundary=[]
        for a,b in zip(ids,ids[1:]+ids[:1]):boundary.extend([a,*edge_points(a,b)])
        mapping[index]=[]
        if len(boundary)>3:
            split_faces+=1;center_id=vertex(np.mean([points[k] for k in ids],axis=0))
            pieces=[[a,b,center_id] for a,b in zip(boundary,boundary[1:]+boundary[:1])]
        else:pieces=[ids]
        for face in pieces:
            if Polygon([points[k] for k in face]).area<1e-12:continue
            mapping[index].append(len(conformed));conformed.append(face);conformed_materials.append(material)
    triangles,materials=conformed,conformed_materials
    cells={key:[new for old in ids for new in mapping[old]] for key,ids in cells.items()}
    # Sub-0.1 mm slivers are numerical overlay artefacts, not resolved ridges.
    # Their middle vertex must stay on the shared 3D edge instead of acquiring
    # an independent nonlinear height and becoming a thin vertical spike.
    constraints={}
    for ids in triangles:
        a,b=max([(ids[0],ids[1]),(ids[1],ids[2]),(ids[2],ids[0])],key=lambda edge:math.dist(points[edge[0]],points[edge[1]]))
        c=next(i for i in ids if i not in [a,b]);u,v,q=np.asarray([points[a],points[b],points[c]])
        direction=v-u;length=np.linalg.norm(direction);t=float(np.dot(q-u,direction)/(length*length))
        if 0<t<1 and np.linalg.norm(q-u-t*direction)<1e-6 and length>constraints.get(c,[-1])[0]:
            constraints[c]=[float(length),a,b,t]
    # Sample the original attributed raster independently of the coarse display DEM.
    tile=ROOT/'work/geodata'/Path(dem['sourceUrl']).name
    assert hashlib.sha256(tile.read_bytes()).hexdigest()==dem['sourceSha256'],'Source raster changed'
    samples=np.asarray(points+[list(center)]);lon=cx+samples[:,0]/kx;lat=cy+samples[:,1]/1113.2
    with rasterio.open(tile) as raster:
        window=from_bounds(lon.min()-.004,lat.min()-.004,lon.max()+.004,lat.max()+.004,raster.transform).round_offsets().round_lengths()
        grid=raster.read(1,window=window).astype(float);transform=raster.window_transform(window)
        xx=(lon-transform.c)/transform.a-.5;yy=(lat-transform.f)/transform.e-.5
        raw=map_coordinates(grid,[yy,xx],order=1,mode='nearest')
        native=map_coordinates(gaussian_filter(grid,source['nativeGaussianSigmaPixels'],mode='nearest'),[yy,xx],order=1,mode='nearest')
    native=np.maximum(native,dem['conditioning']['landFloorMeters']);target_level=float(native[-1])
    # Elevated mountain lakes cannot share the river's citywide water datum.
    # Infer their own display levels from the same retained raw source raster.
    gx,gy=np.meshgrid(np.arange(grid.shape[1]),np.arange(grid.shape[0]))
    glon=transform.c+(gx+.5)*transform.a;glat=transform.f+(gy+.5)*transform.e
    scene_x=(glon-cx)*kx;scene_y=(glat-cy)*1113.2
    lakes=[];lake_shapes=[];water_source=source['mountainWater']
    for index,rings_ in enumerate(geo['water']):
        shape=Polygon(rings_[0],rings_[1:])
        if not patch.contains(shape.buffer(water_source['nativeRestoreMeters']/100)) or shape.area>10:continue
        values=grid[contains_xy(shape,scene_x,scene_y)]
        if len(values)>=3:level=float(np.median(values));method='median of raw raster pixels inside polygon'
        else:
            p=shape.representative_point();lon=cx+p.x/kx;lat=cy+p.y/1113.2
            level=float(map_coordinates(grid,[[(lat-transform.f)/transform.e-.5],[(lon-transform.c)/transform.a-.5]],order=1)[0])
            method='bilinear source at interior point; lake smaller than three source pixels'
        if level<dem['verticalDatumMeters']+water_source['minimumAboveRiverDatumMeters']:continue
        provenance=water_sources[index]
        assert hashlib.sha256(json.dumps(rings_,separators=(',',':')).encode()).hexdigest()==provenance['polygonSha256'],'Reconcile local water provenance after changing its geographic boundary'
        feature=provenance['feature']
        lakes.append({'geographyWaterIndex':index,'rings':rings(shape),'levelMeters':round(level,6),'rawPixelCount':len(values),'method':method,'source':'GLO-30 inferred display level',
                      'osmType':feature['type'],'osmId':feature['id'],'name':feature['tags'].get('name'),'osmTags':feature['tags']})
        lake_shapes.append(shape)
    weights=[];levels=[];platform_weights=[]
    for (x,y),z in zip(points,native[:-1]):
        p=Point(x,y);edge=smooth(min(x-bounds[0],bounds[2]-x,y-bounds[1],bounds[3]-y)/(source['edgeBlendMeters']/100))
        forest=smooth(p.distance(woods.boundary)/(source['forestBlendMeters']/100)) if woods.covers(p) else 0
        weight=edge*forest
        shores=[]
        for shape,lake in zip(lake_shapes,lakes):
            distance=p.distance(shape);strength=1-smooth(distance/(water_source['shoreBlendMeters']/100))
            restore=1-smooth(max(0,distance-water_source['shoreBlendMeters']/100)/((water_source['nativeRestoreMeters']-water_source['shoreBlendMeters'])/100))
            weight=max(weight,edge*restore)
            if strength>0:shores.append((strength,strength/max(distance,.00001)**2,lake['levelMeters']+water_source['bankAboveWaterMeters']))
        if shores:
            strength=max(t[0] for t in shores);bank=sum(t[1]*t[2] for t in shores)/sum(t[1] for t in shores)
            z=z*(1-strength)+bank*strength;weight=max(weight,edge*strength)
        apron=1-smooth(max(0,p.distance(Point(center))-source['tower']['platformRadiusMeters']/100)/(source['tower']['platformBlendMeters']/100))
        weights.append(round(max(weight,apron),9));platform_weights.append(round(apron,9))
        levels.append(round(float(z*(1-apron)+target_level*apron),6))
    inputs=['data/qingxiu-terrain-source.json','data/qingxiu-paths-source.json','data/qingxiu-water-source.json','data/forest-source.json',
            'data/landmarks.json','public/data/geography.json','public/data/terrain.json']
    plan={'id':source['id'],'bounds':bounds,'columnRange':ir,'rowRange':jr,
          'grid':{'columns':cols,'rows':rows,'dx':sx,'dy':sy},'points':points,'triangles':triangles,'materials':materials,'cells':cells,
          'linearHeightConstraints':[[c,*value[1:]] for c,value in sorted(constraints.items())],
          'rawSourceMeters':np.round(raw[:-1],6).tolist(),'targetMeters':levels,'weights':weights,'platformWeights':platform_weights,
          'towerCenterSceneXY':center,'platformLevelMeters':target_level,'paths':path_records,
          'waterBodies':lakes,
          'pathFootprints':{k:[rings(p) for p in polygons(a)] for k,a in zones if k in ['steps','walk','service']},
          'sourceRasterSha256':dem['sourceSha256'],'sourceRasterUrl':dem['sourceUrl'],'sourceResolutionArcSeconds':1,
          'pathTimestamp':paths_source['timestamp'],'source':source,
          'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
          'statistics':{'landAreaKm2':round(land.area/100,4),'triangles':len(triangles),'vertices':len(points),'conformedFaces':split_faces,'pathWays':len(path_records),'mountainLakes':len(lakes),
                        'pathLengthKm':round(sum(p['lengthMeters'] for p in path_records)/1000,3),
                        'pathAreaM2':round(sum(a.area for k,a in zones if k in ['steps','walk','service'])*10000,2),
                        'rawRangeMeters':[round(float(raw.min()),3),round(float(raw.max()),3)]}}
    destination=Path(output) if output else ROOT/'data/qingxiu-terrain-plan.json'
    destination.write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps(plan['statistics']),flush=True)
    return plan


if __name__=='__main__':prepare()
