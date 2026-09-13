"""Geographic coverage, source elevations, actual triangle sampling and path support."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from mountain_terrain import PLAN, vertex_heights, surface, build_paths, water_level
from forest_canopy import coarse_terrain_surface
from test_waterfront import ground, GEO, DEM


class Recorder:
    def __init__(self):self.faces=[]
    def face(self,points,key):self.faces.append((np.asarray(points),key))


class MountainTests(unittest.TestCase):
    def test_sources_and_original_arrays(self):
        for path,digest in PLAN['inputHashes'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
        for name in ['geography.json','terrain.json']:
            self.assertEqual((ROOT/'public/data'/name).read_bytes(),(ROOT/'work/urban-structure/baseline-p2/public/data'/name).read_bytes())
        tile=ROOT/'work/geodata'/Path(PLAN['sourceRasterUrl']).name
        with rasterio.open(tile) as raster:
            samples=np.asarray(PLAN['points'])[::41];cx,cy=GEO['center'];kx=1113.2*np.cos(np.radians(cy))
            x=((cx+samples[:,0]/kx)-raster.transform.c)/raster.transform.a-.5
            y=((cy+samples[:,1]/1113.2)-raster.transform.f)/raster.transform.e-.5
            expected=map_coordinates(raster.read(1).astype(float),[y,x],order=1)
        self.assertLess(np.max(np.abs(expected-np.asarray(PLAN['rawSourceMeters'])[::41])),.00001)
        self.assertEqual(PLAN['sourceResolutionArcSeconds'],1)

    def test_land_and_path_coverage(self):
        water=unary_union([Polygon(r[0],r[1:]) for r in GEO['water']])
        faces=[Polygon([PLAN['points'][i] for i in ids]) for ids in PLAN['triangles']]
        land=unary_union(faces);expected=box(*PLAN['bounds']).difference(water)
        self.assertLess(land.symmetric_difference(expected).area,1e-5)
        self.assertLess(sum(p.area for p in faces)-land.area,1e-7)
        paths=unary_union([p for p,key in zip(faces,PLAN['materials']) if key in ['walk','steps','service']])
        footprint=unary_union([Polygon(r[0],r[1:]) for rs in PLAN['pathFootprints'].values() for r in rs])
        self.assertLess(paths.symmetric_difference(footprint).area,1e-5)
        self.assertLess(paths.intersection(water.buffer(-1e-6)).area,1e-8)
        source=json.loads((ROOT/'data/qingxiu-paths-source.json').read_text())
        identifiers={e['id'] for e in source['elements']}
        self.assertTrue(all(r['osmId'] in identifiers for r in PLAN['paths']))
        self.assertGreater(len(PLAN['paths']),50)

    def test_each_triangle_sampler_and_outer_seam(self):
        for mobile in [False,True]:
            levels=vertex_heights(ground,tuple(GEO['bounds']),DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
            for ids in PLAN['triangles']:
                p=np.mean([PLAN['points'][i] for i in ids],axis=0)
                actual=surface(*p,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
                self.assertIsNotNone(actual)
                # Sub-square-centimetre clipped slivers amplify floating-point
                # centroid error; retain an explicit 0.1 mm world-space limit.
                self.assertAlmostEqual(actual,float(np.mean([levels[i] for i in ids])),delta=1e-6)
            w,s,e,n=PLAN['bounds'];edges=0
            for i,(x,y) in enumerate(PLAN['points']):
                if min(abs(x-w),abs(x-e),abs(y-s),abs(y-n))<1e-6:
                    edges+=1
                    self.assertAlmostEqual(levels[i],coarse_terrain_surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile),places=6)
            self.assertGreater(edges,100)

    def test_paths_follow_relief_and_platform_is_local(self):
        for mobile in [False,True]:
            b=Recorder();build_paths(b,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
            heights=[]
            for face,key in b.faces:
                if key=='park_edge':continue
                for x,y,z in face:
                    support=surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
                    self.assertIsNotNone(support)
                    self.assertAlmostEqual(z-support,.006,places=5);heights.append(z)
            self.assertGreater(max(heights)-min(heights),1,'Park paths were flattened across the hill')
        center=Point(PLAN['towerCenterSceneXY']);radius=(PLAN['source']['tower']['platformRadiusMeters']+PLAN['source']['tower']['platformBlendMeters'])/100
        self.assertTrue(all(weight==0 for point,weight in zip(PLAN['points'],PLAN['platformWeights']) if Point(point).distance(center)>radius+1e-6))
        core=[z for z,weight in zip(PLAN['targetMeters'],PLAN['platformWeights']) if weight==1]
        self.assertGreater(len(core),4);self.assertLess(max(core)-min(core),1e-6)

    def test_mountain_lakes_have_local_levels_and_supported_banks(self):
        self.assertGreaterEqual(len(PLAN['waterBodies']),4)
        for lake in PLAN['waterBodies']:
            shape=Polygon(lake['rings'][0],lake['rings'][1:]);p=shape.representative_point()
            stage=water_level(p.x,p.y)
            self.assertGreater(stage,.26+.25)
            self.assertEqual(lake['rings'],GEO['water'][lake['geographyWaterIndex']])
            selected=[i for i,p in enumerate(PLAN['points']) if Point(p).distance(shape.boundary)<2e-6]
            self.assertGreater(len(selected),4)
            for mobile in [False,True]:
                levels=vertex_heights(ground,tuple(GEO['bounds']),DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
                gaps=np.asarray(levels)[selected]-stage
                self.assertGreater(float(gaps.min()),.005,'The mountain shore fell back to the river datum')
                self.assertLess(float(gaps.max()),.012,'A cliff remains around a local lake')
        self.assertIsNone(water_level(15,-14),'Mountain water overrides escaped to the Yongjiang river')


if __name__=='__main__':unittest.main()
