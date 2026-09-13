"""Candidate terrain vertex removal with error checked against the source mesh.

Only manifold interior fans of one material are eligible. Boundary vertices,
vertical faces and overlapping source faces are frozen. Every replacement uses
unchanged source vertices and is checked over all source/new triangle overlaps.
This prepares an explicit candidate; it never changes production terrain.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import json
import math
from pathlib import Path
import time

import mapbox_earcut
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from prepare_building_support import TerrainSurface


def triangulate_ring(points):
    """Keep every boundary vertex, including collinear stations."""
    points=np.asarray(points,dtype=float)
    polygon=Polygon(points)
    if not polygon.is_valid or polygon.area<=1e-12:return None
    faces=mapbox_earcut.triangulate_float64(points,np.array([len(points)],dtype=np.uint32)).reshape(-1,3).tolist()
    for i,p in enumerate(points):
        if any(i in f for f in faces):continue
        found=False
        for j,f in enumerate(faces):
            for k in range(3):
                a,b,c=f[k],f[(k+1)%3],f[(k+2)%3]
                edge=points[b]-points[a];length2=float(edge@edge)
                if length2<=1e-20:continue
                t=float((p-points[a])@edge/length2)
                if 1e-10<t<1-1e-10 and np.linalg.norm(p-(points[a]+t*edge))<1e-10:
                    faces[j:j+1]=[[a,i,c],[i,b,c]];found=True;break
            if found:break
        if not found:return None
    faces=np.asarray(faces,dtype=int)
    if len(faces)!=len(points)-2:return None
    shapes=shapely.polygons(points[faces])
    if min(shapely.area(shapes))<=1e-12:return None
    union=shapely.union_all(shapes)
    if polygon.symmetric_difference(union).area>1e-10:return None
    if abs(float(shapely.area(shapes).sum())-union.area)>1e-10:return None
    return faces


class Reducer:
    def __init__(self,triangles,materials,tolerance_meters=.05,normal_degrees=2.):
        if tolerance_meters<0 or not 0<normal_degrees<90:raise ValueError('Invalid error bounds')
        self.original=np.asarray(triangles,dtype=float)
        self.materials=np.asarray(materials,dtype=int)
        if len(self.materials)!=len(self.original):raise ValueError('Missing face materials')
        self.surface=TerrainSurface(self.original)
        self.vertices,indices=np.unique(self.original.reshape(-1,3),axis=0,return_inverse=True)
        self.faces={i:tuple(f) for i,f in enumerate(indices.reshape(-1,3))}
        self.face_material=dict(enumerate(self.materials.tolist()))
        self.adj=[set() for _ in self.vertices]
        edges=Counter()
        for i,f in self.faces.items():
            for v in f:self.adj[v].add(i)
            for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))]+=1
        self.protected={v for edge,count in edges.items() if count!=2 for v in edge}
        normals=np.cross(self.original[:,1]-self.original[:,0],self.original[:,2]-self.original[:,0])
        valid=abs(normals[:,2])>1e-12
        self.source_ids=np.flatnonzero(valid)
        # Steep retaining faces do not behave as a stable single-valued ground
        # surface; their vertices remain fixed with the original triangles.
        for i in np.flatnonzero(~valid | (np.linalg.norm(normals[:,:2],axis=1)>10*abs(normals[:,2]))):
            self.protected.update(self.faces[int(i)])
        self.shapes=shapely.polygons(self.surface.triangles[:,:,:2]);self.tree=STRtree(self.shapes)
        for start in range(0,len(self.shapes),1024):
            pairs=self.tree.query(self.shapes[start:start+1024],predicate='intersects')
            a=pairs[0]+start;b=pairs[1];keep=a<b;a,b=a[keep],b[keep]
            keep=shapely.area(shapely.intersection(self.shapes[a],self.shapes[b]))>1e-12
            for i in np.unique(np.concatenate([a[keep],b[keep]])):
                self.protected.update(self.faces[int(self.source_ids[i])])
        self.tolerance=tolerance_meters/100
        self.normal_cos=math.cos(math.radians(normal_degrees))
        self.rejections=Counter();self.maximum_error=0.;self.maximum_normal=0.
        self.generation=np.zeros(len(self.vertices),dtype=int);self.next_face=len(self.faces)
        self.removed=[]

    def ring(self,v):
        incident=sorted(self.adj[v])
        if v in self.protected or len(incident)<3:return None
        if len({self.face_material[i] for i in incident})!=1:return None
        graph=defaultdict(list)
        for i in incident:
            others=[a for a in self.faces[i] if a!=v]
            if len(others)!=2:return None
            a,b=others;graph[a].append(b);graph[b].append(a)
        if any(len(ns)!=2 for ns in graph.values()):return None
        start=min(graph);ring=[start];previous=None;current=start
        while True:
            options=sorted(n for n in graph[current] if n!=previous)
            if not options:return None
            nxt=options[0]
            if nxt==start:break
            if nxt in ring:return None
            ring.append(nxt);previous,current=current,nxt
        if len(ring)!=len(graph) or len(ring)!=len(incident):return None
        return incident,ring

    def score(self,v):
        result=self.ring(v)
        if result is None:return None
        _,ring=result;p=self.vertices[ring];origin=self.vertices[v]
        # Scheduling heuristic only; exact acceptance is independent of this fit.
        xy=p[:,:2]-origin[:2]
        fit=np.linalg.lstsq(np.column_stack([xy,np.ones(len(p))]),p[:,2],rcond=None)[0]
        return abs(float(fit[2]-origin[2]))

    def replacement(self,v):
        result=self.ring(v)
        if result is None:return None,'topology'
        incident,ring=result
        local=triangulate_ring(self.vertices[ring,:2])
        if local is None:return None,'triangulation'
        ids=np.asarray(ring)[local];triangles=self.vertices[ids]
        polygon=Polygon(self.vertices[ring,:2])
        old_shapes=shapely.polygons(self.vertices[np.asarray([self.faces[i] for i in incident])][:,:,:2])
        old_union=shapely.union_all(old_shapes)
        if (polygon.symmetric_difference(old_union).area>1e-10 or
            abs(float(shapely.area(old_shapes).sum())-old_union.area)>1e-10):return None,'coverage'
        new=TerrainSurface(triangles)
        if len(new.triangles)!=len(triangles):return None,'vertical'
        shapes=shapely.polygons(triangles[:,:,:2])
        pairs=self.tree.query(shapes,predicate='intersects');ni,oi=pairs
        clipped=shapely.intersection(shapes[ni],self.shapes[oi]);areas=shapely.area(clipped)
        keep=areas>1e-12;ni,oi,clipped=ni[keep],oi[keep],clipped[keep]
        material=self.face_material[incident[0]]
        if np.any(self.materials[self.source_ids[oi]]!=material):return None,'material'
        points,indices=shapely.get_coordinates(clipped,return_index=True)
        if not len(points):return None,'coverage'
        planes=new.planes[ni[indices]]-self.surface.planes[oi[indices]]
        delta=abs(planes[:,0]*points[:,0]+planes[:,1]*points[:,1]+planes[:,2])
        error=float(delta.max())
        if error>self.tolerance+1e-12:return None,'height'
        old_normals=np.column_stack([-self.surface.planes[oi,:2],np.ones(len(oi))])
        new_normals=np.column_stack([-new.planes[ni,:2],np.ones(len(ni))])
        cosines=np.sum(old_normals*new_normals,axis=1)/(np.linalg.norm(old_normals,axis=1)*np.linalg.norm(new_normals,axis=1))
        cosine=float(cosines.min())
        if cosine<self.normal_cos-1e-12:return None,'normal'
        # Keep upward winding, regardless of ring traversal direction.
        normal_z=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,2]
        ids[normal_z<0]=ids[normal_z<0][:,[0,2,1]]
        return (incident,ring,ids,material,error,cosine),None

    def run(self,max_removals=None,progress=None):
        heap=[]
        for v in range(len(self.vertices)):
            score=self.score(v)
            if score is not None:heapq.heappush(heap,(score,v,0))
        initial_candidates=len(heap);started=time.monotonic();attempts=0
        while heap and (max_removals is None or len(self.removed)<max_removals):
            _,v,generation=heapq.heappop(heap)
            if generation!=self.generation[v] or not self.adj[v]:continue
            attempts+=1;replacement,reason=self.replacement(v)
            if replacement is None:self.rejections[reason]+=1;continue
            incident,ring,faces,material,error,cosine=replacement
            for i in incident:
                for p in self.faces.pop(i):self.adj[p].remove(i)
                del self.face_material[i]
            for face in faces:
                i=self.next_face;self.next_face+=1
                self.faces[i]=tuple(int(p) for p in face);self.face_material[i]=material
                for p in face:self.adj[p].add(i)
            self.removed.append(v);self.maximum_error=max(self.maximum_error,error)
            self.maximum_normal=max(self.maximum_normal,math.degrees(math.acos(max(-1,min(1,cosine)))))
            for p in ring:
                self.generation[p]+=1;score=self.score(p)
                if score is not None:heapq.heappush(heap,(score,p,int(self.generation[p])))
            if progress and len(self.removed)%1000==0:progress(len(self.removed),attempts,time.monotonic()-started)
        face_ids=sorted(self.faces)
        triangles=self.vertices[np.asarray([self.faces[i] for i in face_ids])]
        materials=np.array([self.face_material[i] for i in face_ids],dtype=int)
        report={'status':'bounded native candidate; production sampling, compression and city dependencies pending',
                'originalTriangles':len(self.original),'candidateTriangles':len(triangles),
                'savedTriangles':len(self.original)-len(triangles),'removedVertices':len(self.removed),
                'protectedVertices':len(self.protected),'initialCandidates':initial_candidates,'attempts':attempts,
                'rejections':dict(self.rejections),'heightToleranceMeters':self.tolerance*100,
                'normalToleranceDegrees':math.degrees(math.acos(self.normal_cos)),
                'maximumAcceptedHeightErrorMeters':self.maximum_error*100,
                'maximumAcceptedNormalAngleDegrees':self.maximum_normal,
                'unchangedOriginalFaces':sum(i<len(self.original) for i in face_ids)}
        origins=np.array([i if i<len(self.original) else -1 for i in face_ids],dtype=int)
        return triangles,materials,origins,report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--tolerance-meters',type=float,default=.05)
    p.add_argument('--normal-degrees',type=float,default=2);p.add_argument('--max-removals',type=int)
    args=p.parse_args();source=np.load(args.input)
    reducer=Reducer(source['triangles'],source['materials'],args.tolerance_meters,args.normal_degrees)
    triangles,materials,origins,report=reducer.run(args.max_removals,lambda n,a,t:print('Removed',n,'vertices;',a,'attempts;',round(t,1),'seconds',flush=True))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output,triangles=triangles,materials=materials,originFaceIndices=origins)
    report['input']={'path':str(args.input),'sha256':hashlib.sha256(args.input.read_bytes()).hexdigest()}
    report['outputSha256']=hashlib.sha256(args.output.read_bytes()).hexdigest()
    report['toolHashes']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(__file__).with_name('prepare_building_support.py')]}
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
