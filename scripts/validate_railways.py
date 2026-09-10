"""Audit retained railway coverage, station connections and compressed meshes."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct

import DracoPy
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]


def validate_railways():
    plan=json.loads((ROOT/'data/railways-plan.json').read_text())
    source=json.loads((ROOT/'data/railways-source.json').read_text())
    geo=json.loads((ROOT/'public/data/geography.json').read_text())
    station_plan=json.loads((ROOT/'data/stations-plan.json').read_text())
    for path,fingerprint in plan['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==fingerprint, f'Stale railway plan: {path}'
    assert plan['bbox']==source['bbox']==geo['bbox']
    assert plan['osmTimestamp']==source['osm3s']['timestamp_osm_base']
    kx=1113.2*math.cos(math.radians(geo['center'][1]))
    def xy(lon,lat):return ((lon-geo['center'][0])*kx,(lat-geo['center'][1])*1113.2)
    clip=box(*geo['bounds'])
    ways={e['id']:e for e in source['elements']}
    retained=defaultdict(list)
    adjacency=defaultdict(set)
    for route in plan['paths']:
        e=ways[route['osmId']]
        assert route['tags']==e['tags'] and e['tags']['railway']=='rail'
        points=[plan['nodes'][i]['xy'] for i in route['nodes']]
        assert all(math.isfinite(v) for p in points for v in p)
        line=LineString(points)
        assert line.length>0 and clip.buffer(.000001).covers(line)
        retained[route['osmId']].append(line)
        for a,b in zip(route['nodes'],route['nodes'][1:]):
            assert a!=b
            adjacency[a].add(b);adjacency[b].add(a)
    for identity,e in ways.items():
        original=LineString([xy(p['lon'],p['lat']) for p in e['geometry']]).intersection(clip)
        if original.is_empty:continue
        actual=unary_union(retained[identity])
        assert original.hausdorff_distance(actual)<.000002, f'Changed railway alignment: {identity}'
        assert abs(original.length-sum(p.length for p in retained[identity]))<.00001, f'Missing/duplicate track: {identity}'
    # Both stations must remain on a common connected source-node network.
    station_nodes={name:{i for i,n in enumerate(plan['nodes']) if n['station']==name} for name in station_plan['stations']}
    start=next(iter(station_nodes['nanning-station']))
    connected={start};todo=[start]
    while todo:
        i=todo.pop()
        for j in adjacency[i]-connected: connected.add(j);todo.append(j)
    assert connected & station_nodes['east-station'], 'Disconnected stations'
    for name,station in station_plan['stations'].items():
        sx,sy=xy(*station['center']);c,s=math.cos(station['angle']),math.sin(station['angle'])
        for rail in station['rails']:
            old=LineString([(sx+u*c-v*s,sy+u*s+v*c) for u,v in rail['points']])
            assert old.difference(unary_union(retained[rail['osmId']]).buffer(.0031)).is_empty, 'Station track lost its approach'
        assert any(adjacency[i]-station_nodes[name] for i in station_nodes[name]), 'Station has no external connection'
    surface_index=STRtree([line.simplify(.000001).buffer(.20,cap_style=2,join_style=2)
                           for route in plan['paths'] if route['tags'].get('tunnel','no')=='no'
                           for line in retained[route['osmId']]])
    sampled_nodes={i for route in plan['paths'] if route['tags'].get('tunnel','no')=='no'
                   for i in route['nodes'] if plan['nodes'][i]['osmNode'] is not None}
    for i in plan['removedBuildings']:
        building=geo['buildings'][i]
        assert building['source']=='procedural' and len(surface_index.query(Polygon(building['rings'][0]),predicate='intersects'))
    report=json.loads((ROOT/'public/data/overview.json').read_text())['railways']
    assert report['planHash']==hashlib.sha256((ROOT/'data/railways-plan.json').read_bytes()).hexdigest()
    assert report['geometry']['maxStationDatumError']<1e-7
    assert report['geometry']['maxBallastPenetration']<.001
    assert report['geometry']['maxDisplayGrade']<=.120001
    profiles=[]
    for filename in ['nanning-city.glb','nanning-city-mobile.glb']:
        raw=(ROOT/'public/models'/filename).read_bytes()
        size=struct.unpack_from('<I',raw,12)[0];model=json.loads(raw[20:20+size]);binary=28+size
        parent=next(n for n in model['nodes'] if n.get('name')=='Railways')
        assert parent['extras']['planHash']==report['planHash'], 'Exported model has a stale railway plan'
        children=[]
        def visit(node):
            children.append(node)
            for i in node.get('children',[]):visit(model['nodes'][i])
        visit(parent)
        assert any(n.get('name')=='Railway_Details' for n in children)
        counts={'structure':0,'details':0};rail_triangles=rail_degenerate=0
        steel_points=[]
        for node in children:
            if 'mesh' not in node:continue
            mesh=model['meshes'][node['mesh']]
            kind='details' if node['name'].startswith('Railway_Details') else 'structure'
            for primitive in mesh['primitives']:
                count=model['accessors'][primitive['indices']]['count']//3
                counts[kind]+=count
                material=model['materials'][primitive['material']]['name']
                if material!='Railway polished rail heads':continue
                view=model['bufferViews'][primitive['extensions']['KHR_draco_mesh_compression']['bufferView']]
                start=binary+view.get('byteOffset',0)
                decoded=DracoPy.decode(raw[start:start+view['byteLength']])
                assert np.isfinite(decoded.points).all() and len(decoded.faces)==count
                assert decoded.faces.min()>=0 and decoded.faces.max()<len(decoded.points)
                steel_points.append(decoded.points)
                triangles=decoded.points[decoded.faces]
                area=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)
                rail_triangles+=len(area);rail_degenerate+=int(np.sum(area<1e-12))
        assert rail_triangles>50000, 'Missing continuous steel rails'
        assert rail_degenerate/rail_triangles<.01, f'Compression collapses rail geometry: {rail_degenerate}/{rail_triangles}'
        assert 100000<counts['structure']<1000000
        # Inspect actual decoded rail-head coordinates, not just triangle counts.
        # Every retained surface source node must have steel within one metre of
        # its centreline (gauge/2 plus quantization tolerance); tunnels excluded.
        cells=defaultdict(list)
        for p in np.vstack(steel_points):
            cells[(math.floor(float(p[0])/2),math.floor(float(-p[2])/2))].append((p[0],-p[2]))
        cells={key:np.array(points) for key,points in cells.items()}
        max_alignment_error=0.
        for i in sampled_nodes:
            x,y=plan['nodes'][i]['xy'];gx,gy=math.floor(x/2),math.floor(y/2)
            candidates=[cells[(u,v)] for u in range(gx-1,gx+2) for v in range(gy-1,gy+2) if (u,v) in cells]
            assert candidates, f'Missing exported track near {i}'
            distance=float(np.sqrt(np.min(np.sum((np.vstack(candidates)-[x,y])**2,axis=1))))
            max_alignment_error=max(max_alignment_error,distance)
        assert max_alignment_error<.0105, f'Exported steel misses source track: {max_alignment_error*100:.2f} m'
        profiles.append(counts)
        print(f'{filename}: {counts}; collapsed rail faces {rail_degenerate}/{rail_triangles}; source alignment {max_alignment_error*100:.3f} m',flush=True)
    assert profiles[0]['structure']==profiles[1]['structure'], 'Mobile lost structural railways'
    assert 0<profiles[1]['details']<profiles[0]['details']
    print('PASS: all source tracks, two station connections, grade/terrain audit, layer hierarchy and decoded rail heads.',flush=True)


if __name__=='__main__':validate_railways()
