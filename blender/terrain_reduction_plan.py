"""Explicit, source-bound terrain replacement for native meshes and sampling.

Loading or importing this module does not change the production scene. A caller
must supply a plan and validate the exact native mesh before replacing its faces.
"""
import gzip
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from reduced_surface import ReducedSurface

_ACTIVE={}


def activate(plan):
    if not plan.validated:raise ValueError('Validate a native mesh before activating its reduction')
    _ACTIVE[plan.profile]=plan


def active_plan(profile):return _ACTIVE.get(profile)


def active_plan_paths():return [p.source_path for p in _ACTIVE.values() if p.source_path is not None]


def replacement_height(x,y,lightweight):
    plan=_ACTIVE.get('smooth' if lightweight else 'detail')
    return None if plan is None else plan.surface.sample(x,y)


@contextmanager
def suspended():
    previous=dict(_ACTIVE);_ACTIVE.clear()
    try:yield
    finally:_ACTIVE.clear();_ACTIVE.update(previous)


def mesh_digest(triangles,materials):
    digest=hashlib.sha256()
    faces=np.asarray(triangles,dtype='<f8');keys=np.asarray(materials,dtype='<i8')
    if faces.ndim!=3 or faces.shape[1:]!=(3,3) or keys.shape!=(len(faces),):
        raise ValueError('Invalid terrain arrays')
    digest.update(np.asarray([len(faces)],dtype='<i8').tobytes())
    digest.update(faces.tobytes());digest.update(keys.tobytes())
    return digest.hexdigest()


class TerrainReductionPlan:
    def __init__(self,payload,root=None):
        if payload.get('schemaVersion')!=1 or payload.get('metersPerUnit')!=100:
            raise ValueError('Unsupported terrain reduction plan')
        if payload.get('profile') not in ['detail','smooth']:raise ValueError('Unknown terrain profile')
        self.payload=payload;self.profile=payload['profile'];self.validated=False;self.source_path=None
        self.surface=ReducedSurface(payload['newTriangles'],[payload['materialKeys'][i] for i in payload['newMaterials']])
        if root is not None:
            root=Path(root).resolve()
            for name,digest in payload['inputHashes'].items():
                path=(root/name).resolve()
                if root not in path.parents:raise ValueError('Source path escapes repository')
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    raise ValueError('Terrain reduction source changed: '+name)

    @classmethod
    def read(cls,path,root):
        path=Path(path);raw=path.read_bytes()
        plan=cls(json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw),root)
        plan.source_path=path.resolve()
        return plan

    def apply(self,triangles,materials,profile):
        if profile!=self.profile:raise ValueError('Cannot apply reduction to a different quality profile')
        if mesh_digest(triangles,materials)!=self.payload['originalMeshSha256']:
            raise ValueError('Native terrain differs from the reduction source')
        before=np.asarray(triangles,dtype=float);before_materials=np.asarray(materials,dtype=int)
        removed=np.asarray(self.payload['removedOriginalFaces'],dtype=int)
        if len(set(removed))!=len(removed) or np.any(removed<0) or np.any(removed>=len(before)):
            raise ValueError('Invalid removed original face indices')
        keep=np.ones(len(before),dtype=bool);keep[removed]=False
        after=np.concatenate([before[keep],np.asarray(self.payload['newTriangles'],dtype=float)])
        after_materials=np.concatenate([before_materials[keep],np.asarray(self.payload['newMaterials'],dtype=int)])
        if mesh_digest(after,after_materials)!=self.payload['candidateMeshSha256']:
            raise ValueError('Replacement does not match the independently checked candidate')
        self.validated=True
        return after,after_materials

    def sample(self,x,y,profile,fallback):
        if profile!=self.profile:return fallback(x,y)
        if not self.validated:raise ValueError('Validate the native mesh before using its replacement sampler')
        value=self.surface.sample(x,y)
        return fallback(x,y) if value is None else value
