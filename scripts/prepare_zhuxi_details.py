"""Place Zhuxi lights and planted islands against the final resolved road mesh."""
import gzip,hashlib,json,math,random,sys
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import LineString,Point,Polygon,box
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from viaduct import Path as RoadPath
from zhuxi_interchange import WAYS
from finish_road_solids import Surface


def prepare(output_path=None):
    plan=json.loads(gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes()))
    selected=[(i,r,RoadPath(r['points'])) for i,r in enumerate(plan['routes']) if r['osmId'] in WAYS]
    assert len(selected)==19,'Zhuxi source ways changed; review the scoped interchange'
    lamps={}
    for profile in ['detail','smooth']:
        raw=np.load(ROOT/f'data/road-solids-{profile}.npz')
        levels=json.loads((ROOT/f'data/road-solids-{profile}.json').read_text())['levels']
        road_faces=np.concatenate((raw['elevated'],raw['ground'],raw['railings'],raw['minzu'],raw['minzuRailings']))
        c=road_faces.mean(axis=1)
        road_faces=road_faces[(c[:,0]>73)&(c[:,0]<80)&(c[:,1]>-14)&(c[:,1]<-6)]
        surfaces=Surface(road_faces);caps=Surface(raw['railings']);placed=[]
        for owner,r,path in selected:
            for s in np.arange(.22,path.length-.20,.46 if profile=='smooth' else .32):
                if any(abs(path.lengths[j]-s)<.18 for _,stations in r['mergeStations'] for j in stations):continue
                j,t=path.section(s);z=levels[owner][j]*(1-t)+levels[owner][j+1]*t
                # Mount the pole on the parapet cap, centred within its 0.5 m
                # width; the old road-edge base cut through the parapet side.
                x,y=path.at(s,-r['width']-.0028)[:2]
                supports=[(float(caps.z(f,[x,y])),f) for f in caps.tree.query(Point(x,y),predicate='intersects')
                          if .006<float(caps.z(f,[x,y]))-z<.025]
                if not supports:continue
                z,cap=min(supports,key=lambda item:abs(item[0]-z-.0123))
                # A vertical pole's whole base must clear a sloping cap.
                z+=.0022*math.hypot(*caps.coeff[cap][:2])+.0002
                blocked=False
                pole=Point(x,y).buffer(.0022)
                for f in surfaces.tree.query(pole,predicate='intersects'):
                    xy=shapely.get_coordinates(pole.intersection(surfaces.shapes[f]))
                    zz=surfaces.z(f,xy)
                    # A neighbouring cap may sit just above this pole's base;
                    # the larger lamp-arm envelope deliberately ignores that
                    # near-base range and cannot detect this collision.
                    if zz.max()>z+.0001 and zz.min()<z+.107:blocked=True;break
                if blocked:continue
                for f in surfaces.tree.query(Point(x,y).buffer(.034),predicate='intersects'):
                    cut=Point(x,y).buffer(.034).intersection(surfaces.shapes[f]);xy=shapely.get_coordinates(cut)
                    zz=surfaces.z(f,xy)
                    if zz.max()>z+.014 and zz.min()<z+.14:blocked=True;break
                if blocked:continue
                if any(math.hypot(x-a,y-b)<.16 for a,b,*_ in placed):continue
                u,v=path.at(s,0)[:2];d=math.hypot(u-x,v-y)
                placed.append([x,y,z,(u-x)/d,(v-y)/d])
        lamps[profile]=placed
    # Enclosed pockets of the existing interchange, never a rectangular park overlay.
    geo=json.loads((ROOT/'public/data/geography.json').read_text())
    scope=box(73.8,-12.8,79.3,-7.65)
    widths={r['roadIndex']:r['width'] for _,r,_ in selected}
    roads=[]
    for i,r in enumerate(geo['roads']):
        line=LineString(r['points'])
        if not scope.intersects(line):continue
        width=widths.get(i,.105 if r['class'] in ['primary','trunk','motorway'] else .065)
        roads.append(line.buffer(width+.025,join_style=2))
    paved=shapely.union_all(roads)
    islands=[]
    for polygon in shapely.get_parts(paved):
        for ring in polygon.interiors:
            area=Polygon(ring)
            if .04<area.area<5 and scope.covers(area):islands.append(area)
    obstacles=[Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings'] if scope.intersects(Polygon(b['rings'][0]))]
    obstacles += [Polygon(p[0],p[1:]) for p in geo['water'] if scope.intersects(Polygon(p[0]))]
    obstacles += [Polygon(p[0],p[1:]) for p in json.loads((ROOT/'data/ground-roads-context.json').read_text())['obstacles'] if scope.intersects(Polygon(p[0]))]
    actual_ramps=[LineString(r['points']).buffer(r['width']+.025) for _,r,_ in selected]
    blocked=shapely.union_all([paved,*obstacles,*actual_ramps])
    safe=shapely.union_all(islands).difference(blocked.buffer(.025))
    trees=[];rng=random.Random(4321)
    for x in np.arange(73.8,79.3,.085):
        for y in np.arange(-12.8,-7.65,.085):
            xj=float(x+rng.uniform(-.025,.025));yj=float(y+rng.uniform(-.025,.025));radius=rng.uniform(.035,.055)
            if safe.covers(Point(xj,yj)) and blocked.distance(Point(xj,yj))>radius*1.1+.008:
                trees.append([xj,yj,radius])
    inputs=['data/elevated-roads-plan.json.gz','data/road-solids-detail.npz','data/road-solids-smooth.npz',
            'public/data/geography.json','data/ground-roads-context.json']
    output={'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
            'lamps':lamps,'trees':trees,'islands':[list(p.exterior.coords) for p in islands]}
    (output_path or ROOT/'data/zhuxi-details.json').write_text(json.dumps(output,separators=(',',':'))+'\n')
    print('Zhuxi',len(islands),'green islands;',len(trees),'trees; lamps', {p:len(v) for p,v in lamps.items()})

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path)
    prepare(parser.parse_args().output)
