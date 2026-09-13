"""Regression checks for P4 source preparation and unaffected canopy sampling."""
import json
import sys
import unittest
from pathlib import Path
from shapely.geometry import box,Point,Polygon

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'blender')]
from prepare_landmark_calibration import prepare
from prepare_forest_canopy import prepare_region
from landmark_sites import reservation_rings,SPECS


class CalibrationTests(unittest.TestCase):
    def test_reproducible_plan(self):
        self.assertEqual(json.loads((ROOT/'data/landmark-calibration-plan.json').read_text()),prepare())

    def test_reservations_and_mapped_water(self):
        from shapely.ops import unary_union
        import math
        geo=json.loads((ROOT/'public/data/geography.json').read_text())
        catalog={p['id']:p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
        water=unary_union([Polygon(r[0],r[1:]) for r in geo['water']])
        kx=1113.2*math.cos(math.radians(geo['center'][1]))
        for identity in SPECS:
            p=catalog[identity];x=(p['lon']-geo['center'][0])*kx;y=(p['lat']-geo['center'][1])*1113.2
            rings=reservation_rings(identity)
            self.assertTrue(all(Polygon(r).is_valid for r in rings))
            shape=unary_union([Polygon([(x+u,y+v) for u,v in ring]) for ring in rings])
            self.assertLess(shape.intersection(water).area,1e-9,identity)
            self.assertTrue(all(abs(u)<p['clearExtent'][0]/2 and abs(v)<p['clearExtent'][1]/2 for r in rings for u,v in r))

    def test_local_clearing_does_not_shift_distant_crowns(self):
        geo={'bounds':[0,0,12,12],'trees':[]};dem={'cols':11,'rows':11}
        woodland=box(.1,.1,11.9,11.9)
        old=box(4,4,8,8);new=box(5,5,7,7)
        previous=prepare_region('sample',woodland,old,geo,dem,1.95,11922560,old)
        current=prepare_region('sample',woodland,new,geo,dem,1.95,11922560,old)
        self.assertGreater(len(current['crownClusters']),len(previous['crownClusters']))
        for key in ['crownClusters','smoothCrownClusters']:
            for crown in previous[key]:
                self.assertIn(crown,current[key],f'Unchanged {key} moved or changed colour')
        self.assertEqual(current,prepare_region('sample',woodland,new,geo,dem,1.95,11922560,old))


if __name__=='__main__':unittest.main()
