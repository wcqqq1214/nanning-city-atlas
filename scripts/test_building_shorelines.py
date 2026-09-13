"""Source restoration must preserve islands, unaffected geometry and mapped heights."""
import copy
import math
import unittest

from shapely.geometry import Polygon,box
from shapely.ops import unary_union
from prepare_geodata import coords,triangulate_water
from prepare_building_shorelines import restore,digest,face_key,permitted_water_overlap,replacement_water
from check_building_shorelines import check


class Tests(unittest.TestCase):
    def fixture(self):
        center=[108.3,22.825];kx=1113.2*math.cos(math.radians(center[1]))
        def feature(identity,shape):
            return {'type':'way','id':identity,'tags':{},'geometry':[
                {'lon':center[0]+x/kx,'lat':center[1]+y/1113.2} for x,y in shape.exterior.coords]}
        old=box(0,0,2,2);far=box(5,5,6,6)
        new=Polygon([[-.2,0],[2,0],[2,.7],[1.5,.7],[1.5,1.3],[2,1.3],[2,2],[-.2,2]])
        footprint=box(1.45,.8,1.9,1.2);source_footprint=box(1.6,.8,1.9,1.2)
        b={'id':'building','sourceRef':'osm/way/2','rings':coords(footprint),'height':12,
           'heightSource':{'kind':'height','value':12},'mappedHeight':True}
        geo={'metersPerUnit':100,'center':center,'bounds':[-10,-10,10,10],
             'water':[coords(old),coords(far)],'waterTriangles':triangulate_water(old)+triangulate_water(far),
             'buildings':[b],'parks':[coords(box(-1,-1,0,3))],'urban':[],'inferredUrban':[],
             'trees':[[8,8,.2]],'roads':[{'points':[[7,7],[8,7]]}],'metadata':{'preserve':True}}
        source={'id':'test','metersPerUnit':100,'center':center,'precisionMeters':.1,'minimumPolygonOverlapFraction':.9,
                'water':[{'geographyWaterIndex':0,'expectedPolygonSha256':digest(geo['water'][0]),
                          'sourceRef':'osm/way/1','feature':feature(1,new)}],
                'buildings':[{'id':'building','sourceRef':'osm/way/2','expectedFootprintSha256':digest(b['rings']),
                              'feature':feature(2,source_footprint)}],'affectedBuildingIds':['building']}
        return geo,source,new,source_footprint

    def test_restored_shared_geometry_has_no_water_overlap_and_preserves_heights(self):
        geo,source,water,footprint=self.fixture();out=restore(geo,source);b=out['buildings'][0]
        self.assertLess(Polygon(b['rings'][0]).symmetric_difference(footprint).area,1e-10)
        self.assertLess(Polygon(out['water'][0][0]).symmetric_difference(water).area,1e-10)
        self.assertEqual(out['shorelineRestoration']['affectedBuildings'][0]['afterWaterOverlapSquareMeters'],0)
        for key in ['height','heightSource','mappedHeight']:self.assertEqual(b[key],geo['buildings'][0][key])

    def test_untouched_water_faces_and_nonparticipating_data_stay_exact(self):
        geo,source,_,_=self.fixture();out=restore(geo,source)
        for key in ['roads','trees','metadata','center','bounds']:self.assertEqual(out[key],geo[key])
        self.assertEqual(out['water'][1],geo['water'][1])
        self.assertEqual(out['waterTriangles'][-2:],geo['waterTriangles'][-2:])
        self.assertEqual(geo['buildings'][0]['rings'],self.fixture()[0]['buildings'][0]['rings'])

    def test_triangles_cover_restored_water_and_building_without_overlap(self):
        geo,source,_,_=self.fixture();out=restore(geo,source)
        for shapes,target in [(out['waterTriangles'],unary_union([Polygon(r[0],r[1:]) for r in out['water']])),
                              (out['buildings'][0]['meshRoofTriangles'],Polygon(out['buildings'][0]['rings'][0]))]:
            faces=[Polygon(t) for t in shapes];union=unary_union(faces)
            self.assertTrue(all(p.area>0 for p in faces))
            self.assertLess(sum(p.area for p in faces)-union.area,1e-10)
            self.assertLess(union.symmetric_difference(target).area,1e-7)

    def test_landcover_changes_only_where_source_restoration_adds_water(self):
        geo,source,new,_=self.fixture();out=restore(geo,source)
        old=Polygon(geo['parks'][0][0]);after=unary_union([Polygon(r[0],r[1:]) for r in out['parks']])
        gained=new.difference(Polygon(geo['water'][0][0]))
        self.assertLess(after.symmetric_difference(old.difference(gained)).area,1e-10)
        self.assertLess(after.intersection(new).area,1e-10)

    def test_stale_source_and_missing_water_triangles_are_rejected(self):
        geo,source,_,_=self.fixture()
        stale=copy.deepcopy(geo);stale['water'][0][0][0][0]+=.001
        with self.assertRaisesRegex(ValueError,'stale'):restore(stale,source)
        stale=copy.deepcopy(geo);stale['waterTriangles']=stale['waterTriangles'][1:]
        with self.assertRaisesRegex(ValueError,'triangles'):restore(stale,source)
        stale=copy.deepcopy(source);stale['water'][0]['feature']['id']=3
        with self.assertRaisesRegex(ValueError,'identity'):restore(geo,stale)

    def test_islands_cannot_disappear_during_source_restoration(self):
        geo,source,_,_=self.fixture();shape=Polygon(geo['water'][0][0],[[[.2,.2],[.4,.2],[.4,.4],[.2,.4],[.2,.2]]])
        geo['water'][0]=coords(shape);source['water'][0]['expectedPolygonSha256']=digest(geo['water'][0])
        with self.assertRaisesRegex(ValueError,'island'):restore(geo,source)

    def test_repeat_preparation_is_deterministic_and_reapplication_is_rejected(self):
        geo,source,_,_=self.fixture();first=restore(geo,source)
        self.assertEqual(first,restore(geo,source))
        with self.assertRaisesRegex(ValueError,'frozen'):restore(first,source)

    def test_checker_rejects_changed_surroundings_and_invented_source_geometry(self):
        geo,source,_,_=self.fixture();candidate=restore(geo,source);check(geo,candidate,source)
        changed=copy.deepcopy(candidate);changed['roads']=[]
        with self.assertRaises(AssertionError):check(geo,changed,source)
        changed=copy.deepcopy(candidate);changed['waterTriangles'].pop()
        with self.assertRaises(AssertionError):check(geo,changed,source)
        changed=copy.deepcopy(candidate);changed['buildings'][0]['height']=15
        with self.assertRaises(AssertionError):check(geo,changed,source)
        changed=copy.deepcopy(candidate);changed['water'][0][0][0][0]+=.001
        with self.assertRaises(AssertionError):check(geo,changed,source)

    def test_reservoir_batch_preserves_previous_restoration_record(self):
        geo,source,_,_=self.fixture()
        geo['shorelineRestoration']={'id':'previous-batch','sourceHash':'previous-source'}
        out=restore(geo,source,record_key='reservoirShorelineRestoration')
        check(geo,out,source,record_key='reservoirShorelineRestoration')
        self.assertEqual(out['shorelineRestoration'],geo['shorelineRestoration'])
        with self.assertRaisesRegex(ValueError,'frozen'):
            restore(out,source,record_key='reservoirShorelineRestoration')
        changed=copy.deepcopy(out);changed['shorelineRestoration']['sourceHash']='changed'
        with self.assertRaises(AssertionError):
            check(geo,changed,source,record_key='reservoirShorelineRestoration')

    def test_self_touching_landcover_keeps_surface_without_overlay_lines(self):
        geo,source,new,_=self.fixture()
        park=Polygon([(-1,-1),(0,-1),(0,1),(.5,1),(0,1),(0,3),(-1,3)])
        self.assertFalse(park.is_valid)
        geo['parks']=[coords(park)]
        expected=park.difference(new.difference(Polygon(geo['water'][0][0])))
        self.assertEqual(expected.geom_type,'GeometryCollection')
        out=restore(geo,source)
        surfaces=[Polygon(r[0],r[1:]) for r in out['parks']]
        self.assertTrue(all(p.is_valid for p in surfaces))
        self.assertLess(unary_union(surfaces).symmetric_difference(expected).area,1e-10)
        check(geo,out,source)

    def test_only_explicit_source_layered_dam_retains_exact_overlap(self):
        geo,source,_,_=self.fixture()
        # Place the source footprint inside source water as a mapped layer-1 dam.
        b=source['buildings'][0];b['feature']=copy.deepcopy(source['water'][0]['feature'])
        b['feature']['id']=2;b['feature']['tags']={'building':'dam','waterway':'dam','layer':'1'}
        b['waterRelationship']='mapped-overwater-structure'
        b['expectedWaterOverlapSquareMeters']=4.1*10000
        out=restore(geo,source);check(geo,out,source)
        for tags in [{},{'building':'dam','waterway':'dam','layer':'0'},
                     {'building':'yes','waterway':'dam','layer':'1'}]:
            changed=copy.deepcopy(source);changed['buildings'][0]['feature']['tags']=tags
            with self.assertRaisesRegex(ValueError,'source-layered'):restore(geo,changed)
        changed=copy.deepcopy(source);changed['buildings'][0]['expectedWaterOverlapSquareMeters']+=1
        with self.assertRaisesRegex(ValueError,'overlap differs'):restore(geo,changed)
        changed=copy.deepcopy(source);del changed['buildings'][0]['waterRelationship']
        with self.assertRaisesRegex(ValueError,'overlap differs'):restore(geo,changed)

    def test_rollout_preserves_both_earlier_restoration_records(self):
        geo,source,_,_=self.fixture()
        for key in ['shorelineRestoration','reservoirShorelineRestoration']:
            geo[key]={'id':key,'sourceHash':'frozen'}
        out=restore(geo,source,record_key='reservoirRolloutRestoration')
        check(geo,out,source,record_key='reservoirRolloutRestoration')
        for key in ['shorelineRestoration','reservoirShorelineRestoration']:self.assertEqual(out[key],geo[key])

    def test_local_dam_clip_preserves_merged_water_and_intersection_digits(self):
        def feature(identity,p,tags):
            return {'type':'way','id':identity,'tags':tags,
                    'geometry':[{'lon':x,'lat':y} for x,y in p.exterior.coords]}
        dam=Polygon([(0,0),(2,0),(0,1)])
        before=Polygon([(-1,-1),(3,-1),(3,.111),(-1,.123)])
        neighbor=box(0,-1,2,0)
        entry={'sourceRef':'osm/way/1','operation':'clip-source-dam-footprint',
               'feature':feature(1,dam,{'building':'dam','waterway':'dam'}),
               'sharedWaterFeature':feature(2,neighbor,{'natural':'water'}),
               'expectedRemovedSquareMeters':before.intersection(dam).area*10000}
        after,precision=replacement_water(entry,before,lambda x,y:(x,y),box(-10,-10,10,10))
        self.assertEqual(precision,9)
        self.assertLess(after.symmetric_difference(before.difference(dam)).area,1e-12)
        self.assertLess(after.intersection(dam).area,1e-12)
        mesh=unary_union([Polygon(t) for t in triangulate_water(after,precision=precision)])
        self.assertLess(mesh.symmetric_difference(after).area*10000,1e-5)
        # Reverting to normal source rounding would move the shared edge.
        rounded=unary_union([Polygon(t) for t in triangulate_water(after)])
        self.assertGreater(rounded.symmetric_difference(after).area*10000,.01)
        changed=copy.deepcopy(entry);changed['expectedRemovedSquareMeters']+=1
        with self.assertRaisesRegex(ValueError,'correction area'):replacement_water(changed,before,lambda x,y:(x,y),box(-10,-10,10,10))
        changed=copy.deepcopy(entry);changed['feature']['tags']['layer']='1'
        with self.assertRaisesRegex(ValueError,'land dam'):replacement_water(changed,before,lambda x,y:(x,y),box(-10,-10,10,10))

    def test_remove_only_reviewed_newly_wet_tree_and_preserve_order_and_stats(self):
        geo,source,_,_=self.fixture();geo['trees']=[[-.1,1,.3],[8,8,.2],[7,8,.4]]
        geo['stats']={'trees':3,'mappedBuildings':1}
        source['treeRemovals']=[{'index':0,'expectedTree':geo['trees'][0], 'geographyWaterIndex':0}]
        out=restore(geo,source);check(geo,out,source)
        self.assertEqual(out['trees'],geo['trees'][1:]);self.assertEqual(out['stats'],{'trees':2,'mappedBuildings':1})
        changed=copy.deepcopy(source);changed['treeRemovals'][0]['index']=1
        with self.assertRaisesRegex(ValueError,'stale'):restore(geo,changed)
        changed['treeRemovals'][0]['expectedTree']=geo['trees'][1]
        with self.assertRaisesRegex(ValueError,'newly inside'):restore(geo,changed)
        bad=copy.deepcopy(out);bad['trees'].reverse()
        with self.assertRaisesRegex(AssertionError,'Unrelated trees'):check(geo,bad,source)

    def test_source_union_preserves_join_and_rejects_wrong_part_or_duplicate(self):
        def feature(identity,p):
            return {'type':'way','id':identity,'geometry':[{'lon':x,'lat':y} for x,y in p.exterior.coords]}
        a,b=box(0,0,1,1),box(1,0,2,1);components=[]
        from prepare_geodata import geom_for
        for i,p in enumerate([a,b]):
            f=feature(i,p);part=geom_for(f,project=lambda x,y:(x,y),clip=box(-10,-10,10,10))
            components.append({'feature':f,'sourceRef':f'osm/way/{i}','sourcePart':0,'expectedSourcePartSha256':digest(coords(part))})
        entry={'operation':'restore-source-union','components':components}
        out,_=replacement_water(entry,box(0,0,2,1),lambda x,y:(x,y),box(-10,-10,10,10))
        self.assertEqual(out.area,2)
        changed=copy.deepcopy(entry);changed['components'][0]['expectedSourcePartSha256']='stale'
        with self.assertRaisesRegex(ValueError,'component changed'):replacement_water(changed,a,lambda x,y:(x,y),box(-10,-10,10,10))
        changed=copy.deepcopy(entry);changed['components'].append(changed['components'][0])
        with self.assertRaisesRegex(ValueError,'overlap'):replacement_water(changed,a,lambda x,y:(x,y),box(-10,-10,10,10))

    def test_neighbor_batch_preserves_all_three_previous_histories(self):
        geo,source,_,_=self.fixture()
        keys=['shorelineRestoration','reservoirShorelineRestoration','reservoirRolloutRestoration']
        for key in keys:geo[key]={'id':key,'sourceHash':'frozen'}
        out=restore(geo,source,record_key='reservoirNeighborRestoration');check(geo,out,source,record_key='reservoirNeighborRestoration')
        for key in keys:self.assertEqual(out[key],geo[key])


if __name__=='__main__':unittest.main()
