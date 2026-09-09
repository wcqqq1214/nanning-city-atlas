"""Prepare staged woodland coverage from the city's retained OSM snapshot.

Run with work/venv/bin/python. --stage qingxiu / nearby / all permits a
bounded rollout; both GLB profiles use the same selected woodland footprint.
"""
import argparse
import hashlib
import json
import math
import random
from functools import lru_cache
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
STAGES = ['qingxiu', 'nearby', 'all']


def forest_source(snapshot):
    """Retain woodland provenance whenever the city snapshot is prepared."""
    return {'osmTimestamp':snapshot['osm3s']['timestamp_osm_base'],
            'attribution':'© OpenStreetMap contributors, ODbL 1.0',
            'description':'Mapped natural=wood and landuse=forest features from the existing city snapshot; geometries are clipped during preparation.',
            'elements':[e for e in snapshot['elements'] if e.get('tags',{}).get('natural')=='wood'
                        or e.get('tags',{}).get('landuse')=='forest']}


def polygons(shape):
    if shape.geom_type == 'Polygon':
        yield shape
    elif hasattr(shape, 'geoms'):
        for child in shape.geoms:
            yield from polygons(child)


def rings(shape):
    return [[[round(x, 5), round(y, 5)] for x, y in ring.coords]
            for ring in [shape.exterior, *shape.interiors]]


def woodland_geometry(feature, xy, clip):
    """Retain closed ways, multipolygon holes and the current scene boundary."""
    if feature['type'] == 'way':
        coords = [xy(p['lon'], p['lat']) for p in feature.get('geometry', []) if p]
        if len(coords) < 4 or coords[0] != coords[-1]:
            raise ValueError(f'Incomplete woodland way {feature["id"]}')
        shape = make_valid(Polygon(coords))
    else:
        outer, inner = [], []
        for member in feature.get('members', []):
            coords = [xy(p['lon'], p['lat']) for p in member.get('geometry', []) if p]
            if len(coords) > 1:
                (inner if member.get('role') == 'inner' else outer).append(LineString(coords))
        shape = unary_union(list(polygonize(unary_union(outer))))
        shape = shape.difference(unary_union(list(polygonize(unary_union(inner)))))
        if shape.is_empty:
            raise ValueError(f'Incomplete woodland relation {feature["id"]}')
    return unary_union(list(polygons(make_valid(shape).intersection(clip))))


