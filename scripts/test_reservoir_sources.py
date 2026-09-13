"""Analytic raster and source-screening checks independent of Nanning source values."""
import copy
import unittest

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box
from audit_reservoir_sources import SourceRaster, audit, display_level_candidate, statistics


class RasterTests(unittest.TestCase):
    def setUp(self):
        self.memory = MemoryFile()
        self.raster = self.memory.open(driver='GTiff', width=5, height=5, count=1,
                                       dtype='float64', crs='EPSG:4326', nodata=-9999,
                                       transform=from_origin(0, .005, .001, .001))
        self.data = np.arange(25, dtype=float).reshape(5, 5)+100
        self.raster.write(self.data, 1)
        self.sampler = SourceRaster(self.raster, [0, 0])
        self.spacing = 1.1132

    def tearDown(self):
        self.raster.close()
        self.memory.close()

    def test_native_centers_holes_and_mask(self):
        s = self.spacing
        outer = box(0, 0, 5*s, 5*s)
        hole = box(2*s, 2*s, 3*s, 3*s)
        polygon = Polygon(outer.exterior.coords, [hole.exterior.coords])
        self.data[0, 0] = -9999
        self.raster.write(self.data, 1)
        values = self.sampler.pixels(polygon)
        self.assertEqual(len(values), 23)
        self.assertNotIn(112, values)
        self.assertNotIn(-9999, values)

    def test_tiny_shape_does_not_invent_pixels(self):
        self.assertEqual(len(self.sampler.pixels(box(.01, .01, .02, .02))), 0)
        self.assertEqual(len(self.sampler.pixels(Polygon())), 0)

    def test_bilinear_profile_on_analytic_plane(self):
        s = self.spacing
        result = self.sampler.profile(box(1.5*s, 2*s, 3.5*s, 3*s))
        for (x, y), z in zip(result['pointsSceneXY'], result['sourceMeters']):
            expected = 100+5*(4.5-y/s)+(x/s-.5)
            self.assertAlmostEqual(z, expected, places=9)

    def test_inventory_includes_legacy_and_source_tagged_dams(self):
        elements, buildings = [], []
        for i, (use, prepared) in enumerate([('dam', True), ('dam', False), ('unknown', False)]):
            x = .001+i*.001
            lonlat = [(x, .002), (x+.0003, .002), (x+.0003, .0023), (x, .0023), (x, .002)]
            elements.append({'type': 'way', 'id': i+1, 'tags': {'waterway': 'dam', 'building': 'dam'},
                             'geometry': [{'lon': x, 'lat': y} for x, y in lonlat]})
            buildings.append({'id': 'dam/'+str(i), 'sourceRef': 'osm/way/'+str(i+1), 'use': use,
                              'qualityGeometry': prepared, 'rings': [[[x*1113.2, y*1113.2] for x, y in lonlat]],
                              'height': 16})
        terrain = {k: 0 for k in ['verticalDatumMeters', 'verticalOffset', 'verticalExaggeration',
                                 'sourceUrl', 'sourceSha256', 'sourceResolutionArcSeconds']}
        raster_name = self.raster.name
        self.raster.close()
        result = audit({'center': [0, 0], 'bounds': [0, 0, 5.566, 5.566], 'water': [],
                        'buildings': buildings}, terrain, {'elements': elements}, raster_name)
        self.assertEqual(result['scope']['mappedDamRecords'], 3)
        self.assertEqual(result['scope']['preparedDamRecords'], 1)
        self.assertEqual(result['scope']['legacyDamRecords'], 2)
        self.assertTrue(all(r['engineeringDamHeightMeters'] is None for r in result['records']))


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.water = {'sourceRef': 'osm/way/1', 'displayMatches': [
            {'index': 2, 'sourceCoverageFraction': .99, 'displayCoverageFraction': .99}],
            'rawPixelStatisticsMetersByInset': {str(k): statistics(np.repeat(96, 30)) for k in [0, 10, 30]}}
        self.records = [{'id': 'dam/1', 'nearbyWaters': [
            {'sourceRef': 'osm/way/1', 'sharedBoundaryMeters': 20}]}]

    def test_stable_interior_is_only_display_candidate(self):
        result = display_level_candidate(self.water, self.records)
        self.assertEqual(result['levelMeters'], 96)
        self.assertFalse(result['isEngineeringLevel'])
        self.assertFalse(result['appliedToRuntime'])

    def test_proximity_or_merged_water_is_not_enough(self):
        self.assertIsNone(display_level_candidate(self.water, [])['levelMeters'])
        self.water['displayMatches'][0]['displayCoverageFraction'] = .03
        self.assertIsNone(display_level_candidate(self.water, self.records)['levelMeters'])

    def test_sparse_heterogeneous_or_unstable_pixels_need_review(self):
        for values in [np.repeat(96, 3), np.linspace(95, 99, 30), np.repeat(98, 30)]:
            water = copy.deepcopy(self.water)
            water['rawPixelStatisticsMetersByInset']['30'] = statistics(values)
            self.assertIsNone(display_level_candidate(water, self.records)['levelMeters'])


if __name__ == '__main__':
    unittest.main()
