"""Check preserved P2 arrays and the original elevation raster."""
import unittest
from pathlib import Path
import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from test_qingxiu_terrain import ROOT, PLAN, GEO
from baseline_inputs import baseline_input

class MountainTests(unittest.TestCase):
    def test_sources_and_original_arrays(self):
        for name in ['geography.json','terrain.json']:
            self.assertEqual((ROOT/'public/data'/name).read_bytes(),(baseline_input('urban-structure/baseline-p2/public/data')/name).read_bytes())
        tile=baseline_input('geodata')/Path(PLAN['sourceRasterUrl']).name
        with rasterio.open(tile) as raster:
            samples=np.asarray(PLAN['points'])[::41];cx,cy=GEO['center'];kx=1113.2*np.cos(np.radians(cy))
            x=((cx+samples[:,0]/kx)-raster.transform.c)/raster.transform.a-.5
            y=((cy+samples[:,1]/1113.2)-raster.transform.f)/raster.transform.e-.5
            expected=map_coordinates(raster.read(1).astype(float),[y,x],order=1)
        self.assertLess(np.max(np.abs(expected-np.asarray(PLAN['rawSourceMeters'])[::41])),.00001)
        self.assertEqual(PLAN['sourceResolutionArcSeconds'],1)
