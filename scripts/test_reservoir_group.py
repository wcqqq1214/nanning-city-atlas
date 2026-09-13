"""Multiple real surface consumers, exclusion ownership and registry provenance."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reservoir_terrain import ReservoirTerrain
from reservoir_group import ReservoirGroup
from reservoir_runtime import load_registry

DEM={'cols':9,'rows':5,'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1}


def terrain(name,left,right,height=50):
    p={'id':name,'center':[108,22],'bounds':[left,0,right,2],
       'columnRange':[left,right],'rowRange':[0,2],
       'points':[[left,0],[right,0],[right,2],[left,2]],
       'triangles':[[0,1,2],[0,2,3]],'weights':[1]*4,'targetMeters':[height]*4,
       'materials':['reservoir_ground']*2,'waterBodies':[],'dams':[]}
    return ReservoirTerrain(p,DEM)


class Tests(unittest.TestCase):
    def test_every_patch_emits_and_samples_its_own_native_surface(self):
        a=terrain('a',0,2);b=terrain('b',4,6,80);g=ReservoirGroup([a,b])
        class Batch:
            partition_override='';cell_override=None
            def __init__(self):self.faces=[]
            def face(self,face,key):self.faces.append((self.partition_override,face,key))
        batch=Batch();args=(lambda x,y:0,[0,0,8,4],9,5,False,lambda *a:0)
        g.build(batch,*args)
        self.assertEqual([f[0] for f in batch.faces],['reservoir_a']*2+['reservoir_b']*2)
        self.assertEqual(batch.partition_override,'');self.assertIsNone(batch.cell_override)
        self.assertEqual(g.sample(1,1,*args),.5)
        self.assertAlmostEqual(g.sample(5,1,*args),.8,places=7)
        self.assertIsNone(g.sample(3,1,*args))
        self.assertEqual(len(list(g.land_xy_triangles())),4)
        for i in [0,1,4,5]:self.assertTrue(g.replaces_cell(i,1))
        self.assertFalse(g.replaces_cell(2,0))

    def test_excluded_cells_can_belong_to_a_second_patch(self):
        a=terrain('a',0,4);a.payload['cellExclusions']=[{'columnRange':[2,4],'rowRange':[0,2]}]
        b=terrain('b',2,4)
        g=ReservoirGroup([a,b]);self.assertIs(g.cells[2,0],b)
        a.payload['cellExclusions']=[]
        with self.assertRaisesRegex(ValueError,'Overlapping'):ReservoirGroup([a,b])

    def test_exclusion_must_preserve_two_profile_cell_ownership(self):
        a=terrain('a',0,4)
        for limits in [[1,2],[-2,2],[0,10]]:
            a.payload['cellExclusions']=[{'columnRange':limits,'rowRange':[0,2]}]
            with self.assertRaisesRegex(ValueError,'align'):ReservoirGroup([a])
        a.payload['cellExclusions']=[{'columnRange':[2,6],'rowRange':[0,2]}]
        g=ReservoirGroup([a]);self.assertTrue(g.replaces_cell(0,0));self.assertFalse(g.replaces_cell(2,0))

    def test_duplicate_water_dam_and_partition_are_rejected(self):
        for field,value,reason in [('waterBodies',{'geographyWaterIndex':3},'water ownership'),('dams',{'id':'dam'},'dam ownership')]:
            a=terrain('a',0,2);b=terrain('b',4,6)
            a.payload[field]=[value];b.payload[field]=[value]
            with self.assertRaisesRegex(ValueError,reason):ReservoirGroup([a,b])
        with self.assertRaisesRegex(ValueError,'partition'):
            ReservoirGroup([terrain('same-name',0,2),terrain('same_name',4,6)])

    def test_a_shared_boundary_cannot_hide_disagreeing_surfaces(self):
        args=(lambda x,y:0,[0,0,8,4],9,5,False,lambda *a:0)
        g=ReservoirGroup([terrain('a',0,2),terrain('b',2,4)])
        self.assertEqual(g.sample(2,1,*args),.5)
        g=ReservoirGroup([terrain('a',0,2),terrain('b',2,4,80)])
        with self.assertRaisesRegex(ValueError,'shared boundary'):g.sample(2,1,*args)

    def test_registry_binds_each_file_and_the_active_city(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'public/data').mkdir(parents=True)
            write=lambda name,value:(root/name).write_text(json.dumps(value))
            sha=lambda name:hashlib.sha256((root/name).read_bytes()).hexdigest()
            write('public/data/geography.json',{'center':[108,22],'water':[],'buildings':[]})
            write('public/data/terrain.json',DEM)
            entries=[]
            for name,lo,hi in [('a',0,2),('b',4,6)]:
                source='data/source-'+name+'.json';write(source,{})
                p=terrain(name,lo,hi).payload
                p['inputs']={key:{'path':str(root/file),'sha256':sha(file)} for key,file in
                             [('geography','public/data/geography.json'),('terrain','public/data/terrain.json'),('source',source)]}
                p['runtimeInputs']={str(Path(v['path']).relative_to(root)):v['sha256'] for v in p['inputs'].values()}
                p['waterInterfaceAudit']={'schemaVersion':1,'neighbors':[],'unresolvedWaterIndices':[]}
                path='data/plan-'+name+'.json';write(path,p);entries.append({'id':name,'path':path,'sha256':sha(path)})
            registry={'schemaVersion':1,'plans':entries};file='data/reservoir-terrain-registry.json';write(file,registry)
            group,paths=load_registry(root/file,root)
            self.assertEqual(len(group.plans),2);self.assertEqual(len(paths),3)
            write('data/source-b.json',{'changed':True})
            with self.assertRaisesRegex(ValueError,'Reprepare'):load_registry(root/file,root)
            write('data/source-b.json',{})
            write('data/plan-b.json',{})
            with self.assertRaisesRegex(ValueError,'registry after changing'):load_registry(root/file,root)

    def test_legacy_and_registry_cannot_both_be_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            registry=root/'data/reservoir-terrain-registry.json'
            self.assertEqual(load_registry(registry,root),(None,[]))
            registry.write_text('{}');(root/'data/reservoir-terrain-plan.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'not both'):load_registry(registry,root)


if __name__=='__main__':unittest.main()
