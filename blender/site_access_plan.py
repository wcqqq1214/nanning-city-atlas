"""Explicit downstream access replacement; importing this module changes nothing."""
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from reduced_surface import ReducedSurface

_ACTIVE=None


def activate(plan):
    expected={(identity,profile) for identity in plan.payload['sites'] for profile in ['detail','smooth']}
    if not expected<=plan.validated:raise ValueError('Validate both native profiles before activating access')
    global _ACTIVE
    _ACTIVE=plan


def active_plan():return _ACTIVE


def replacement_height(x,y,lightweight):
    if _ACTIVE is None:return None
    return _ACTIVE.sample(x,y,'smooth' if lightweight else 'detail',lambda x,y:None)


@contextmanager
def suspended():
    global _ACTIVE
    previous=_ACTIVE;_ACTIVE=None
    try:yield
    finally:_ACTIVE=previous


def signatures(triangles,materials):
    rows=[]
    for face,key in zip(triangles,materials):
        points=[tuple(p) for p in face]
        rows.append((int(key),min(tuple(points[i:]+points[:i]) for i in range(3))))
    return sorted(rows)


class SiteAccessPlan:
    def __init__(self,payload,grading,baselines):
        self.payload=payload;self.grading={s['id']:s for s in grading['sites']};self.baselines=baselines
        self.surfaces={};self.validated=set()
        if set(payload['sites'])-set(self.grading):raise ValueError('Unknown grading site in access plan')
        for identity,profiles in payload['sites'].items():
            for profile in ['detail','smooth']:
                record=profiles[profile]
                if 'nativeStorageAudit' not in record:raise ValueError('Prepare native-storage access before integration')
                triangles=np.asarray(record['terrainTriangles'],dtype=float)
                if not np.array_equal(triangles,triangles.astype(np.float32).astype(float)):
                    raise ValueError('Access soil is not exactly representable in Blender')
                self.surfaces[(identity,profile)]=ReducedSurface(record['terrainTriangles'],record['terrainMaterials'])

    @classmethod
    def read(cls,path,root):
        root=Path(root).resolve();payload=json.loads(Path(path).read_text());inputs={}
        for name,expected in payload['inputs'].items():
            source=(root/name).resolve();source.relative_to(root)
            if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError(f'Stale access input: {name}')
            inputs[source]=expected
            if source.suffix=='.json' and source.name!='block-grading-plan.json':
                metadata=json.loads(source.read_text())
                for field in ['inputHashes','tools']:
                    for dependency,digest in metadata.get(field,{}).items():
                        child=(root/dependency).resolve();child.relative_to(root)
                        if hashlib.sha256(child.read_bytes()).hexdigest()!=digest:
                            raise ValueError(f'Stale access dependency: {dependency}')
        grading_paths=[p for p in inputs if p.name=='block-grading-plan.json']
        if len(grading_paths)!=1:raise ValueError('Access needs its original grading source')
        grading=json.loads(grading_paths[0].read_text());baselines={}
        for profile in ['detail','smooth']:
            paths=[p for p in inputs if p.name==profile+'.npz']
            if len(paths)!=1:raise ValueError('Access needs both original native terrain captures')
            data=np.load(paths[0]);centers=data['triangles'][:,:,:2].mean(axis=1)
            for site in grading['sites']:
                w,s,e,n=site['bounds'];mask=(centers[:,0]>=w)&(centers[:,0]<=e)&(centers[:,1]>=s)&(centers[:,1]<=n)
                baselines[(site['id'],profile)]={'triangles':data['triangles'][mask],'materials':data['materials'][mask]}
        return cls(payload,grading,baselines)

    def validate_base(self,identity,profile,triangles,materials):
        source=self.baselines[(identity,profile)]
        if signatures(triangles,materials)!=signatures(source['triangles'],source['materials']):
            raise ValueError(f'Access base terrain changed: {identity}/{profile}')
        self.validated.add((identity,profile))

    def sample(self,x,y,profile,fallback):
        for identity in self.payload['sites']:
            if (identity,profile) not in self.validated:raise ValueError('Validate actual base terrain before access sampling')
            value=self.surfaces[(identity,profile)].sample(x,y)
            if value is not None:return value
        return fallback(x,y)

    def emit_terrain(self,batch,identity,profile):
        if (identity,profile) not in self.validated:raise ValueError('Validate actual base terrain before replacing it')
        record=self.payload['sites'][identity][profile]
        previous=(batch.partition_override,batch.cell_override)
        try:
            batch.partition_override='grading_access_'+identity.replace('-','_');batch.cell_override=(0,0)
            for face,key in zip(record['terrainTriangles'],record['terrainMaterials']):batch.face(face,key)
        finally:batch.partition_override,batch.cell_override=previous
