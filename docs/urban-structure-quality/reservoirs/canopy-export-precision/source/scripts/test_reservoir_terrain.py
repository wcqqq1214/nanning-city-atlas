"""Analytic crest bounds, native sampling and independent coverage regressions."""
import sys
import ast
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
import hashlib
import json
import tempfile
import random
from unittest.mock import patch
import numpy as np
from shapely.geometry import Polygon,box
from check_reservoir_terrain import compare
from prepare_reservoir_terrain import crest_polygon,prepare,replacement_ranges,trim_inactive_south_rows,exclude_inactive_cells,inactive_base_cells,restoration_boundary_sides,restoration_edge_distance
import copy
from shapely.geometry import mapping
from prepare_building_shorelines import digest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reservoir_terrain import ReservoirTerrain
from reservoir_runtime import load


class Tests(unittest.TestCase):
    def inactive_fixture(self):
        points=[[x/2,y/2] for y in range(9) for x in range(9)];faces=[]
        for j in range(8):
            for i in range(8):
                a=j*9+i;faces.extend([[a,a+1,a+10],[a,a+10,a+9]])
        return {'points':points,'triangles':faces,'weights':[0]*81,'targetMeters':list(range(81)),
                'rawSourceMeters':list(range(81)),'materials':['reservoir_ground']*128,'bounds':[0,0,4,4],
                'columnRange':[0,4],'rowRange':[0,4],'landGeometry':mapping(box(0,0,4,4)),'statistics':{}}

    def test_inactive_selection_protects_water_active_land_dams_and_retained_values(self):
        p=self.inactive_fixture();p['weights'][10]=.1
        p['materials'][100]='dam_slope'
        geo={'bounds':p['bounds'],'water':[[list(box(2.5,2.5,3,3).exterior.coords)]]}
        exclusions,report=inactive_base_cells(p,geo,5,5)
        self.assertEqual(exclusions,[{'columnRange':[2,4],'rowRange':[2,4]}])
        self.assertEqual(report['denseTriangles'],32)
        self.assertEqual(report['detailBaseTriangles'],8)
        out=exclude_inactive_cells(copy.deepcopy(p),geo['bounds'],5,5,exclusions)
        self.assertEqual(out['statistics']['triangles'],96)
        for field in ['weights','targetMeters','rawSourceMeters']:
            self.assertEqual(out[field],[p[field][p['points'].index(q)] for q in out['points']])
        self.assertEqual(inactive_base_cells(p,geo,5,5,exclusions)[0],[])

    def test_inactive_cells_merge_exact_runs_and_decline_split_faces(self):
        p=self.inactive_fixture();geo={'bounds':p['bounds'],'water':[]}
        exclusions,report=inactive_base_cells(p,geo,5,5)
        self.assertEqual(exclusions,[{'columnRange':[0,4],'rowRange':[0,4]}])
        self.assertEqual(report['cells'],4)
        # A triangle spanning two candidate cells must not be silently cut.
        p['triangles'].append([0,8,40]);p['materials'].append('reservoir_ground')
        exclusions,report=inactive_base_cells(p,geo,5,5)
        self.assertEqual(exclusions,[{'columnRange':[0,4],'rowRange':[0,2]}])
        self.assertEqual(report['cells'],2)

    def test_sub_lattice_intersection_cannot_hide_a_face_crossing_the_cut(self):
        from prepare_block_grading import NativeXYGrid
        p=self.inactive_fixture();step=NativeXYGrid(p['bounds']).steps[0]
        # Integer native vertices enclose a sliver below y=2. Its intersection
        # is fractional in lattice units and used to round to empty.
        points=[[1,2-step],[1+step,2+step],[1+2*step,2+4*step]]
        first=len(p['points']);p['points']+=points
        p['triangles'].append([first,first+1,first+2]);p['materials'].append('reservoir_ground')
        for field in ['weights','targetMeters','rawSourceMeters']:p[field]+=[0]*3
        geo={'bounds':p['bounds'],'water':[]}
        exclusions,report=inactive_base_cells(p,geo,5,5)
        self.assertEqual(exclusions,[{'columnRange':[2,4],'rowRange':[0,4]}])
        self.assertEqual(report['cells'],2)
        with self.assertRaisesRegex(ValueError,'crosses a prepared face'):
            exclude_inactive_cells(p,geo['bounds'],5,5,[{'columnRange':[0,2],'rowRange':[2,4]}])

    def test_production_seam_audit_includes_internal_restored_cells(self):
        # Load the pure checker function without Blender or scene side effects.
        path=Path(__file__).resolve().parents[1]/'blender/check_reservoir_runtime.py'
        function=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='replacement_edges')
        env={'np':np};exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),env)
        triangles=[]
        for y in range(6):
            for x in range(6):
                if 2<=x<4 and 2<=y<4:continue
                a,b,c,d=[(x,y,0),(x+1,y,0),(x+1,y+1,0),(x,y+1,0)]
                triangles.extend([[a,b,c],[a,c,d]])
        outer=[[0,0],[6,0],[6,6],[0,6],[0,0]];hole=[[2,2],[4,2],[4,4],[2,4],[2,2]]
        payload={'bounds':[0,0,6,6],'replacementBoundarySegments':list(zip(outer,outer[1:]))+list(zip(hole,hole[1:]))}
        edges=list(env['replacement_edges'](np.asarray(triangles),payload))
        self.assertEqual(len(edges),32)
        self.assertEqual(sum(all(2<=q[0]<=4 and 2<=q[1]<=4 for q in edge) for edge in edges),8)

    def test_city_plinth_queries_the_actual_float32_cut_edge(self):
        east=184.68535258918888;stored=float(np.float32(east))
        p={'bounds':[east-.1,0,east,1],'points':[[stored-.1,0],[stored,0],[stored,1]],
           'triangles':[[0,1,2]],'weights':[1]*3,'targetMeters':[50]*3,'materials':['reservoir_ground'],
           'waterBodies':[],'restoredCityBoundarySides':['east']}
        terrain=ReservoirTerrain(p,{'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        args=(lambda x,y:0,p['bounds'],3,3,False,lambda *a:0)
        self.assertAlmostEqual(terrain.sample(east,.5,*args),.5)
        self.assertIsNone(terrain.sample(east+.001,.5,*args))
        p['restoredCityBoundarySides']=[]
        self.assertIsNone(terrain.sample(east,.5,*args))

    def test_city_cut_can_preserve_shore_height_without_opening_internal_seams(self):
        bounds=[2,2,10,8];city=[0,0,10,10]
        self.assertEqual(restoration_boundary_sides(bounds,city),[])
        sides=restoration_boundary_sides(bounds,city,True)
        self.assertEqual(sides,['east'])
        self.assertEqual(restoration_edge_distance([10,5],bounds,sides),300)
        self.assertEqual(restoration_edge_distance([2,5],bounds,sides),0)
        self.assertEqual(restoration_edge_distance([6,2],bounds,sides),0)
        self.assertEqual(restoration_boundary_sides([2,2,9,8],city,True),[])

    def test_crest_respects_mapped_footprint_and_end_setback(self):
        footprint=box(0,0,2,.5);crest=crest_polygon(footprint,4,10)
        self.assertTrue(footprint.covers(crest))
        self.assertAlmostEqual(crest.bounds[0],.1)
        self.assertAlmostEqual(crest.bounds[2],1.9)
        self.assertAlmostEqual(crest.bounds[3]-crest.bounds[1],.04)

    def test_narrow_footprint_cannot_force_a_crest(self):
        with self.assertRaises(ValueError):crest_polygon(box(0,0,.5,.1),4,10)

    def test_axis_setback_does_not_erode_a_narrow_dam_sideways(self):
        footprint=box(0,0,.5,.1)
        crest=crest_polygon(footprint,4,10,inset_mode='axis')
        self.assertTrue(footprint.covers(crest))
        self.assertAlmostEqual(crest.bounds[0],.1)
        self.assertAlmostEqual(crest.bounds[2],.4)
        self.assertAlmostEqual(crest.bounds[3]-crest.bounds[1],.04)

    def test_axis_setback_rejects_unfittable_width_or_endpoints(self):
        with self.assertRaisesRegex(ValueError,'width'):
            crest_polygon(box(0,0,.5,.02),4,10,inset_mode='axis')
        with self.assertRaisesRegex(ValueError,'axis'):
            crest_polygon(box(0,0,.2,.1),4,10,inset_mode='axis')
        with self.assertRaisesRegex(ValueError,'mode'):
            crest_polygon(box(0,0,.5,.1),4,10,inset_mode='unknown')

    def test_overwater_dam_cannot_be_silently_cut_out_of_embankment_mesh(self):
        ring=[[[0,0],[2,0],[2,2],[0,2],[0,0]]]
        geo={'center':[108,22],'water':[ring],
             'buildings':[{'id':'dam','sourceRef':'osm/way/1','use':'dam','rings':ring}]}
        source={'center':geo['center'],'metersPerUnit':100,
                'mesh':{'nativeFullRestoreMeters':100,'nativeRestoreMeters':150},
                'waterBodies':[{'geographyWaterIndex':0,'expectedPolygonSha256':digest(ring)}],
                'dams':[{'id':'dam','sourceRef':'osm/way/1','expectedFootprintSha256':digest(ring),'isEngineeringDesign':False}]}
        with self.assertRaisesRegex(ValueError,'dedicated structure'):
            prepare(geo,{},source,None)

    def test_city_edge_margin_requires_explicit_policy_and_preserves_grid(self):
        focus=box(2,7,4,10)
        with self.assertRaisesRegex(ValueError,'exceeds'):replacement_ranges([0,0,10,10],11,11,focus,200)
        ir,jr,clipped=replacement_ranges([0,0,10,10],11,11,focus,200,True)
        self.assertEqual((ir,jr,clipped),([0,6],[0,6],True))
        with self.assertRaisesRegex(ValueError,'inside'):replacement_ranges([0,0,10,10],11,11,box(2,7,4,11),200,True)
        with self.assertRaisesRegex(ValueError,'two-profile'):replacement_ranges([0,0,10,10],10,11,focus,200,True)

    def test_trim_only_inactive_border_preserves_every_retained_vertex_value(self):
        points=[[0,0],[2,0],[0,2],[2,2],[0,4],[2,4]]
        plan={'bounds':[0,0,2,4],'rowRange':[0,4],'points':points,
              'triangles':[[0,1,2],[1,3,2],[2,3,4],[3,5,4]],'materials':['ground']*4,
              'weights':[0,0,0,0,1,1],'targetMeters':[50,51,52,53,54,55],
              'rawSourceMeters':[60,61,62,63,64,65],'landGeometry':mapping(box(0,0,2,4)),'statistics':{}}
        out=trim_inactive_south_rows(copy.deepcopy(plan),[0,0,2,4],5,2)
        self.assertEqual(out['points'],points[2:]);self.assertEqual(out['targetMeters'],plan['targetMeters'][2:])
        self.assertEqual(out['weights'],plan['weights'][2:]);self.assertEqual(out['bounds'],[0,2,2,4])
        self.assertEqual(out['inactiveBorderTrim']['removedTriangles'],2)
        for i in [0,2]:
            bad=copy.deepcopy(plan);bad['weights'][i]=.1
            with self.assertRaisesRegex(ValueError,'modified terrain'):trim_inactive_south_rows(bad,[0,0,2,4],5,2)

    def test_excluded_corner_keeps_prior_patch_cells_and_zero_height_seam(self):
        points=[[x,y] for y in range(5) for x in range(5)];faces=[]
        for j in range(4):
            for i in range(4):
                a=j*5+i;faces.extend([[a,a+1,a+6],[a,a+6,a+5]])
        p={'points':points,'triangles':faces,'weights':[0]*25,'targetMeters':list(range(25)),
           'rawSourceMeters':list(range(25)),'materials':['reservoir_ground']*32,'bounds':[0,0,4,4],
           'columnRange':[0,4],'rowRange':[0,4],'landGeometry':mapping(box(0,0,4,4)),'statistics':{}}
        exclusions=[{'columnRange':[0,2],'rowRange':[2,4]}]
        out=exclude_inactive_cells(copy.deepcopy(p),[0,0,4,4],5,5,exclusions)
        self.assertEqual(out['statistics']['triangles'],24)
        model=ReservoirTerrain(out,{})
        self.assertFalse(model.replaces_cell(0,2));self.assertTrue(model.replaces_cell(2,2))
        for q,z in zip(out['points'],out['targetMeters']):self.assertEqual(z,p['targetMeters'][points.index(q)])
        bad=copy.deepcopy(p);bad['weights'][0]=1
        with self.assertRaisesRegex(ValueError,'modified reservoir'):exclude_inactive_cells(bad,[0,0,4,4],5,5,exclusions)

    def test_profile_boundaries_and_shared_native_sampler(self):
        plan={'points':[[0,0],[2,0],[0,2],[2,2]],'weights':[0,1,1,0],
              'targetMeters':[100]*4,'triangles':[[0,1,2],[1,3,2]],'materials':['ground']*2}
        terrain=ReservoirTerrain(plan,{'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        for mobile,base in [(False,.25),(True,.5)]:
            surface,collapsed=terrain.surface(lambda x,y:base,[0,0,2,2],3,3,mobile,lambda x,y,g,*args:g(x,y))
            self.assertEqual(collapsed,0)
            self.assertEqual(surface.sample(0,0),base)
            self.assertEqual(surface.sample(2,2),base)
            self.assertEqual(surface.sample(1,1),1)
            self.assertIsNone(surface.sample(-1,0))

    def test_invalid_blend_field_rejected(self):
        with self.assertRaises(ValueError):ReservoirTerrain({'points':[[0,0]],'weights':[1.1],'targetMeters':[90]}, {})

    def test_water_holes_and_cached_profile_surface(self):
        plan={'bounds':[0,0,2,2],'points':[[0,0],[2,0],[0,2]],'weights':[0]*3,
              'targetMeters':[100]*3,'triangles':[[0,1,2]],'materials':['ground'],
              'waterBodies':[{'levelMeters':90,'rings':[[[0,0],[2,0],[2,2],[0,2],[0,0]],
                                                       [[.2,.2],[.4,.2],[.4,.4],[.2,.4],[.2,.2]]]}]}
        terrain=ReservoirTerrain(plan,{'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        self.assertEqual(terrain.water_level(1,1),.9)
        self.assertIsNone(terrain.water_level(.3,.3))
        self.assertIsNone(terrain.water_level(3,3))
        ground=lambda x,y:.5
        coarse=lambda x,y,g,b,c,r,m:.7 if m else g(x,y)
        detail=terrain.surface(ground,[0,0,2,2],3,3,False,coarse)[0]
        self.assertIs(detail,terrain.surface(ground,(0,0,2,2),3,3,False,coarse)[0])
        self.assertEqual(terrain.sample(.3,.3,ground,[0,0,2,2],3,3,False,coarse),.5)
        self.assertEqual(terrain.sample(1.8,1.8,ground,[0,0,2,2],3,3,False,coarse),.9)
        self.assertAlmostEqual(terrain.sample(.3,.3,ground,[0,0,2,2],3,3,True,coarse),.7)

    def test_runtime_binding_rejects_stale_sources_and_wrong_dam(self):
        def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
        ring=[[[0,0],[1,0],[1,1],[0,1],[0,0]]]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'public/data').mkdir(parents=True);(root/'data').mkdir()
            geo={'center':[108,22],'water':[ring],'buildings':[{'id':'dam','use':'dam','sourceRef':'way/1','rings':ring}]}
            dem={'cols':5,'rows':5,'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1}
            for name,value in [('public/data/geography.json',geo),('public/data/terrain.json',dem),('data/source.json',{})]:
                (root/name).write_text(json.dumps(value))
            inputs={key:{'path':str(root/name),'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
                    for key,name in [('geography','public/data/geography.json'),('terrain','public/data/terrain.json'),('source','data/source.json')]}
            plan={'center':geo['center'],'columnRange':[0,2],'rowRange':[0,2],'points':[],'weights':[],'targetMeters':[],
                  'waterInterfaceAudit':{'schemaVersion':1,'neighbors':[],'unresolvedWaterIndices':[]},
                  'inputs':inputs,'runtimeInputs':{str(Path(v['path']).relative_to(root)):v['sha256'] for v in inputs.values()},
                  'dams':[{'id':'dam','sourceRef':'way/1','expectedFootprintSha256':digest(ring)}],
                  'waterBodies':[{'geographyWaterIndex':0,'rings':ring,'expectedPolygonSha256':digest(ring)}]}
            path=root/'data/reservoir-terrain-plan.json';path.write_text(json.dumps(plan))
            self.assertIsInstance(load(path,root),ReservoirTerrain)
            plan['waterInterfaceAudit']['unresolvedWaterIndices']=[1];path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'neighboring water interfaces'):load(path,root)
            plan['waterInterfaceAudit']['unresolvedWaterIndices']=[]
            plan['dams'][0]['id']='ordinary';path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'dam exclusion'):load(path,root)
            plan['dams'][0]['id']='dam';path.write_text(json.dumps(plan))
            (root/'data/source.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'Reprepare reservoir'):load(path,root)

    def test_dedicated_dam_is_removed_from_road_building_volumes(self):
        import road_inputs
        dam={'id':'mapped-dam','height':16,'rings':[[[0,0],[1,0],[0,1],[0,0]]]}
        ordinary={**dam,'id':'ordinary'}
        class Visibility:
            @staticmethod
            def building_visible(*args,**kwargs):return True
        env={'GEO':{'buildings':[dam,ordinary]},'height':lambda x,y:.5,'RAILWAY_BUILDINGS':set(),
             'city_visibility':Visibility,'inside_nanhu':lambda x,y:False,'NANHU_X':0,'NANHU_Y':0}
        with patch('reservoir_runtime.DAM_IDS',frozenset(['mapped-dam'])):
            levels=road_inputs.capture_building_levels(env)
        self.assertEqual([v[0] for v in levels],[1])

    def test_native_replacement_preserves_outside_faces_and_palette_rng(self):
        import terrain_mesh
        points=[[x,y] for y in range(3) for x in range(2,5)]
        triangles=[]
        for j in range(2):
            for i in range(2):
                a=j*3+i;triangles.extend([[a,a+1,a+4],[a,a+4,a+3]])
        payload={'id':'test','bounds':[2,0,4,2],'columnRange':[2,4],'rowRange':[2,4],
                 'points':points,'weights':[int(p==[3,1]) for p in points],
                 'targetMeters':[450]*9,'triangles':triangles,'materials':['reservoir_ground']*8,'waterBodies':[]}
        plan=ReservoirTerrain(payload,{'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        class Batch:
            def __init__(self,*args):self.faces=[];self.partition_override='';self.cell_override=None
            def face(self,vertices,key):self.faces.append((tuple(tuple(p) for p in vertices),key,self.partition_override))
        ground=lambda x,y:3.0
        coarse=lambda x,y,g,*args:g(x,y)
        def finished(x,y):return 9 if plan.contains(x,y) else ground(x,y)
        finished.unpatched=ground
        env={'Batch':Batch,'GEO':{'bounds':[0,0,4,4],'center':[0,0]},'DEM':{'landcover':[1]*25},
             'COLS':5,'ROWS':5,'height':ground,'unpatched_height':ground,'TERRAIN_MATERIALS':[],
             'replaces_terrain_cell':lambda i,j:False,'replaces_local_cell':lambda i,j:False,
             'replaces_mountain_cell':lambda i,j:False,'zhenning_terrain_patch':lambda *a:(-1,-1,-1,-1),
             'build_park_terrain':lambda *a:None,'build_local_terrain':lambda *a:None,'build_mountain_terrain':lambda *a:None,
             'NANHU_X':0,'NANHU_Y':0,'coarse_terrain_surface':coarse}
        for mobile in [False,True]:
            env['RNG']=random.Random(42);env['height']=ground
            with patch('terrain_mesh.RESERVOIR_PLAN',None),patch('reservoir_runtime.PLAN',None):
                before=terrain_mesh._build_native(env,mobile)
            state=env['RNG'].getstate()
            env['RNG']=random.Random(42);env['height']=finished
            with patch('terrain_mesh.RESERVOIR_PLAN',plan),patch('reservoir_runtime.PLAN',plan):
                after=terrain_mesh._build_native(env,mobile)
            self.assertEqual(state,env['RNG'].getstate())
            outside=[f for f in before.faces if not (sum(p[0] for p in f[0])/3>2 and sum(p[1] for p in f[0])/3<2)]
            self.assertEqual(outside,[f for f in after.faces if not f[2]])
            self.assertEqual(len([f for f in after.faces if f[2]]),8)
            for face,key,partition in after.faces:
                if not partition:continue
                x,y=[sum(p[k] for p in face)/3 for k in [0,1]]
                step=2 if mobile else 1
                cell=(int(x)//step,int((4-y))//step)
                old_keys={old_key for old_face,old_key,_ in before.faces
                          if (int(sum(p[0] for p in old_face)/3)//step,int(4-sum(p[1] for p in old_face)/3)//step)==cell}
                self.assertEqual(old_keys,{key})
            self.assertEqual(plan.sample(3,1,ground,[0,0,4,4],5,5,mobile,coarse),4.5)

    def test_native_replacement_rejects_overlapping_patches(self):
        import terrain_mesh
        class Plan:
            def replaces_cell(self,i,j):return True
        env={'Batch':lambda *a:None,'GEO':{'bounds':[0,0,2,2]},'DEM':{'landcover':[1]*9},
             'COLS':3,'ROWS':3,'height':lambda x,y:0,'RNG':random.Random(1),'TERRAIN_MATERIALS':[],
             'replaces_terrain_cell':lambda i,j:True,'replaces_local_cell':lambda i,j:False,'replaces_mountain_cell':lambda i,j:False}
        with patch('reservoir_runtime.PLAN',Plan()):
            with self.assertRaisesRegex(ValueError,'overlaps'):terrain_mesh._build_native(env,False)

    def test_checker_rejects_filled_island(self):
        faces=np.array([[[0,0,0],[2,0,0],[0,2,0]],[[2,0,0],[2,2,0],[0,2,0]]])
        expected=Polygon(box(0,0,2,2).exterior.coords,[box(.5,.5,1,1).exterior.coords])
        with self.assertRaisesRegex(ValueError,'coverage'):compare(faces,expected)

    def test_checker_rejects_overlapping_faces(self):
        face=np.array([[[0,0,0],[1,0,0],[0,1,0]]])
        with self.assertRaisesRegex(ValueError,'Overlapping'):compare(np.concatenate([face,face]),Polygon(face[0,:,:2]))


if __name__=='__main__':unittest.main()
