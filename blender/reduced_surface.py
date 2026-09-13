"""Explicit replacement triangles shared by native emission and height queries.

No plan is activated on import. The caller owns source/profile validation and
must remove the corresponding original faces before emitting a replacement.
Points outside the replacement return None for the caller's original sampler.
"""
import math


class ReducedSurface:
    def __init__(self,triangles,materials,cell_size=1.2):
        if not math.isfinite(cell_size) or cell_size<=0:raise ValueError('Invalid spatial cell size')
        self.triangles=[tuple(tuple(float(c) for c in p) for p in t) for t in triangles]
        self.materials=list(materials)
        if len(self.materials)!=len(self.triangles):raise ValueError('Missing triangle materials')
        self.cell_size=cell_size;self.cells={};self.planes=[]
        for i,t in enumerate(self.triangles):
            if len(t)!=3 or any(len(p)!=3 or not all(math.isfinite(c) for c in p) for p in t):
                raise ValueError('Expected finite XYZ triangles')
            a,b,c=t;bx,by,bz=[b[k]-a[k] for k in range(3)];cx,cy,cz=[c[k]-a[k] for k in range(3)]
            determinant=bx*cy-by*cx
            if abs(determinant)<=1e-12:raise ValueError('Replacement cannot contain a vertical or degenerate face')
            self.planes.append((a,bx,by,cx,cy,determinant,bz,cz))
            west,south=min(p[0] for p in t),min(p[1] for p in t)
            east,north=max(p[0] for p in t),max(p[1] for p in t)
            for x in range(math.floor(west/cell_size),math.floor(east/cell_size)+1):
                for y in range(math.floor(south/cell_size),math.floor(north/cell_size)+1):
                    self.cells.setdefault((x,y),[]).append(i)

    def sample(self,x,y):
        cell=(math.floor(x/self.cell_size),math.floor(y/self.cell_size))
        for i in self.cells.get(cell,()):
            a,bx,by,cx,cy,det,bz,cz=self.planes[i];dx,dy=x-a[0],y-a[1]
            u=(dx*cy-dy*cx)/det;v=(bx*dy-by*dx)/det
            if min(u,v,1-u-v)>=-1e-10:return a[2]+u*bz+v*cz
        return None

    def emit(self,batch):
        for triangle,material in zip(self.triangles,self.materials):batch.face(triangle,material)
