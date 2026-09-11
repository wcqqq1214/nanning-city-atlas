"""Audit prepared mall footprints and both actually exported Draco meshes."""
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import DracoPy
import numpy as np
from shapely import intersects_xy
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from mall_landmarks import PLAN, SITES, intersects_site


def validate_malls(plan_only=False):
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    catalog = {p['id']: p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
    exported = {p['id']: p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
    assert PLAN['sceneCenter'] == geo['center']
    assert PLAN['sourceHash'] == hashlib.sha256((ROOT/'data/malls-source.json').read_bytes()).hexdigest()
    context = json.loads((ROOT/'data/ground-roads-context.json').read_text())
    obstacles = unary_union([Polygon(p[0],p[1:]) for p in context['obstacles']])
    water = unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    envelopes = {}
    for identity,site in SITES.items():
        place = catalog[identity]
        assert [place['lon'],place['lat']] == site['center'] and place['modelled']
        assert place['closeDistance'] < place['cameraDistance']
        x=(place['lon']-geo['center'][0])*1113.2*math.cos(math.radians(geo['center'][1]))
        y=(place['lat']-geo['center'][1])*1113.2
        ring=site['site'];shape=Polygon(ring)
        assert shape.is_valid
        triangles=[Polygon([ring[i] for i in tri]) for tri in site['triangles']]
        assert all(t.is_valid and t.area>1e-10 for t in triangles)
        assert unary_union(triangles).symmetric_difference(shape).area<1e-9, 'Mall roof fills its concave courtyard'
        assert abs(sum(t.area for t in triangles)-shape.area)<1e-9
        site_shape=Polygon([(x+u,y+v) for u,v in ring])
        envelope=unary_union([site_shape,*[box(x+w,y+s,x+e,y+n) for w,s,e,n in site['entranceRects']]])
        assert not envelope.intersects(water)
        assert envelope.difference(obstacles.buffer(.001)).area < .00001, 'Ground roads were not rebuilt around the malls'
        for tower in site['towers']:
            assert shape.covers(Polygon(tower['ring']))
        for b in geo['buildings']:
            if b.get('name') in ['南宁华润大厦A座','南宁华润大厦B座','南宁华润大厦C座']:
                assert not intersects_site(identity,b['rings'][0][:-1],x,y), 'Mall replacement deletes neighbouring CR towers'
        envelopes[identity]=(x,y,envelope.buffer(.04))
    if plan_only:
        print('Malls: source, concave roof, road obstacles and CR neighbours verified.')
        return
    results={}
    for quality,suffix in [('detail',''),('smooth','-mobile')]:
        raw=(ROOT/f'public/models/nanning-city{suffix}.glb').read_bytes()
        size=struct.unpack_from('<I',raw,12)[0];model=json.loads(raw[20:20+size]);binary=28+size
        result={}
        for identity in SITES:
            nodes=[n for n in model['nodes'] if n.get('name')=='Landmark_'+identity]
            assert len(nodes)==1 and 'mesh' in nodes[0]
            node=nodes[0]
            assert not any(k in node for k in ['matrix','translation','rotation','scale'])
            count=0; materials=set();all_points=[]
            for primitive in model['meshes'][node['mesh']]['primitives']:
                ext=primitive['extensions']['KHR_draco_mesh_compression'];view=model['bufferViews'][ext['bufferView']]
                start=binary+view.get('byteOffset',0)
                mesh=DracoPy.decode(raw[start:start+view['byteLength']])
                assert np.isfinite(mesh.points).all()
                faces=mesh.points[mesh.faces]
                area=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)/2
                assert (area>1e-12).all(), f'{quality}/{identity} has collapsed decoded triangles'
                material_name=model['materials'][primitive['material']]['name']
                materials.add(material_name)
                if identity=='mixc' and material_name=='MixC bronze entrance surrounds':
                    x,y,_=envelopes[identity]
                    corner=LineString([(x+u,y+v) for u,v in SITES[identity]['site'][2:4]]).buffer(.10)
                    tall=mesh.points[mesh.points[:,1]>exported[identity]['position'][1]+.59]
                    assert len(tall)>10 and intersects_xy(corner,tall[:,0],-tall[:,2]).all(), 'MixC main entrance must face the NW corner'
                count+=len(mesh.faces);all_points.extend(mesh.points)
            points=np.asarray(all_points)
            _,_,envelope=envelopes[identity]
            assert intersects_xy(envelope,points[:,0],-points[:,2]).all(), 'Mall mesh leaves the prepared site and entrances'
            assert {'Mall blue sage glazing','Mall aluminium mullions','Mall warm gold lettering'} <= materials
            assert (15_000<count<32_000) if identity=='hangyang' else (5_000<count<12_000)
            result[identity]={'triangles':count,'materials':len(materials),
                              'bounds':np.round([points.min(axis=0),points.max(axis=0)],4).tolist()}
        results[quality]=result
    assert results['detail']==results['smooth'], 'Lightweight export loses mall geometry'
    print('Malls: source, concave roof, road obstacles, CR neighbours and both Draco exports verified.')
    print(json.dumps(results,ensure_ascii=False))
    return results


if __name__=='__main__':
    validate_malls(plan_only='--plan-only' in sys.argv)
