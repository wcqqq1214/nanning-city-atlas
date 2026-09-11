import hashlib,json,struct,sys
from pathlib import Path
import numpy as np
import DracoPy,shapely
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
def decode(filename):
    raw=(ROOT/'public/models'/filename).read_bytes();n=struct.unpack_from('<I',raw,12)[0]
    g=json.loads(raw[20:20+n]);groups={k:[] for k in ['deck','structure','soffit','ground','groundWalls','terrain','buildings']}
    for node in g['nodes']:
        assert not any(k in node for k in ['translation','rotation','scale','matrix'])
        name=node.get('name','');group=None
        if 'mesh' not in node:continue
        for p in g['meshes'][node['mesh']]['primitives']:
            mat=g['materials'][p['material']]['name'];key=None
            if name.startswith('ElevatedRoads_'):
                if mat=='Qingxiang sage asphalt':key='deck'
                elif mat=='Qingxiang warm concrete':key='structure'
                elif mat=='Qingxiang shaded box girders':key='soffit'
            elif name.startswith('GroundRoads_'):
                if mat=='Qingxiang warm concrete':key='groundWalls'
                elif mat!='Qingxiang lane markings':key='ground'
            elif name.startswith('Terrain_'):key='terrain'
            elif name.startswith('Buildings_'):key='buildings'
            if key is None:continue
            v=g['bufferViews'][p['extensions']['KHR_draco_mesh_compression']['bufferView']];start=28+n+v.get('byteOffset',0)
            d=DracoPy.decode(raw[start:start+v['byteLength']]);tri=np.asarray(d.points[d.faces],dtype=float)[:,:,[0,2,1]];tri[:,:,1]*=-1
            groups[key].append(tri)
    print(filename,{k:sum(len(v) for v in a) for k,a in groups.items()},flush=True)
    return {k:np.concatenate(v) for k,v in groups.items()},hashlib.sha256(raw).hexdigest()

def intersections(upper,lower,label,self_test=False,tolerance=.0005,min_length=.001,edge_tolerance=.0005):
    """Exact non-coplanar face intersections after XY broad-phase and plane clipping.

    Require penetration through the interiors of both faces. Plane straddling
    alone can report metres of depth at a shared edge moved by a millimetre:
    the far vertices straddle an infinite plane outside the other triangle.
    Ignore the 5 cm edge envelope and intersection segments shorter than 10 cm.
    """
    normals=np.cross(lower[:,1]-lower[:,0],lower[:,2]-lower[:,0]);length=np.linalg.norm(normals,axis=1)
    valid=length>1e-10;lower_ids=np.flatnonzero(valid);normals=normals[valid]/length[valid,None];lower=lower[valid]
    shapes=shapely.convex_hull(shapely.multipoints(lower[:,:,:2]));tree=STRtree(shapes)
    records=[];seen=set();tested=0
    for start in range(0,len(upper),3000):
        u=upper[start:start+3000];a,b=tree.query(shapely.convex_hull(shapely.multipoints(u[:,:,:2])),predicate='intersects')
        if self_test:
            keep=a+start<lower_ids[b];a,b=a[keep],b[keep]
        keep=(u[a,:,2].min(axis=1)<lower[b,:,2].max(axis=1)-tolerance)&(u[a,:,2].max(axis=1)>lower[b,:,2].min(axis=1)+tolerance)
        a,b=a[keep],b[keep]
        if len(a)==0:continue
        d=np.einsum('ijk,ik->ij',u[a]-lower[b,0,None,:],normals[b]);tested+=len(d)
        keep=(d.min(axis=1)<-tolerance)&(d.max(axis=1)>tolerance)
        for ai,bi,di in zip(a[keep],b[keep],d[keep]):
            tri=u[ai];points=[]
            for j,k in [(0,1),(1,2),(2,0)]:
                if di[j]*di[k]<0:points.append(tri[j]+di[j]/(di[j]-di[k])*(tri[k]-tri[j]))
            if len(points)!=2:continue
            axes=[i for i in range(3) if i!=int(np.abs(normals[bi]).argmax())]
            line=shapely.LineString(np.array(points)[:,axes]);poly=shapely.Polygon(lower[bi][:,axes])
            overlap=line.intersection(poly.buffer(-edge_tolerance,join_style=2))
            if overlap.length<min_length:continue
            # Trim the upper face's shared-edge envelope as well.
            segment=np.array(points);dv=segment[1,axes]-segment[0,axes]
            ts=[np.dot(p-segment[0,axes],dv)/np.dot(dv,dv) for p in np.asarray(overlap.coords)]
            clipped=segment[0]+np.array([min(ts),max(ts)])[:,None]*(segment[1]-segment[0])
            un=np.cross(tri[1]-tri[0],tri[2]-tri[0]);axes=[i for i in range(3) if i!=int(np.abs(un).argmax())]
            overlap=shapely.LineString(clipped[:,axes]).intersection(shapely.Polygon(tri[:,axes]).buffer(-edge_tolerance,join_style=2))
            if overlap.length<min_length:continue
            probe=np.asarray(overlap.centroid.coords[0]);segment=np.array(points);dv=segment[1,axes]-segment[0,axes]
            t=np.dot(probe-segment[0,axes],dv)/np.dot(dv,dv);p=segment[0]+t*(segment[1]-segment[0])
            cell=tuple(round(float(c),2) for c in p[:2])
            depth=float(min(-di.min(),di.max())*100)
            records.append({'point':p.tolist(),'depthMeters':depth,'lengthMeters':float(overlap.length*100),'upperFace':int(start+ai),'lowerFace':int(lower_ids[bi]),
                            'upperTriangle':tri.tolist(),'lowerTriangle':lower[bi].tolist()})
            seen.add(cell)
    records.sort(key=lambda r:r['depthMeters'],reverse=True)
    print(label,'intersecting face pairs',len(records),'1m locations',len(seen),'tested',tested,flush=True)
    print('Strongest:',[{k:r[k] for k in ['point','depthMeters','lengthMeters']} for r in records[:3]],flush=True)
    return {'pairs':len(records),'locations':len(seen),'records':records}

if __name__=='__main__':
    profile=sys.argv[1] if len(sys.argv)>1 else 'detail';filename='nanning-city.glb' if profile=='detail' else 'nanning-city-mobile.glb'
    groups,digest=decode(filename);report={'model':filename,'sha256':digest,'checks':{}}
    for a,b in [('deck','deck'),('deck','ground'),('deck','soffit'),('structure','deck'),('structure','ground'),('soffit','terrain'),('structure','buildings'),('soffit','buildings')]:
        report['checks'][a+'/'+b]=intersections(groups[a],groups[b],profile+' '+a+'/'+b,a==b)
        (ROOT/f'work/road-repair/collision-{profile}.json').write_text(json.dumps(report,separators=(',',':')))
