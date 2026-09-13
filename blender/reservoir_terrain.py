"""Explicit reservoir surface; importing this module never activates a plan."""
import hashlib
import json
import struct
from functools import lru_cache
from pathlib import Path

import numpy as np

from reduced_surface import ReducedSurface
from terrain_height import scene_height
from reservoir_water import inside_polygon


class ReservoirTerrain:
    def __init__(self, payload, dem):
        self.payload=payload;self.dem=dem
        if len(payload['points'])!=len(payload['weights']) or len(payload['points'])!=len(payload['targetMeters']):
            raise ValueError('Reservoir vertex fields do not match')
        if any(not 0<=w<=1 for w in payload['weights']):raise ValueError('Invalid reservoir blend weight')

    @classmethod
    def read(cls,path):
        payload=json.loads(Path(path).read_text())
        for item in payload['inputs'].values():
            if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('Reprepare reservoir after changing '+item['path'])
        dem=json.loads(Path(payload['inputs']['terrain']['path']).read_text())
        return cls(payload,dem)

    def replaces_cell(self,i,j):
        return (self.payload['columnRange'][0]<=i<self.payload['columnRange'][1] and self.payload['rowRange'][0]<=j<self.payload['rowRange'][1]
                and not any(e['columnRange'][0]<=i<e['columnRange'][1] and e['rowRange'][0]<=j<e['rowRange'][1]
                            for e in self.payload.get('cellExclusions',[])))

    def contains(self,x,y):
        w,s,e,n=self.payload['bounds']
        return w-1e-5<=x<=e+1e-5 and s-1e-5<=y<=n+1e-5

    def water_level(self,x,y):
        for i,lake in enumerate(self.payload['waterBodies']):
            if lake.get('waterMesh'):
                value=self.water_surface(i).sample(x,y)
                if value is not None:return value
            if inside_polygon(x,y,lake['rings']):return self.water_height(i,x,y)
        return None

    @lru_cache(maxsize=32)
    def water_surface(self,index):
        mesh=self.payload['waterBodies'][index].get('waterMesh')
        if mesh is None:return None
        points=[struct.unpack('<fff',struct.pack('<fff',x,y,scene_height(z,self.dem)))
                for (x,y),z in zip(mesh['points'],mesh['targetMeters'])]
        return ReducedSurface([[points[i] for i in face] for face in mesh['triangles']],['reservoir_water']*len(mesh['triangles']))

    def water_height(self,index,x,y):
        surface=self.water_surface(index)
        if surface is None:return scene_height(self.payload['waterBodies'][index]['levelMeters'],self.dem)
        value=surface.sample(x,y)
        if value is not None:return value
        # Source and native XY can differ slightly at a rounded shoreline.
        # Interpolate its actual edge, never invent a second height field.
        best=(float('inf'),None)
        for face in surface.triangles:
            for a,b in zip(face,face[1:]+face[:1]):
                dx,dy=b[0]-a[0],b[1]-a[1];length2=dx*dx+dy*dy
                t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/length2))
                distance=(a[0]+t*dx-x)**2+(a[1]+t*dy-y)**2
                if distance<best[0]:best=(distance,a[2]+t*(b[2]-a[2]))
        if best[0]>(.00005)**2:raise ValueError('Water sampler is outside the prepared mesh')
        return best[1]

    def custom_water_contains(self,x,y):
        return any(lake.get('waterMesh') and inside_polygon(x,y,lake['rings']) for lake in self.payload['waterBodies'])

    def custom_water_triangles(self):
        return [face for i,lake in enumerate(self.payload['waterBodies']) if lake.get('waterMesh')
                for face in self.water_surface(i).triangles]

    def surface(self,ground,bounds,columns,rows,lightweight,coarse):
        return self._surface(getattr(ground,'unpatched',ground),tuple(bounds),columns,rows,lightweight,coarse)

    @lru_cache(maxsize=8)
    def _surface(self,ground,bounds,columns,rows,lightweight,coarse):
        ground=getattr(ground,'unpatched',ground);vertices=[]
        for (x,y),target,weight in zip(self.payload['points'],self.payload['targetMeters'],self.payload['weights']):
            z=scene_height(target,self.dem)*weight+coarse(x,y,ground,bounds,columns,rows,lightweight)*(1-weight)
            vertices.append(struct.unpack('<fff',struct.pack('<fff',x,y,z)))
        triangles=[];materials=[];collapsed=0
        for ids,key in zip(self.payload['triangles'],self.payload['materials']):
            triangle=[vertices[i] for i in ids];a,b,c=triangle
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if area==0:collapsed+=1;continue
            if abs(area)<=1e-12:raise ValueError('Reservoir preparation contains unresolved near-degenerate native face')
            if area<0:triangle.reverse()
            triangles.append(triangle);materials.append(key)
        return ReducedSurface(triangles,materials),collapsed

    def sample(self,x,y,ground,bounds,columns,rows,lightweight,coarse):
        if not self.contains(x,y):return None
        # The atlas cut is stored in float64 city bounds but emitted in float32.
        # Clamp only the tiny interval between those two representations on
        # explicitly restored city sides, so the plinth uses the actual edge.
        xy=[x,y]
        for k,side in enumerate(['west','south','east','north']):
            if side not in self.payload.get('restoredCityBoundarySides',[]):continue
            limit=self.payload['bounds'][k];native=struct.unpack('<f',struct.pack('<f',limit))[0];axis=k%2
            if k<2 and limit<=xy[axis]<native or k>=2 and native<xy[axis]<=limit:
                xy[axis]=native
        x,y=xy
        surface,_=self.surface(ground,bounds,columns,rows,lightweight,coarse)
        z=surface.sample(x,y)
        return self.water_level(x,y) if z is None else z

    def bank_faces(self,surface):
        """Directed native boundary edges close the land down to each lake."""
        edges={};directions={}
        for triangle in surface.triangles:
            for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1;directions[key]=(a,b)
        segments=[]
        for lake_index,entry in enumerate(self.payload['waterBodies']):
            for ring in entry['rings']:
                segments.extend((a,b,lake_index) for a,b in zip(ring,ring[1:]))
        if not segments:return []
        starts=np.asarray([v[0] for v in segments]);ends=np.asarray([v[1] for v in segments]);direction=ends-starts
        length2=np.sum(direction*direction,axis=1);faces=[]
        for key,count in edges.items():
            if count!=1:continue
            a,b=directions[key];midpoint=(np.asarray(a[:2])+b[:2])/2
            t=np.clip(np.sum((midpoint-starts)*direction,axis=1)/np.maximum(length2,1e-20),0,1)
            distance=np.linalg.norm(midpoint-starts-t[:,None]*direction,axis=1);i=int(np.argmin(distance))
            if distance[i]>1.5e-5:continue
            lake_index=segments[i][2]
            bottom_a=self.water_height(lake_index,*a[:2])-.02
            bottom_b=self.water_height(lake_index,*b[:2])-.02
            faces.append([(*a[:2],bottom_a),(*b[:2],bottom_b),b,a])
        return faces

    def build(self,batch,ground,bounds,columns,rows,lightweight,coarse,base_material=None):
        surface,collapsed=self.surface(ground,bounds,columns,rows,lightweight,coarse)
        if collapsed:raise ValueError('Reservoir native faces collapsed during integration')
        previous=(batch.partition_override,batch.cell_override)
        batch.partition_override='reservoir_'+self.payload['id'].replace('-','_');batch.cell_override=(0,0)
        try:
            for face,key in zip(surface.triangles,surface.materials):
                if key=='reservoir_ground' and base_material is not None:
                    key=base_material(*[sum(p[k] for p in face)/3 for k in [0,1]])
                batch.face(face,key)
            for face in self.bank_faces(surface):batch.face(face,'dam_slope')
        finally:batch.partition_override,batch.cell_override=previous
