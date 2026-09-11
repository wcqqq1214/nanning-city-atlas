"""Check source provenance, unchanged raw samples and exported mall grading."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from shapely.geometry import Polygon
from validate_cultural_landmarks import glb, terrain_peak

ROOT=Path(__file__).resolve().parents[1]


def validate():
    dem=json.loads((ROOT/'public/data/terrain.json').read_text())
    manifest=json.loads((ROOT/'data/terrain-source.json').read_text())
    for path,digest in manifest['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Stale terrain: {path}'
    forest=json.loads((ROOT/'data/forest-plan.json').read_text())
    digest=hashlib.sha256(json.dumps([r['woodland'] for r in forest['regions']],separators=(',',':')).encode()).hexdigest()
    assert digest==manifest['woodlandFootprintSha256'],'Woodland mask changed; resample terrain'
    rows,cols=dem['rows'],dem['cols']
    raw=np.asarray(dem['heights']).reshape(rows,cols)
    display=np.asarray(dem['sceneHeights']).reshape(rows,cols)
    assert np.isfinite(raw).all() and np.isfinite(display).all()
    assert raw.min()>0 and raw.max()<1000, 'Unexpected Nanning source elevation'
    w,s,e,n=dem['bbox'];cx,cy=dem['center']
    assert (e-w)*111320*math.cos(math.radians(cy))/(cols-1)<=60
    assert (n-s)*111320/(rows-1)<=60
    assert dem['verticalExaggeration']==1.35
    wet=np.array(dem['landcover']).reshape(rows,cols)==2
    assert np.max(np.abs(display[wet]-dem['conditioning']['waterDisplayMeters']))<.001
    tile=ROOT/'work/geodata'/Path(dem['sourceUrl']).name
    if tile.exists():
        assert hashlib.sha256(tile.read_bytes()).hexdigest()==dem['sourceSha256']
        with rasterio.open(tile) as source:
            grid=source.read(1);t=source.transform
            # Independent raster coordinates at well-spaced points including all edges.
            js,is_=np.meshgrid(np.linspace(0,rows-1,23,dtype=int),np.linspace(0,cols-1,31,dtype=int),indexing='ij')
            lon=w+(e-w)*is_/(cols-1);lat=n-(n-s)*js/(rows-1)
            expected=map_coordinates(grid,[(lat-t.f)/t.e-.5,(lon-t.c)/t.a-.5],order=1)
            assert np.max(np.abs(raw[js,is_]-expected))<.006,'Raw samples no longer match the source raster'
    else:
        print('Source raster not cached; source-value comparison skipped')
    mall=json.loads((ROOT/'data/malls-plan.json').read_text())
    places={p['id']:p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
    sites={}
    for identity,site in mall['sites'].items():
        mx=(site['center'][0]-cx)*1113.2*math.cos(math.radians(cy));my=(site['center'][1]-cy)*1113.2
        sites[identity]=Polygon([(mx+x,my+y) for x,y in site['site']])
    result={}
    for profile,suffix in [('detail',''),('smooth','-mobile')]:
        doc,decode=glb(ROOT/f'public/models/nanning-city{suffix}.glb')
        triangles=[]
        for node in doc['nodes']:
            if 'mesh' not in node or not node.get('name','').startswith('Terrain_'):continue
            for p in doc['meshes'][node['mesh']]['primitives']:
                a=doc['accessors'][p['attributes']['POSITION']];lo,hi=a['min'],a['max']
                if not any(lo[0]<=s.bounds[2] and hi[0]>=s.bounds[0] and -hi[2]<=s.bounds[3] and -lo[2]>=s.bounds[1] for s in sites.values()):continue
                m=decode(p);triangles.append(m.points[m.faces])
        triangles=np.concatenate(triangles)
        inverse=triangles.copy();inverse[:,:,1]*=-1
        result[profile]={}
        for identity,site in sites.items():
            high=terrain_peak(triangles,site);low=-terrain_peak(inverse,site)
            assert high-low<.005,f'{profile}/{identity}: mall parcel is not flat'
            clearance=places[identity]['position'][1]-high
            assert .001<clearance<.10,f'{profile}/{identity}: buried floor or tall artificial pedestal'
            result[profile][identity]={'terrainRangeMeters':round((high-low)*100,3),'floorClearanceMeters':round(clearance*100,3)}
    print('PASS: source samples, water level, woodland provenance, both exported mall parcels and floor clearance.')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':validate()
