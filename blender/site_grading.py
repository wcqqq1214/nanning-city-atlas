"""Source-bound site grading shared by native terrain and dependent samplers.

The optional data plan contains horizontal topology and an estimated pad level.
Every profile evaluates its boundary against its own ungraded terrain. Resolved
roads are downstream and are not treated as inputs to this ground surface.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from block_grading import GradePatch
from reduced_surface import ReducedSurface

ROOT=Path(__file__).resolve().parents[1]
PLAN_PATH=ROOT/'data/block-grading-plan.json'
MATERIAL_KEYS=['block_paving','block_retaining']


class SiteGrading:
    def __init__(self,payload):
        self.payload=payload;self.patches=[GradePatch(site) for site in payload['sites']]
        for i,patch in enumerate(self.patches):
            a=patch.plan
            if not a['columnRange'][0]<a['columnRange'][1] or not a['rowRange'][0]<a['rowRange'][1]:
                raise ValueError('Invalid grading cell range')
            if any(v%2 for v in a['columnRange']+a['rowRange']):
                raise ValueError('Grading boundary must align with both terrain profiles')
            for other in self.patches[:i]:
                b=other.plan
                if (max(a['columnRange'][0],b['columnRange'][0])<min(a['columnRange'][1],b['columnRange'][1]) and
                    max(a['rowRange'][0],b['rowRange'][0])<min(a['rowRange'][1],b['rowRange'][1])):
                    raise ValueError('Grading patches overlap')

    def contains(self,x,y):
        return any(p.plan['bounds'][0]-1e-5<=x<=p.plan['bounds'][2]+1e-5 and p.plan['bounds'][1]-1e-5<=y<=p.plan['bounds'][3]+1e-5 for p in self.patches)

    def replaces_cell(self,i,j):return any(p.replaces_cell(i,j) for p in self.patches)

    @lru_cache(maxsize=16)
    def surfaces(self,ground,bounds,columns,rows,lightweight,coarse):
        ground=getattr(ground,'unpatched',ground)
        result=[]
        for patch in self.patches:
            # Quantize before evaluating heights. Intersections separated by
            # less than a float32 XY step must not acquire two different Zs at
            # the same stored position. Preserve full pad weight when one of
            # these coincident points belongs to the pad boundary.
            xy=[struct.unpack('<ff',struct.pack('<ff',*p)) for p in patch.plan['points']]
            weights={}
            for point,weight in zip(xy,patch.plan['weights']):weights[point]=max(weights.get(point,0),weight)
            positions={}
            for (x,y),weight in weights.items():
                z=(1-weight)*coarse(x,y,ground,bounds,columns,rows,lightweight)+weight*patch.plan['targetSceneZ']
                positions[(x,y)]=struct.unpack('<fff',struct.pack('<fff',x,y,z))
            vertices=[positions[point] for point in xy]
            faces=[];materials=[];dropped=0
            for ids,key in zip(patch.plan['triangles'],patch.plan['materials']):
                face=[vertices[i] for i in ids];a,b,c=face
                determinant=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                if determinant==0:dropped+=1;continue
                if abs(determinant)<=1e-12:raise ValueError('Near-vertical grading face needs preparation repair')
                if determinant<0:face.reverse()
                if key=='ground' and any(patch.plan['weights'][i]>1e-8 for i in ids):
                    u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
                    nx=u[1]*v[2]-u[2]*v[1];ny=u[2]*v[0]-u[0]*v[2]
                    if (nx*nx+ny*ny)**.5/abs(determinant)>patch.plan['retainingFaceGradeThreshold']:key='block_retaining'
                faces.append(face);materials.append(key)
            result.append((patch,ReducedSurface(faces,materials),dropped))
        return result

    def sample(self,x,y,ground,bounds,columns,rows,lightweight,coarse):
        if not self.contains(x,y):return None
        for patch,surface,_ in self.surfaces(ground,tuple(bounds),columns,rows,lightweight,coarse):
            z=surface.sample(x,y)
            if z is not None:return z
        return None

    def build(self,batch,ground,bounds,columns,rows,lightweight,coarse,base_material):
        for patch,surface,dropped in self.surfaces(ground,tuple(bounds),columns,rows,lightweight,coarse):
            partitioned=hasattr(batch,'partition_override')
            if partitioned:
                previous=(batch.partition_override,batch.cell_override)
                batch.partition_override='grading_'+patch.plan['id'].replace('-','_');batch.cell_override=(0,0)
            try:
                for face,key in zip(surface.triangles,surface.materials):
                    if key=='base':key=base_material(*[sum(p[k] for p in face)/3 for k in [0,1]])
                    batch.face(face,key)
            finally:
                if partitioned:batch.partition_override,batch.cell_override=previous
            if dropped:print('Grading float32 collapsed faces:',patch.plan['id'],dropped,flush=True)


def load(path=PLAN_PATH,root=ROOT):
    if not path.exists():return None
    payload=json.loads(path.read_text())
    required={'public/data/geography.json','public/data/terrain.json','data/block-grading-source.json'}
    if not required<=set(payload.get('runtimeInputs',{})):
        raise ValueError('Reprepare grading plan with runtime source bindings')
    for name,digest in payload['runtimeInputs'].items():
        file=(root/name).resolve();file.relative_to(root.resolve())
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('Reprepare grading after changing '+name)
    return SiteGrading(payload)


PLAN=load()
def contains(x,y):return PLAN is not None and PLAN.contains(x,y)
def replaces_cell(i,j):return PLAN is not None and PLAN.replaces_cell(i,j)
def surface(x,y,ground,bounds,columns,rows,lightweight,coarse):
    return None if PLAN is None else PLAN.sample(x,y,ground,bounds,columns,rows,lightweight,coarse)
