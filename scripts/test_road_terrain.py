"""An interior ridge must be covered even when both route endpoints are low."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from viaduct import Path as RoadPath
from road_terrain import deck_floors

class DeckTerrainTests(unittest.TestCase):
    def test_interior_ridge(self):
        path=RoadPath([(.1,.5),(1.9,.5)])
        ridge=lambda x,y:1-abs(x-1)
        floors=deck_floors(path,.05,[.1,.1],ridge,[0,0,2,1],3,2)
        for n in range(101):
            fraction=n/100;x=.1+1.8*fraction
            self.assertGreaterEqual(floors[0]*(1-fraction)+floors[1]*fraction,ridge(x,.5)-1e-9)

    def test_fixed_landing_preserved(self):
        path=RoadPath([(.1,.5),(1.9,.5)])
        ridge=lambda x,y:1-abs(x-1)
        floors=deck_floors(path,.05,[.1,.1],ridge,[0,0,2,1],3,2,{0:.1})
        self.assertAlmostEqual(floors[0],.1)
        for n in range(101):
            fraction=n/100;x=.1+1.8*fraction
            self.assertGreaterEqual(floors[0]*(1-fraction)+floors[1]*fraction,ridge(x,.5)-1e-9)

if __name__=='__main__':unittest.main()
