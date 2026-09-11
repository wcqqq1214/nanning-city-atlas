"""Validate place provenance, road reservations and both decoded cultural models.

Run with work/venv/bin/python scripts/validate_cultural_landmarks.py.
Ground clearance is measured against exported terrain, including triangle edges.
"""
import json
import math
import struct
import sys
from pathlib import Path

import DracoPy
import numpy as np
from shapely import intersects_xy
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from cultural_landmarks import SPECS, envelope


def glb(path):
    raw=path.read_bytes()
    size=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+size]);binary=28+size
    def decode(primitive):
        view=doc['bufferViews'][primitive['extensions']['KHR_draco_mesh_compression']['bufferView']]
        start=binary+view.get('byteOffset',0)
        return DracoPy.decode(raw[start:start+view['byteLength']])
    return doc,decode


def terrain_peak(triangles,site):
    """Exact maximum of each clipped linear terrain triangle over the site."""
    peak=-math.inf
    west,south,east,north=site.bounds
    horizontal=triangles[:,:,[0,2]]*np.array([1,-1])
    low=horizontal.min(axis=1);high=horizontal.max(axis=1)
    selected=(low[:,0]<=east)&(high[:,0]>=west)&(low[:,1]<=north)&(high[:,1]>=south)
    for tri,xy in zip(triangles[selected],horizontal[selected]):
        a,b,c=xy;matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-10:continue
        clipped=Polygon(xy).intersection(site)
        if clipped.is_empty or clipped.area<1e-10:continue
        points=np.asarray(clipped.exterior.coords)
        weights=np.linalg.solve(matrix,(points-a).T).T
        z=tri[0,1]+weights[:,0]*(tri[1,1]-tri[0,1])+weights[:,1]*(tri[2,1]-tri[0,1])
        peak=max(peak,float(z.max()))
    assert math.isfinite(peak), 'No terrain found under landmark'
    return peak


def validate():
    geo=json.loads((ROOT/'public/data/geography.json').read_text())
    catalog={p['id']:p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
    exported={p['id']:p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
    source=json.loads((ROOT/'data/cultural-landmarks-source.json').read_text())
    by_osm={p['id']:p for p in source['elements']}
    context=json.loads((ROOT/'data/ground-roads-context.json').read_text())
    obstacles=unary_union([Polygon(p[0],p[1:]) for p in context['obstacles']])
    sites={}
    for identity,spec in SPECS.items():
        place=catalog[identity];record=by_osm[spec['osmId']]
        if 'sourceUrl' in place:assert str(spec['osmId']) in place['sourceUrl']
        bounds=record['bounds']
        assert bounds['minlon']<=place['lon']<=bounds['maxlon']
        assert bounds['minlat']<=place['lat']<=bounds['maxlat']
        x=(place['lon']-geo['center'][0])*1113.2*math.cos(math.radians(geo['center'][1]))
        y=(place['lat']-geo['center'][1])*1113.2
        site=Polygon([(x+u,y+v) for u,v in envelope(identity)])
        assert site.difference(obstacles.buffer(.001)).area<1e-5, f'{identity}: outside prepared road obstacles'
        assert abs(exported[identity]['position'][0]-x)<.00051
        assert abs(exported[identity]['position'][2]+y)<.00051
        sites[identity]=site
    results={}
    for profile,suffix in [('detail',''),('smooth','-mobile')]:
        doc,decode=glb(ROOT/f'public/models/nanning-city{suffix}.glb')
        terrain=[]
        for node in doc['nodes']:
            if not node.get('name','').startswith('Terrain_') or 'mesh' not in node:continue
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                accessor=doc['accessors'][primitive['attributes']['POSITION']]
                lo,hi=accessor['min'],accessor['max']
                if not any(lo[0]<=s.bounds[2] and hi[0]>=s.bounds[0] and -hi[2]<=s.bounds[3] and -lo[2]>=s.bounds[1] for s in sites.values()):continue
                mesh=decode(primitive);terrain.append(mesh.points[mesh.faces])
        terrain=np.concatenate(terrain)
        result={}
        for identity,site in sites.items():
            nodes=[n for n in doc['nodes'] if n.get('name')=='Landmark_'+identity]
            assert len(nodes)==1 and 'mesh' in nodes[0], f'{identity}: duplicate or missing model'
            node=nodes[0]
            assert not any(k in node for k in ['matrix','translation','rotation','scale'])
            points=[];count=0;materials=set();shadow=None
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                mesh=decode(primitive);assert np.isfinite(mesh.points).all()
                faces=mesh.points[mesh.faces]
                areas=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)/2
                assert (areas>1e-12).all(), f'{profile}/{identity}: collapsed triangles after compression'
                name=doc['materials'][primitive['material']]['name'];materials.add(name)
                if name=='Longxiang recessed openings':shadow=faces.mean(axis=1)
                count+=len(faces);points.append(mesh.points)
            points=np.concatenate(points)
            assert intersects_xy(site.buffer(.0003),points[:,0],-points[:,2]).all(), f'{identity}: model leaves reserved footprint'
            datum=exported[identity]['position'][1]
            peak=terrain_peak(terrain,site)
            assert peak<datum-.001, f'{profile}/{identity}: terrain {peak} penetrates floor {datum}'
            assert abs(points[:,1].max()-datum-SPECS[identity]['height'])<.05
            assert 'Cultural landmark paving' in materials
            if identity=='qingxiu':
                assert shadow is not None and 35_000<count<60_000
                floors=np.floor((shadow[:,1]-datum-.075)/.275).astype(int)
                assert set(floors)==set(range(9)), 'Pagoda must retain nine distinct storeys of arched openings'
                assert {'Longxiang green glazed tiles','Longxiang jade eave edges','Longxiang red brown joinery'}<=materials
            else:
                assert 10_000<count<30_000
                assert {'Museum blue grey glazing','Museum bronze lettering','Museum ivory relief','Museum silver roof panels'}<=materials
            result[identity]={'triangles':count,'materials':len(materials),'terrainClearance':round(datum-peak,4),
                              'bounds':np.round([points.min(axis=0),points.max(axis=0)],4).tolist()}
        results[profile]=result
    for identity in SPECS:
        for field in ['triangles','materials','bounds']:
            assert results['detail'][identity][field]==results['smooth'][identity][field], f'{identity}: lightweight export loses detail'
    print('PASS: source locations, road reservations, nine pagoda storeys, both Draco meshes and exact displayed-terrain clearance.')
    print(json.dumps(results,ensure_ascii=False,indent=2))
    return results


if __name__=='__main__':
    validate()
