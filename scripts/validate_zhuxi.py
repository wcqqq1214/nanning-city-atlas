"""Check the exported Zhuxi furnishings, lane scope and greenery clearance."""
import gzip,hashlib,json,struct,sys
from pathlib import Path
import DracoPy
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString,Point
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from zhuxi_interchange import WAYS,MAIN_WAYS,RAMP_WAYS,CONNECTOR_WAYS
from road_interfaces import LANDING_WAYS
from viaduct import Path as RoadPath
from road_collision_checks import intersections


def validate_zhuxi():
    plan=json.loads(gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes()))
    details=json.loads((ROOT/'data/zhuxi-details.json').read_text())
    for path,digest in details['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Stale Zhuxi data: {path}'
    selected=[r for r in plan['routes'] if r['osmId'] in WAYS]
    assert len(selected)==19
    for r in selected:
        expected=3 if r['osmId'] in MAIN_WAYS else 2 if r['osmId'] in RAMP_WAYS else 1
        assert r['lanes']==expected
        assert r['width']==(.065 if expected==3 else .0325 if expected==2 else .0175)
    assert len(details['islands'])>=2 and len(details['trees'])>=10,'Missing planted ramp interiors'
    assert any(y>-10.4 for x,y,r in details['trees']) and any(y<-10.4 for x,y,r in details['trees']), 'Missing greenery on one side of the interchange'
    for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
        levels=json.loads((ROOT/f'data/road-solids-{profile}.json').read_text())['levels']
        for i,r in enumerate(plan['routes']):
            if r['osmId'] not in LANDING_WAYS:continue
            path=RoadPath(r['points']);end=LANDING_WAYS[r['osmId']]
            endpoint=0 if end==0 else -1
            assert abs(levels[i][endpoint]-r['roadFloors'][profile][endpoint])<.002,'Minzu landing lost its fixed deck height'
            for j,(s,t) in enumerate(zip(path.lengths,path.lengths[1:])):
                if (s if end==0 else path.length-t)<.8:
                    assert abs(levels[i][j+1]-levels[i][j])<=.18*(t-s)+1e-6,'Steep spike at a Minzu landing'
        raw=(ROOT/'public/models'/filename).read_bytes();size=struct.unpack_from('<I',raw,12)[0]
        model=json.loads(raw[20:20+size]);nodes=model['nodes'];groups={'lamps':[],'trees':[],'roads':[],'structure':[]}
        lamps=next(n for n in nodes if n.get('name')=='ZhuxiInterchange')
        parent=next(n for n in nodes if n.get('name')=='ElevatedRoads')
        assert nodes.index(lamps) in parent['children'],'Lights ignore road-layer visibility'
        trees=next(n for n in nodes if n.get('name')=='Vegetation_zhuxi')
        parent=next(n for n in nodes if n.get('name')=='Vegetation')
        assert nodes.index(trees) in parent['children'],'Plantings ignore vegetation-layer visibility'
        minzu_road_faces=0
        for node in nodes:
            if 'mesh' not in node:continue
            name=node.get('name','')
            for p in model['meshes'][node['mesh']]['primitives']:
                mat=model['materials'][p['material']]['name']
                key='lamps' if name=='ZhuxiInterchange' else 'trees' if name=='Vegetation_zhuxi' else None
                if name.startswith(('ElevatedRoads_','MinzuAvenue_','GroundRoads_')) and mat in ['Qingxiang sage asphalt','Secondary sage streets','Simple neighbourhood paving']:key='roads'
                if name.startswith(('ElevatedRoads_','MinzuAvenue_','GroundRoads_')) and mat in ['Qingxiang warm concrete','Qingxiang shaded box girders']:key='structure'
                if name.startswith('MinzuAvenue_') and mat=='Qingxiang lamp columns':key='lamps'
                if key is None:continue
                view=model['bufferViews'][p['extensions']['KHR_draco_mesh_compression']['bufferView']];start=28+size+view.get('byteOffset',0)
                mesh=DracoPy.decode(raw[start:start+view['byteLength']]);tri=np.asarray(mesh.points[mesh.faces],dtype=float)[:,:,[0,2,1]];tri[:,:,1]*=-1
                if key in ['roads','structure'] or name.startswith('MinzuAvenue_'):
                    lo=tri.min(axis=1);hi=tri.max(axis=1)
                    tri=tri[(hi[:,0]>73.8)&(lo[:,0]<79.3)&(hi[:,1]>-12.8)&(lo[:,1]<-7.65)]
                if name.startswith('MinzuAvenue_') and key=='roads':minzu_road_faces+=len(tri)
                groups[key].append(tri)
        groups={k:np.concatenate(v) for k,v in groups.items()}
        assert minzu_road_faces>0,'The interface audit must include native Minzu road surfaces'
        assert len(groups['lamps'])>100 and len(groups['trees'])>0
        assert len(groups['trees'])==len(details['trees'])*(30 if profile=='detail' else 8), 'Exported greenery is stale'
        for name in ['lamps','trees']:
            for road in ['roads','structure']:
                conflicts=intersections(groups[name],groups[road],profile+' Zhuxi '+name+'/'+road)
                assert conflicts['pairs']==0,f'Zhuxi {name} intersects {road}'
        conflicts=intersections(groups['structure'],groups['roads'],profile+' Zhuxi structure/road')
        assert conflicts['pairs']==0,'Zhuxi structure intersects road, including Minzu interfaces'
        conflicts=intersections(groups['roads'],groups['roads'],profile+' Zhuxi road/road',self_test=True)
        assert conflicts['pairs']==0,'Zhuxi road surfaces intersect'
        # Conservative plan-space envelopes cover canopy edges as well as trunks.
        lines=shapely.union_all([LineString(r['points']).buffer(r['width']+.015) for r in selected])
        for x,y,radius in details['trees']:
            assert not lines.intersects(Point(x,y).buffer(radius*1.1)),'Canopy reaches an interchange ramp'
        print(profile, {k:len(v) for k,v in groups.items()},len(details['lamps'][profile]),'lamps',flush=True)
    print('PASS: Zhuxi lane scope, both exported detail groups, layer parents, lamp/canopy clearance.',flush=True)

if __name__=='__main__':validate_zhuxi()
