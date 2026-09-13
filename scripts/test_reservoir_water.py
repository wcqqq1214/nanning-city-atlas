"""Display transitions must be continuous and queries must use exported faces."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
import ast
import numpy as np
from shapely import union_all
from shapely.geometry import box,LineString,Polygon
from shapely.ops import unary_union,polygonize
from check_reservoir_terrain import compare,shared_shoreline
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reservoir_water import WaterLevelField
from reservoir_terrain import ReservoirTerrain
from prepare_geodata import coords
from prepare_reservoir_terrain import prepare_water_mesh,water_mesh_lines
from prepare_block_grading import NativeXYGrid,triangulate_stations


class Tests(unittest.TestCase):
    def fixture(self):
        a,b=box(0,0,1,1),box(1,0,2,1)
        return {'levelMeters':80,'rings':coords(box(0,0,2,1)),
                'transitionWidthMeters':30,'waterMeshSpacingMeters':30,
                'levelRegions':[{'rings':coords(a),'levelMeters':80},{'rings':coords(b),'levelMeters':84}]}

    def test_join_is_continuous_and_distant_interiors_keep_source_levels(self):
        f=WaterLevelField(self.fixture())
        self.assertEqual(f.meters(.5,.5),80);self.assertEqual(f.meters(1.5,.5),84)
        self.assertEqual(f.meters(1,.5),82)
        self.assertAlmostEqual(f.meters(1-1e-7,.5),f.meters(1+1e-7,.5),places=10)
        levels=[f.meters(x,.5) for x in np.linspace(.5,1.5,101)]
        self.assertTrue(all(a<=b for a,b in zip(levels,levels[1:])))

    def test_region_coverage_is_required(self):
        e=self.fixture();e['levelRegions'].pop()
        with self.assertRaisesRegex(ValueError,'cover'):prepare_water_mesh(e,box(0,0,2,1),NativeXYGrid([0,0,2,1]),LineString([(0,0),(2,0)]))

    def test_native_water_mesh_coverage_and_sampler(self):
        e=self.fixture();native=NativeXYGrid([0,0,2,1])
        # Additional land-side boundary station must survive water triangulation.
        border=LineString([(0,0),(.125,0),(2,0),(2,1),(0,1),(0,0)])
        e['waterMesh']=prepare_water_mesh(e,box(0,0,2,1),native,native.encode(border))
        self.assertIn([.125,0],e['waterMesh']['points'])
        p=ReservoirTerrain({'points':[],'weights':[],'targetMeters':[],'waterBodies':[e]},
                           {'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        mesh=p.water_surface(0);compare(np.asarray(mesh.triangles),box(0,0,2,1))
        for face in mesh.triangles:
            xyz=np.mean(face,axis=0)
            self.assertAlmostEqual(p.water_height(0,*xyz[:2]),xyz[2],places=10)
        self.assertTrue(p.custom_water_contains(.5,.5));self.assertFalse(p.custom_water_contains(-1,.5))
        self.assertEqual(p.custom_water_triangles(),mesh.triangles)

    def test_join_refinement_reduces_height_interpolation_error(self):
        entry=self.fixture();polygon=box(0,0,2,1);native=NativeXYGrid([0,0,2,1]);field=WaterLevelField(entry)
        def error(mesh):
            xyz=np.column_stack([mesh['points'],mesh['targetMeters']]);faces=xyz[mesh['triangles']]
            return max(abs(p[2]-field.meters(*p[:2])) for p in faces.mean(axis=1))
        coarse=prepare_water_mesh(entry,polygon,native,native.encode(polygon.boundary))
        entry['transitionMeshSpacingMeters']=5
        fine=prepare_water_mesh(entry,polygon,native,native.encode(polygon.boundary))
        compare(np.column_stack([fine['points'],fine['targetMeters']])[fine['triangles']],polygon)
        self.assertLess(error(fine),error(coarse)/2)
        self.assertEqual(min(fine['targetMeters']),80);self.assertEqual(max(fine['targetMeters']),84)
        entry['transitionMeshSpacingMeters']=30
        with self.assertRaisesRegex(ValueError,'finer'):prepare_water_mesh(entry,polygon,native,native.encode(polygon.boundary))

    def test_city_loop_replaces_old_flat_faces_with_actual_continuous_mesh(self):
        e=self.fixture();e['waterMesh']={'points':[[0,0],[2,0],[0,1],[2,1]],
            'targetMeters':[80,84,80,84],'triangles':[[0,1,2],[1,3,2]]}
        p=ReservoirTerrain({'points':[],'weights':[],'targetMeters':[],'waterBodies':[e]},
                           {'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        batches={}
        class Batch:
            def __init__(self,name,*args):self.faces=[];batches[name]=self
            def face(self,face,material):self.faces.append(tuple(tuple(v) for v in face))
            def finish(self):pass
        path=Path(__file__).resolve().parents[1]/'blender/build_city.py';tree=ast.parse(path.read_text())
        start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='water' for t in n.targets))
        end=next(i for i,n in enumerate(tree.body[start:],start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                 and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name)
                 and n.value.func.value.id=='custom_water' and n.value.func.attr=='finish')
        outside=[[3,0],[4,0],[3,1]]
        env={'Batch':Batch,'GEO':{'waterTriangles':[[[0,0],[2,0],[0,1]],[[2,0],[2,1],[0,1]],outside]},
             'custom_water_contains':p.custom_water_contains,'custom_water_triangles':p.custom_water_triangles,
             'reservoir_water_level':p.water_level,'mountain_water_level':lambda x,y:None}
        exec(compile(ast.Module(body=tree.body[start:end+1],type_ignores=[]),str(path),'exec'),env)
        self.assertEqual(batches['Water'].faces,[tuple((x,y,.26) for x,y in outside)])
        self.assertEqual(batches['Reservoir_water_custom'].faces,p.custom_water_triangles())

    def test_snapped_oblique_shore_uses_the_same_cells_on_both_sides(self):
        bounds=[100,100,104,104];native=NativeXYGrid(bounds)
        lake=Polygon([(100.7,101.3),(102.8,100.6),(103.1,102.9),(101.4,103.2)])
        entry={'levelMeters':80,'levelRegions':[{'rings':coords(lake),'levelMeters':80}],
               'transitionWidthMeters':30,'waterMeshSpacingMeters':30}
        lake=Polygon(entry['levelRegions'][0]['rings'][0]);land=native.encode(box(*bounds)).difference(native.encode(lake))
        lines=[land.boundary]+water_mesh_lines(entry,lake,native)
        for x in np.arange(100.17,104,.31):
            lines.append(native.encode(LineString([(x,100),(x,104)])).intersection(land))
        network=union_all(lines,grid_size=1);cells=list(polygonize(network));faces=[]
        for cell in cells:
            if not land.covers(cell.representative_point()):continue
            cell=native.decode(cell);rings=[list(r.coords)[:-1] for r in [cell.exterior,*cell.interiors]]
            xy=np.asarray([p for r in rings for p in r]);ends=np.cumsum([len(r) for r in rings],dtype=np.uint32)
            for tri in triangulate_stations(xy,ends):
                faces.append([[*xy[i],.002] for i in tri])
        mesh=prepare_water_mesh(entry,lake,native,network,cells)
        water=np.asarray([[*p,0] for p in mesh['points']])[mesh['triangles']]
        result=shared_shoreline(np.asarray(faces),water,.2,bounds)
        self.assertGreater(result['sharedNativeEdges'],40)

    def test_shoreline_checker_rejects_different_segmentation_even_with_same_coverage(self):
        # Water occupies the lower half, land upper half; outer edges leave the patch.
        water=np.asarray([[[0,0,0],[2,0,0],[0,1,0]],[[2,0,0],[2,1,0],[0,1,0]]],float)
        land=np.asarray([[[0,1,.002],[2,1,.002],[0,2,.002]],[[2,1,.002],[2,2,.002],[0,2,.002]]],float)
        result=shared_shoreline(land,water,.2,[0,0,2,2]);self.assertEqual(result['sharedNativeEdges'],1)
        split=np.asarray([[[0,0,0],[2,0,0],[1,1,0]],[[0,0,0],[1,1,0],[0,1,0]],[[2,0,0],[2,1,0],[1,1,0]]],float)
        compare(split,box(0,0,2,1))
        with self.assertRaisesRegex(ValueError,'exact shoreline'):shared_shoreline(land,split,.2,[0,0,2,2])


if __name__=='__main__':unittest.main()