def prepare_region(region_id, woodland, exclusions, geo, dem, cluster_spacing, seed):
    allowed = woodland.difference(exclusions)
    # Tiny islands and narrow fragments retain their existing individual trees.
    allowed = unary_union([p for p in polygons(allowed) if p.area > .08])
    assert not allowed.is_empty, f'No usable woodland in {region_id}'
    core, edge = prep(allowed.buffer(-.55)), prep(woodland)
    replaced, edge_trees = [], []
    for index, tree in enumerate(geo['trees']):
        point = Point(tree[:2])
        if core.contains(point):
            replaced.append(index)
        elif edge.contains(point):
            edge_trees.append(index)

    boundary = allowed.boundary
    west, south, east, north = allowed.bounds
    cluster_rng = random.Random(seed+1)
    crown_clusters = []
    prepared = prep(allowed)
    for j in range(math.ceil((north-south)/cluster_spacing)):
        for i in range(math.ceil((east-west)/cluster_spacing)):
            x = west+(i+.5+.5*(j%2))*cluster_spacing+cluster_rng.uniform(-.3,.3)
            y = south+(j+.5)*cluster_spacing+cluster_rng.uniform(-.3,.3)
            radius = cluster_rng.uniform(.66,.86)
            if prepared.contains(Point(x,y).buffer(radius+.02)):
                crown_clusters.append([round(x,5),round(y,5),round(radius,4),
                                       round(cluster_rng.uniform(.78,.96),4),
                                       round(cluster_rng.uniform(0,math.tau),4),
                                       cluster_rng.choices([0,1,2],weights=[2,6,2])[0]])

    rng = random.Random(seed)
    spacing = 1.70
    sites = []
    for j in range(-2, math.ceil((north-south)/spacing)+3):
        for i in range(-2, math.ceil((east-west)/spacing)+3):
            sites.append((west+(i+.5*(j%2))*spacing+rng.uniform(-.24,.24)*spacing,
                          south+j*spacing*.87+rng.uniform(-.21,.21)*spacing,
                          rng.uniform(.58,.82),rng.choices([0,1,2],weights=[2,6,2])[0]))
    # Indexed nearest-crown queries keep large suburban regions practical to
    # regenerate, instead of scanning every crown for each terrain vertex.
    site_index = STRtree([Point(site[:2]) for site in sites])

    @lru_cache(maxsize=None)
    def crown(x, y):
        point = Point(x,y)
        near = sites[int(site_index.nearest(point))]
        distance = math.hypot(near[0]-x,near[1]-y)/spacing
        rise = .22+(near[2]-.22)*math.exp(-3.2*distance**4)
        blend = min(1,point.distance(boundary)/.40)
        return .10+(rise-.10)*blend,near[3]

    def canopy_mesh(step):
        points, triangles, colors, lookup = [], [], [], {}

        def add_triangle(surface):
            footprint = Polygon(surface)
            if not prepared.intersects(footprint):
                return
            color = crown(*footprint.centroid.coords[0])[1]
            for polygon in polygons(footprint.intersection(allowed)):
                if polygon.area < 1e-8:
                    continue
                ring_points = [list(r.coords)[:-1] for r in [polygon.exterior,*polygon.interiors]]
                coords = np.array([p for r in ring_points for p in r],dtype=np.float64)
                ends = np.cumsum([len(r) for r in ring_points],dtype=np.uint32)
                indices = mapbox_earcut.triangulate_float64(coords,ends).reshape(-1,3)
                local = []
                for x,y in coords:
                    point = (round(float(x),5),round(float(y),5),round(crown(x,y)[0],5))
                    key = point[:2]
                    if key not in lookup:
                        lookup[key] = len(points)
                        points.append(list(point))
                    local.append(lookup[key])
                for tri in indices:
                    ids = [local[int(i)] for i in tri]
                    if len(set(ids)) < 3:
                        continue
                    a,b,c = [points[i] for i in ids]
                    cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                    if abs(cross) < 1e-9:
                        continue
                    if cross < 0:
                        ids.reverse()
                    triangles.append(ids)
                    colors.append(color)

        # Every canopy face is supported by one displayed terrain triangle,
        # including the coarser mobile grid. Holes are never triangulated over.
        minx,miny,maxx,maxy = geo['bounds']
        dx,dy = (maxx-minx)/(dem['cols']-1),(maxy-miny)/(dem['rows']-1)
        first_i = max(0,math.floor((west-minx)/dx/step)*step)
        first_j = max(0,math.floor((maxy-north)/dy/step)*step)
        for j in range(first_j,min(dem['rows']-1,math.ceil((maxy-south)/dy)),step):
            for i in range(first_i,min(dem['cols']-1,math.ceil((east-minx)/dx)),step):
                ii,jj = min(i+step,dem['cols']-1),min(j+step,dem['rows']-1)
                v = [(minx+a*dx,maxy-b*dy) for a,b in [(i,j),(ii,j),(ii,jj),(i,jj)]]
                for tri in [(v[0],v[2],v[1]),(v[0],v[3],v[2])]:
                    add_triangle(tri)
        return {'points':points,'triangles':triangles,'colors':colors}

    plan = {'id':region_id,'areaKm2':round(allowed.area/100,4),
            'woodland':[rings(p) for p in polygons(woodland)],
            'coverage':[rings(p) for p in polygons(allowed)],
            'replacedTreeIndices':replaced,'edgeTreeIndices':edge_trees,
            'crownClusters':crown_clusters,'detail':canopy_mesh(1),'smooth':canopy_mesh(2)}
    print(f'{region_id}: {plan["areaKm2"]:.3f} km², {len(replaced)} interior trees replaced, '
          f'{len(crown_clusters)} crowns, '
          f'{len(plan["detail"]["triangles"])} / {len(plan["smooth"]["triangles"])} surface triangles.',flush=True)
    return plan


