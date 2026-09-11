"""Conservative deck floors over complete displayed terrain triangles."""
import math

def clip(subject,triangle):
    def cross(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    sign=1 if cross(*triangle)>=0 else -1
    for a,b in zip(triangle,triangle[1:]+triangle[:1]):
        if not subject:break
        output=[];p=subject[-1];dp=cross(a,b,p)*sign
        for q in subject:
            dq=cross(a,b,q)*sign
            if (dp>=0)!=(dq>=0):
                t=dp/(dp-dq);output.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
            if dq>=0:output.append(q)
            p,dp=q,dq
        subject=output
    return subject

def deck_floors(path,width,original,surface,bounds,columns,rows,fixed=None):
    """Add the worst interior ridge clearance to both ends of each segment.

    The full-resolution grid also subdivides the coarse profile's triangles.
    Their planar height difference has its extrema at clipped polygon vertices.
    """
    west,south,east,north=bounds;dx=(east-west)/(columns-1);dy=(north-south)/(rows-1)
    base=[max(z,surface(*path.at(s)[:2])) for s,z in zip(path.lengths,original)]
    fixed=fixed or {}
    for j,z in fixed.items():base[j]=min(base[j],z)
    result=base.copy()
    for j,(a,b) in enumerate(zip(path.lengths,path.lengths[1:])):
        q=[path.at(a,-width,base[j]),path.at(b,-width,base[j+1]),path.at(b,width,base[j+1]),path.at(a,width,base[j])]
        deficit=0
        for ids in [(0,1,2),(0,2,3)]:
            t=[q[k] for k in ids];u,v,w=t
            den=(v[0]-u[0])*(w[1]-u[1])-(w[0]-u[0])*(v[1]-u[1])
            if abs(den)<1e-10:continue
            zx=((v[2]-u[2])*(w[1]-u[1])-(w[2]-u[2])*(v[1]-u[1]))/den
            zy=((v[0]-u[0])*(w[2]-u[2])-(w[0]-u[0])*(v[2]-u[2]))/den
            weights=[0 if k in [0,3] else 1 for k in ids]
            wx=((weights[1]-weights[0])*(w[1]-u[1])-(weights[2]-weights[0])*(v[1]-u[1]))/den
            wy=((v[0]-u[0])*(weights[2]-weights[0])-(w[0]-u[0])*(weights[1]-weights[0]))/den
            i0=max(0,math.floor((min(p[0] for p in t)-west)/dx));i1=min(columns-2,math.floor((max(p[0] for p in t)-west)/dx))
            j0=max(0,math.floor((north-max(p[1] for p in t))/dy));j1=min(rows-2,math.floor((north-min(p[1] for p in t))/dy))
            for row in range(j0,j1+1):
                for col in range(i0,i1+1):
                    x,y=west+col*dx,north-row*dy
                    cell=[(x,y),(x+dx,y),(x+dx,y-dy),(x,y-dy)]
                    for indices in [(0,1,2),(0,2,3)]:
                        overlap=clip([p[:2] for p in t],[cell[k] for k in indices])
                        for px,py in overlap:
                            gap=surface(px,py)-(u[2]+zx*(px-u[0])+zy*(py-u[1]))
                            if gap<=0:continue
                            fraction=max(0,min(1,weights[0]+wx*(px-u[0])+wy*(py-u[1])))
                            free=(0 if j in fixed else 1-fraction)+(0 if j+1 in fixed else fraction)
                            if free>1e-6:deficit=max(deficit,gap/free)
        if deficit>0:
            if j not in fixed:result[j]=max(result[j],base[j]+deficit+.002)
            if j+1 not in fixed:result[j+1]=max(result[j+1],base[j+1]+deficit+.002)
    return result
