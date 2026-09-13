"""Check the real patch mesh, shared sampler and immutable geographic inputs."""
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from local_terrain import PLAN, surface, vertex_heights, replaces_cell
from forest_canopy import coarse_terrain_surface
from terrain_height import scene_height
from major_bridges import Bridge, SPECS

GEO=json.loads((ROOT/'public/data/geography.json').read_text())
DEM=json.loads((ROOT/'public/data/terrain.json').read_text())


def ground(x,y):
    w,s,e,n=GEO['bounds'];cols,rows=DEM['cols'],DEM['rows']
    u=max(0,min(cols-1.000001,(x-w)/(e-w)*(cols-1)))
    v=max(0,min(rows-1.000001,(n-y)/(n-s)*(rows-1)))
    i,j=int(u),int(v);a,b=u-i,v-j;h=DEM['sceneHeights']
    meters=(h[j*cols+i]*(1-a)+h[j*cols+i+1]*a)*(1-b)+(h[(j+1)*cols+i]*(1-a)+h[(j+1)*cols+i+1]*a)*b
    return scene_height(meters,DEM)


class WaterfrontTests(unittest.TestCase):
    def test_coverage_and_materials(self):
        water=unary_union([Polygon(r[0],r[1:]) for r in GEO['water']])
        shapes=[Polygon([PLAN['points'][i] for i in tri]) for tri in PLAN['triangles']]
        self.assertTrue(all(p.is_valid and p.area>0 for p in shapes))
        land=unary_union(shapes);expected=box(*PLAN['bounds']).difference(water)
        self.assertLess(land.symmetric_difference(expected).area,.00004)
        self.assertLess(sum(p.area for p in shapes)-land.area,.0000001)
        walk=unary_union([p for p,key in zip(shapes,PLAN['materials']) if key=='waterfront_paving'])
        self.assertLess(walk.intersection(water.buffer(-.000003)).area,1e-8)
        self.assertGreater(walk.area*10000,5000)
        pieces=[walk] if walk.geom_type=='Polygon' else list(walk.geoms)
        self.assertGreater(max(p.area for p in pieces)/walk.area,.99, 'Promenade was severed by an elevated bridge reservation')
        self.assertTrue(all(v%2==0 for key in ['columnRange','rowRange'] for v in PLAN[key]))
        self.assertGreater(PLAN['statistics']['lengthMeters'],500)

    def test_sampler_and_boundary(self):
        bounds=GEO['bounds'];cols,rows=DEM['cols'],DEM['rows']
        w,s,e,n=PLAN['bounds'];edge_count=0
        for mobile in [False,True]:
            levels=vertex_heights(ground,tuple(bounds),cols,rows,mobile,coarse_terrain_surface)
            for face in PLAN['triangles']:
                p=np.mean([PLAN['points'][i] for i in face],axis=0)
                z=surface(*p,ground,bounds,cols,rows,mobile,coarse_terrain_surface)
                self.assertIsNotNone(z)
                self.assertAlmostEqual(z,float(np.mean([levels[i] for i in face])),places=6)
            for i,(x,y) in enumerate(PLAN['points']):
                if min(abs(x-w),abs(x-e),abs(y-s),abs(y-n))<.000002:
                    edge_count+=1
                    self.assertAlmostEqual(levels[i],coarse_terrain_surface(x,y,ground,bounds,cols,rows,mobile),places=6)
            for a,b in zip(PLAN['wallVertexIds'],PLAN['wallVertexIds'][1:]):
                self.assertLess(math.dist(PLAN['points'][a],PLAN['points'][b]),.5)
                self.assertGreater(min(levels[a],levels[b]),PLAN['section']['waterSceneZ'])
        self.assertGreater(edge_count,80)

    def test_sources_unchanged(self):
        baseline=ROOT/'work/urban-structure/baseline-p1'
        for filename in ['geography.json','terrain.json']:
            self.assertEqual((ROOT/'public/data'/filename).read_bytes(),(baseline/'public/data'/filename).read_bytes())
        for path,digest in PLAN['inputHashes'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)

    def test_bridge_bank_support_and_grade(self):
        def final_ground(x,y):
            values=[surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
                    for mobile in [False,True]]
            return max(coarse_terrain_surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile)
                       if z is None else z for mobile,z in zip([False,True],values))
        bridge=Bridge(SPECS['yongjiang-bridge'],ground,lambda x,y:ground(x,y)+.065,final_ground)
        # Check the complete width and interpolated underside, including both banks.
        minimum=math.inf
        for s in np.linspace(0,bridge.path.total,600):
            i=max(0,min(len(bridge.stations)-2,int(np.searchsorted(bridge.stations,s,side='right'))-1))
            a,b=bridge.stations[i:i+2];t=(s-a)/(b-a)
            depth=bridge.depth(a)*(1-t)+bridge.depth(b)*t
            for offset in [-bridge.width,0,bridge.width]:
                x,y,_=bridge.path.at(s,offset)
                minimum=min(minimum,bridge.level(s)-depth-final_ground(x,y))
        self.assertGreater(minimum,.005,'Bridge underside intersects a bank between stations')
        self.assertLess(max(bridge.levels),.70,'The legacy 92 m deck offset returned')
        self.assertGreater(min(bridge.levels),SPECS['yongjiang-bridge']['displayProfile']['mainMinimumSceneZ']-.01)
        for a,b,u,v in zip(bridge.stations,bridge.stations[1:],bridge.levels,bridge.levels[1:]):
            self.assertLessEqual(abs(v-u)/(b-a),.200001)


if __name__=='__main__': unittest.main()