def prepare(stage='all'):
    source = json.loads((ROOT/'data/forest-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    dem = json.loads((ROOT/'public/data/terrain.json').read_text())
    places = json.loads((ROOT/'data/landmarks.json').read_text())
    assert source['osmTimestamp']==geo['osmTimestamp'], 'Prepare geography and woodland from the same OSM snapshot'
    kx = 1113.2*math.cos(math.radians(geo['center'][1]))

    def xy(lon,lat):
        return ((lon-geo['center'][0])*kx,(lat-geo['center'][1])*1113.2)

    clip = box(*geo['bounds'])
    grouped = {key:[] for key in STAGES}
    records = []
    for feature in source['elements']:
        tags = feature['tags']
        assert tags.get('natural')=='wood' or tags.get('landuse')=='forest'
        shape = woodland_geometry(feature,xy,clip)
        # Qingxiu is the original pilot. The large regional relation is rolled
        # out last; all smaller urban and suburban woodland comes beforehand.
        group = ('qingxiu' if feature['type']=='relation' and feature['id']==11922560 else
                 'all' if feature['type']=='relation' and feature['id']==9862173 else 'nearby')
        records.append({'type':feature['type'],'id':feature['id'],'name':tags.get('name'),
                        'classification':'natural=wood' if tags.get('natural')=='wood' else 'landuse=forest',
                        'stage':group,'mappedAreaKm2':round(shape.area/100,4)})
        if not shape.is_empty:
            grouped[group].append(shape)

    water = unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    buildings = unary_union([Polygon(b['rings'][0]) for b in geo['buildings']])
    roads = unary_union([LineString(r['points']).buffer(
        .19 if r['class'] in ['primary','trunk','motorway'] else
        .135 if r['class']=='secondary' else .10,
        cap_style=3,join_style=2) for r in geo['roads']])
    clearings = []
    for place in places:
        x,y = xy(place['lon'],place['lat'])
        if place.get('clearExtent'):
            w,h = place['clearExtent']
            clearings.append(box(x-w/2,y-h/2,x+w/2,y+h/2).buffer(.15))
        elif place['id']=='qingxiu':
            clearings.append(Point(x,y).buffer(.85))
    # The hand-modelled Nanhu park owns its own trees, terrain and paths.
    nanhu = json.loads((ROOT/'data/nanhu-plan.json').read_text())
    nx,ny = xy(*nanhu['center'])
    clearings.append(Polygon([(nx+u,ny+v) for u,v in nanhu['park']]).buffer(.15))
    # Roads and buildings are polygonal in the displayed city. Mitred buffers
    # retain clearance without adding dozens of arc vertices at every corner.
    exclusions = unary_union([water.buffer(.18,join_style=2),
                              buildings.buffer(.14,join_style=2),roads,*clearings])

    previous = Polygon()
    regions, rollout = [], []
    for order,key in enumerate(STAGES):
        shape = unary_union(grouped[key]).difference(previous)
        previous = previous.union(shape)
        enabled = order <= STAGES.index(stage)
        rollout.append({'stage':key,'enabled':enabled,'mappedAreaKm2':round(shape.area/100,4),
                        'sourceCount':sum(r['stage']==key and r['mappedAreaKm2']>0 for r in records)})
        if enabled:
            regions.append(prepare_region(key,shape,exclusions,geo,dem,
                           [1.95,4.8,8.0][order],[11922560,11922618,9862173][order]))
    inputs = ['public/data/geography.json','public/data/terrain.json','data/landmarks.json',
              'data/nanhu-plan.json','data/forest-source.json']
    plan = {'version':2,'stage':stage,'center':geo['center'],'bbox':geo['bbox'],
            'osmTimestamp':source['osmTimestamp'],'areaKm2':round(sum(r['areaKm2'] for r in regions),4),
            'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
            'sources':records,'rollout':rollout,'regions':regions}
    (ROOT/'data/forest-plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n')
    print(f'Total: {plan["areaKm2"]:.3f} km² canopy, stage {stage}.',flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=STAGES,default='all')
    prepare(parser.parse_args().stage)
