"""Bijective, material- and winding-aware checks of decoded terrain candidates."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

from validate_cultural_landmarks import glb
from decoded_surface import face_arrays

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from local_terrain import MATERIAL_KEYS
from site_grading import PLAN as GRADING_PLAN, MATERIAL_KEYS as GRADING_MATERIALS
MATERIAL_KEYS=MATERIAL_KEYS+(GRADING_MATERIALS if GRADING_PLAN is not None else [])


def match_faces(native,actual,position_meters=.05,normal_degrees=.5,include_mapping=False):
    # Decode yields float32 while native captures may use float64. Compute
    # centroids in the same precision: float32 summation at city coordinates
    # can otherwise reject identical vertices before the exact face check.
    a=np.asarray(native['triangles'],dtype=np.float64);b=np.asarray(actual['triangles'],dtype=np.float64)
    an=np.asarray(native['cornerNormals'],dtype=np.float64);bn=np.asarray(actual['cornerNormals'],dtype=np.float64)
    am=np.asarray(native['materials']);bm=np.asarray(actual['materials'])
    if len(a)!=len(b):raise ValueError('Export changed triangle count')
    if set(am)!=set(bm):raise ValueError('Export changed material classes')
    radius=position_meters/100;maximum_position=0.;maximum_normal=0.;undefined=0
    mapping=np.full(len(b),-1,dtype=np.int64) if include_mapping else None
    for material in sorted(set(am)):
        ids_a=np.flatnonzero(am==material);ids_b=np.flatnonzero(bm==material)
        if len(ids_a)!=len(ids_b):raise ValueError('Export changed per-material triangle counts')
        aa,bb=a[ids_a],b[ids_b];na,nb=an[ids_a],bn[ids_b]
        tree=cKDTree(aa.mean(axis=1));near=tree.query_ball_point(bb.mean(axis=1),radius+1e-12)
        rows=np.repeat(np.arange(len(bb)),[len(v) for v in near]);cols=np.array([i for v in near for i in v],dtype=int)
        if len(rows)==0:raise ValueError('No exported faces match native positions')
        positions=np.full(len(rows),np.inf);angles=np.full(len(rows),np.inf)
        for permutation in [(0,1,2),(1,2,0),(2,0,1)]:
            # Only cyclic permutations: a reversed triangle must not pass.
            delta=np.linalg.norm(aa[cols]-bb[rows][:,permutation],axis=2).max(axis=1)
            old_n=na[cols];new_n=nb[rows][:,permutation]
            old_len=np.linalg.norm(old_n,axis=2);new_len=np.linalg.norm(new_n,axis=2)
            denominator=old_len*new_len
            cosine=np.divide(np.sum(old_n*new_n,axis=2),denominator,out=np.ones_like(denominator),where=denominator>1e-20)
            angle=np.degrees(np.arccos(np.clip(cosine,-1,1)))
            angle[(old_len>1e-10)&(new_len<=1e-10)]=180
            # A zero-area source polygon has no defined shading normal.
            angle[old_len<=1e-10]=0;angle=angle.max(axis=1)
            good=(delta<=radius+1e-12)&(angle<=normal_degrees+1e-8)&(delta<positions)
            positions[good]=delta[good];angles[good]=angle[good]
        good=np.isfinite(positions);rows,cols,positions,angles=rows[good],cols[good],positions[good],angles[good]
        graph=csr_matrix((np.ones(len(rows),dtype=np.int8),(rows,cols)),shape=(len(bb),len(aa)))
        matched=maximum_bipartite_matching(graph,perm_type='column')
        if np.any(matched<0):raise ValueError(f'Cannot bijectively match {int((matched<0).sum())} faces within position/normal limits')
        if mapping is not None:mapping[ids_b]=ids_a[matched]
        lookup={(int(r),int(c)):i for i,(r,c) in enumerate(zip(rows,cols))}
        selected=np.array([lookup[(i,int(j))] for i,j in enumerate(matched)])
        maximum_position=max(maximum_position,float(positions[selected].max()*100))
        maximum_normal=max(maximum_normal,float(angles[selected].max()))
        undefined+=int((np.linalg.norm(na,axis=2)<=1e-10).sum())
    result={'triangles':len(a),'maximumVertexDisplacementMeters':maximum_position,
            'maximumCornerNormalAngleDegrees':maximum_normal,'undefinedSourceCornerNormals':undefined,
            'positionLimitMeters':position_meters,'normalLimitDegrees':normal_degrees,
            'bijectiveFaceMatch':True,'materialsAndWindingPreserved':True}
    if mapping is not None:result['nativeIndexByActualFace']=mapping.tolist()
    return result


def material_names():
    tree=ast.parse((ROOT/'blender/build_city.py').read_text())
    definition=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets))
    names={key.value:value.args[0].value for key,value in zip(definition.keys,definition.values)}
    return [names[key] for key in MATERIAL_KEYS]


def decoded(path):
    doc,decode=glb(path);names=material_names();faces=[];normals=[];materials=[]
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        if not node.get('name','').startswith('Terrain_'):raise ValueError('Unexpected non-terrain mesh')
        if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked terrain transform')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            mesh=decode(primitive);triangles,face_normals=face_arrays(mesh)
            faces.append(triangles);normals.append(face_normals)
            materials.extend([names.index(doc['materials'][primitive['material']]['name'])]*len(mesh.faces))
    return {'triangles':np.concatenate(faces),'cornerNormals':np.concatenate(normals),'materials':np.asarray(materials)}


def unchanged_native(before,after,removed):
    kept=np.ones(len(before['triangles']),dtype=bool);kept[removed]=False
    def key(t,m):return int(m),tuple(sorted(tuple(p) for p in t))
    wanted={key(t,m) for t,m in zip(before['triangles'][kept],before['materials'][kept])}
    mask=np.array([key(t,m) in wanted for t,m in zip(after['triangles'],after['materials'])])
    source={k:before[k][kept] for k in ['triangles','materials','cornerNormals']}
    target={k:after[k][mask] for k in ['triangles','materials','cornerNormals']}
    # Native positions are exact float32 source values; Blender's custom-normal
    # storage can introduce a small angular quantization when retaining normals.
    return match_faces(source,target,position_meters=1e-7,normal_degrees=.05)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=args.directory;plan=json.loads(gzip.decompress(args.plan.read_bytes()))
    before=np.load(root/'native-before.npz');after=np.load(root/'native-after.npz')
    result={'status':'isolated native/Draco geometry checks passed; final terrain contact and city integration pending',
            'unchangedNative':unchanged_native(before,after,plan['removedOriginalFaces']),
            'before':match_faces(before,decoded(root/'terrain-before.glb')),
            'after':match_faces(after,decoded(root/'terrain-after.glb'))}
    result['savedTriangles']=result['before']['triangles']-result['after']['triangles']
    result['savedBytes']=(root/'terrain-before.glb').stat().st_size-(root/'terrain-after.glb').stat().st_size
    result['inputs']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.plan,*[root/n for n in ['native-before.npz','native-after.npz','terrain-before.glb','terrain-after.glb']]]}
    result['toolHashes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'scripts/validate_cultural_landmarks.py',ROOT/'blender/build_city.py',ROOT/'scripts/decoded_surface.py']}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
