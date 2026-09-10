"""Audit source replacements, navigation spans, layer parenting and decoded GLBs."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import DracoPy
import numpy as np
from shapely.geometry import LineString, Point

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from major_bridges import PLAN, SPECS, REPLACED_ROADS


def validate_bridges():
    geo=json.loads((ROOT/'public/data/geography.json').read_text())
    catalog=json.loads((ROOT/'public/data/landmarks.json').read_text())
    places={p['id']:p for p in catalog}
    assert len(places)==len(catalog), 'Duplicate place IDs'
    assert len(SPECS)==13 and len(REPLACED_ROADS)==28
    assert SPECS['taoyuan-bridge']['roadIndices']==[749,872], 'Unnamed Taoyuan bridge was omitted or captured its ramps'
    assert SPECS['taoyuan-bridge']['spansMeters']==[66,120,120,66]
    assert PLAN['sceneCenter']==geo['center']
    digest=hashlib.sha256((ROOT/'data/bridges-plan.json').read_bytes()).hexdigest()
    for path,fingerprint in PLAN['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==fingerprint, f'Stale bridge plan: {path}'
    assert json.loads((ROOT/'public/data/overview.json').read_text())['riverBridges']['planHash']==digest
    for identity,s in SPECS.items():
        assert places[identity]['layer']=='roads' and places[identity]['modelled']
        line=LineString(s['points'])
        assert abs(line.length-s['length'])<1e-6
        assert abs((s['mainEnd']-s['mainStart'])*100-sum(s['spansMeters']))<1e-5
        assert 0<s['mainStart']<s['mainEnd']<line.length
        assert max(a for a in np.linalg.norm(np.diff(np.array(s['points']),axis=0),axis=1))<.081
        midpoint=line.interpolate((s['mainStart']+s['mainEnd'])/2)
        p=places[identity]['position']
        assert midpoint.distance(Point(p[0],-p[2]))<.002, f'{identity}: wrong label anchor'
        for index in s['roadIndices']:
            road=geo['roads'][index]
            assert road['bridge'] and road['name']==s.get('osmName',s['name'])
            assert LineString(road['points']).difference(line.buffer(.20)).is_empty, f'{identity}: centreline drift'
    full={}
    totals=[]
    for profile in ['nanning-city.glb','nanning-city-mobile.glb']:
        raw=(ROOT/'public/models'/profile).read_bytes()
        size=struct.unpack_from('<I',raw,12)[0]
        model=json.loads(raw[20:20+size]); binary=28+size
        nodes=model['nodes']; lookup={n.get('name'):n for n in nodes}
        parent=lookup['Bridges']
        structures=details=0
        taoyuan_counts=None
        for identity,s in SPECS.items():
            node=lookup['Landmark_'+identity]
            assert nodes.index(node) in parent['children'], 'Bridge ignores roads layer'
            assert node['extras']['planHash']==digest
            assert node['extras']['sourceRoadIndices']==s['roadIndices']
            fittings=lookup['RiverBridge_Details_'+identity]
            assert nodes.index(fittings) in node['children']
            counts=[]
            for n in [node,fittings]:
                count=0; collapsed=0; faces_count=0; decks=[]
                for primitive in model['meshes'][n['mesh']]['primitives']:
                    count+=model['accessors'][primitive['indices']]['count']//3
                    ext=primitive['extensions']['KHR_draco_mesh_compression']
                    view=model['bufferViews'][ext['bufferView']]
                    start=binary+view.get('byteOffset',0)
                    mesh=DracoPy.decode(raw[start:start+view['byteLength']])
                    assert np.isfinite(mesh.points).all(), 'Nonfinite bridge vertex'
                    faces=mesh.points[mesh.faces]
                    area=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)/2
                    collapsed+=int((area<1e-11).sum());faces_count+=len(faces)
                    if model['materials'][primitive['material']]['name']=='River bridge asphalt': decks.extend(mesh.points)
                assert collapsed/max(1,faces_count)<.005, f'{identity}: compression collapsed geometry'
                if n is node:
                    points=np.array(decks)
                    assert len(points)>10, f'{identity}: missing deck'
                    p=places[identity]['position']
                    assert abs(points[:,1].max()-p[1])<3, 'Wrong vertical coordinate convention'
                    if s['displayRise']>0:
                        bounds=model['accessors'][model['meshes'][n['mesh']]['primitives'][0]['attributes']['POSITION']]
                        assert all(math.isfinite(v) for v in bounds['min']+bounds['max'])
                counts.append(count)
            structures+=counts[0];details+=counts[1]
            if identity=='taoyuan-bridge': taoyuan_counts=counts
            if profile=='nanning-city.glb': full[identity]=counts
            else:
                assert counts[0]==full[identity][0], 'Mobile lost bridge structure'
                assert 0<counts[1]<full[identity][1], 'Bridge fittings LOD missing'
        # Keep the original twelve-bridge budget; Taoyuan has its own allowance.
        assert all(0<count<20_000 for count in taoyuan_counts), 'Taoyuan bridge exceeded its budget'
        assert structures-taoyuan_counts[0]<160_000 and details-taoyuan_counts[1]<160_000, 'Existing bridge geometry exceeded its budget'
        totals.append((structures,details))
    print(f'PASS: {len(SPECS)} bridges / {len(REPLACED_ROADS)} replaced strips; decoded structures and layer parenting; detail/smooth triangles {totals}')
    return totals


if __name__=='__main__': validate_bridges()
