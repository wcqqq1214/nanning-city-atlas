"""Project, clip and connect the retained railway snapshot without inventing tracks."""
import hashlib
import json
import math
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]


def lines(shape):
    if shape.geom_type == 'LineString' and shape.length > 1e-7:
        yield shape
    elif hasattr(shape, 'geoms'):
        for child in shape.geoms:
            yield from lines(child)


def prepare():
    source = json.loads((ROOT/'data/railways-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    stations = json.loads((ROOT/'data/stations-plan.json').read_text())
    dem = json.loads((ROOT/'public/data/terrain.json').read_text())
    assert source['bbox'] == geo['bbox']
    kx = 1113.2*math.cos(math.radians(geo['center'][1]))
    def xy(lon, lat):
        return ((lon-geo['center'][0])*kx, (lat-geo['center'][1])*1113.2)
    clip = box(*geo['bounds'])
    sites = {}
    for identity, station in stations['stations'].items():
        sx, sy = xy(*station['center'])
        c, s = math.cos(station['angle']), math.sin(station['angle'])
        sites[identity] = Polygon([(sx+u*c-v*s, sy+u*s+v*c) for u,v in station['site']])
    paths, nodes, node_lookup = [], [], {}
    for element in source['elements']:
        source_nodes = {tuple(round(v, 7) for v in xy(p['lon'], p['lat'])): n
                        for n,p in zip(element['nodes'], element['geometry'])}
        tags = element.get('tags', {})
        assert tags.get('railway') == 'rail'
        raw = LineString([xy(p['lon'],p['lat']) for p in element['geometry']])
        for part, line in enumerate(lines(raw.intersection(clip))):
            # Preserve every original vertex. Extra samples follow the exact
            # source segments; planar crossings are never joined without a node.
            points = list(line.coords)
            samples = []
            for a,b in zip(points,points[1:]):
                count = max(1, math.ceil(math.dist(a,b)/.45))
                ts={i/count for i in range(count)}
                west,south,east,north=geo['bounds']
                u0,u1=[(p[0]-west)/(east-west)*(dem['cols']-1) for p in [a,b]]
                v0,v1=[(north-p[1])/(north-south)*(dem['rows']-1) for p in [a,b]]
                # The visible ground is piecewise planar. Retain its grid and
                # diagonal crossings so a DEM ridge cannot peak between samples.
                for lo,hi in [(u0,u1),(v0,v1),(u0-v0,u1-v1)]:
                    if abs(hi-lo)<1e-10: continue
                    for edge in range(math.ceil(min(lo,hi)),math.floor(max(lo,hi))+1):
                        t=(edge-lo)/(hi-lo)
                        if 1e-7<t<1-1e-7: ts.add(t)
                samples.extend([(a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t) for t in sorted(ts)])
            samples.append(points[-1])
            indices = []
            for i,p in enumerate(samples):
                rounded = tuple(round(v,7) for v in p)
                osm_node = source_nodes.get(rounded)
                key = ('osm',osm_node) if osm_node else (element['id'],part,i)
                if key not in node_lookup:
                    node_lookup[key] = len(nodes)
                    station = next((name for name,site in sites.items() if site.covers(Point(p))), None)
                    nodes.append({'xy':list(rounded), 'osmNode':osm_node, 'station':station})
                if not indices or indices[-1] != node_lookup[key]:
                    indices.append(node_lookup[key])
            paths.append({'id':f"{element['id']}-{part}", 'osmId':element['id'], 'nodes':indices,
                          'tags':tags, 'lengthMeters':round(line.length*100,3)})
    surface_paths = [p for p in paths if p['tags'].get('tunnel','no') == 'no']
    surface_lines = [LineString([nodes[i]['xy'] for i in p['nodes']]) for p in surface_paths]
    surface = unary_union(surface_lines)
    corridor = surface.buffer(.20, cap_style=2, join_style=2)
    index = STRtree(surface_lines)
    road_areas = [LineString(r['points']).buffer(.15 if r['class'] in ['primary','trunk','motorway'] else .10,
                  cap_style=2,join_style=2) for r in geo['roads']]
    road_index = STRtree(road_areas)
    for route,line in zip(surface_paths,surface_lines):
        route['piers'],route['masts']=[],[]
        if route['tags'].get('bridge','no')!='no':
            count=max(1,math.ceil(line.length/.32))
            for j in range(count):
                distance=(j+.5)*line.length/count
                point=line.interpolate(distance)
                # Leave streets and lower railway corridors open below spans.
                if len(road_index.query(point.buffer(.035),predicate='intersects')): continue
                conflicts=index.query(point.buffer(.026),predicate='intersects')
                if any(surface_paths[int(i)]['id']!=route['id'] and
                       surface_paths[int(i)]['tags'].get('layer','0')!=route['tags'].get('layer','0') for i in conflicts): continue
                route['piers'].append(round(distance,7))
        if route['tags'].get('electrified')=='contact_line' and line.length>=.22:
            count=max(1,math.floor(line.length/.55))
            for j in range(count):
                distance=(j+.5)*line.length/count
                x,y=line.interpolate(distance).coords[0]
                a,b=line.interpolate(max(0,distance-.001)).coords[0],line.interpolate(min(line.length,distance+.001)).coords[0]
                length=math.dist(a,b)
                point=Point(x-(b[1]-a[1])/length*.041,y+(b[0]-a[0])/length*.041)
                if any(site.covers(Point(x,y)) for site in sites.values()): continue
                if len(index.query(point.buffer(.025),predicate='intersects')): continue
                if len(road_index.query(point.buffer(.012),predicate='intersects')): continue
                route['masts'].append(round(distance,7))
    removed_trees = [i for i,(x,y,r) in enumerate(geo['trees'])
                     if len(index.query(Point(x,y).buffer(r+.20), predicate='intersects'))]
    removed_buildings = [i for i,b in enumerate(geo['buildings']) if b['source']=='procedural'
                         and corridor.intersects(Polygon(b['rings'][0]))]
    inputs = ['data/railways-source.json','data/stations-plan.json','data/region.json',
              'public/data/geography.json','public/data/terrain.json']
    plan = {'version':1, 'sceneCenter':geo['center'], 'bbox':geo['bbox'],
            'osmTimestamp':source['osm3s']['timestamp_osm_base'],
            'attribution':source['attribution'],
            'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
            'nodes':nodes, 'paths':paths, 'removedTrees':removed_trees,
            'removedBuildings':removed_buildings,
            'stats':{'ways':len({p['osmId'] for p in paths}), 'sections':len(paths),
                     'trackLengthKm':round(sum(p['lengthMeters'] for p in paths)/1000,3),
                     'bridgeSections':sum(p['tags'].get('bridge','no')!='no' for p in paths),
                     'tunnelSections':sum(p['tags'].get('tunnel','no')!='no' for p in paths)}}
    (ROOT/'data/railways-plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(plan['stats'],ensure_ascii=False), 'nodes',len(nodes),
          'cleared infill',len(removed_buildings),'trees',len(removed_trees),flush=True)


if __name__ == '__main__':
    prepare()
