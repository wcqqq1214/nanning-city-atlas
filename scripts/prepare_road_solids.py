"""Resolve complete bridge and approach solids before exporting their surfaces."""
import argparse,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np
import manifold3d as mf
import shapely
from shapely.geometry import Polygon,LineString,Point,box
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from prepare_ground_roads import triangulate

def prism(top,bottom,owner,kind=0):
    top=np.asarray(top,dtype=np.float64);bottom=np.asarray(bottom,dtype=np.float64)
    area=np.cross(top[1]-top[0],top[2]-top[0])[2]
    if abs(area)<1e-10:return None
    if area<0:top=top[[0,2,1]];bottom=bottom[[0,2,1]]
    vertices=np.concatenate((top,bottom))
    faces=np.asarray([[0,1,2],[5,4,3],[0,3,4],[0,4,1],[1,4,5],[1,5,2],[2,5,3],[2,3,0]],dtype=np.uint64)
    below,side=(1,2) if kind==0 else (9,10) if kind==8 else (6,7)
    tags=np.asarray([owner*16+kind,owner*16+below,*[owner*16+side]*6],dtype=np.uint64)
    result=mf.Manifold(mf.Mesh64(vertices,faces,face_id=tags))
    assert result.status()==mf.Error.NoError,result.status()
    return result

def prepare(profile,region=None):
    from viaduct import Path as RoadPath
    PLAN=json.loads(gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes()))
    GROUND=json.loads(gzip.decompress((ROOT/'data/ground-roads-plan.json.gz').read_bytes()))
    for path,digest in json.loads((ROOT/'work/road-repair/input-hashes.json').read_text()).items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Recapture native road surfaces after changing {path}'
    levels=json.loads((ROOT/f'work/road-repair/levels-{profile}.json').read_text())
    with np.load(ROOT/f'work/road-repair/inputs-{profile}.npz') as source:ground={key:source[key] for key in source.files}
    mesh=GROUND['meshes'][profile]
    paths=[RoadPath(r['points']) for r in PLAN['routes']]
    route_ids=[i for i,p in enumerate(paths) if region is None or LineString(p.points).intersects(region)]
    footprints=[LineString(paths[i].points).buffer(PLAN['routes'][i]['width']+.015) for i in route_ids]
    minzu_sections=json.loads((ROOT/'work/road-repair/minzu-sections.json').read_text())
    footprints.extend(Polygon(np.asarray(s['points'])[:,:2]).buffer(.015) for s in minzu_sections)
    road_shapes=shapely.polygons(np.asarray(mesh['points'])[np.asarray(mesh['triangles'])]);tree=STRtree(road_shapes)
    selected=np.unique(tree.query(footprints,predicate='intersects')[1])
    if region is not None:selected=np.array([i for i in selected if road_shapes[i].intersects(region)])
    volumes=[]
    obstacles=shapely.union_all([Polygon(p[0],p[1:]) for p in json.loads((ROOT/'data/ground-roads-context.json').read_text())['obstacles']]).buffer(.005)
    shapely.prepare(obstacles)
    for i in route_ids:
        p=paths[i];w=PLAN['routes'][i]['width'];z=levels[i]
        for j,(a,b) in enumerate(zip(p.lengths,p.lengths[1:])):
            q=np.array([p.at(a,-w,z[j]),p.at(b,-w,z[j+1]),p.at(b,w,z[j+1]),p.at(a,w,z[j])])
            if region is not None and not Polygon(q[:,:2]).intersects(region):continue
            for indices in [[0,1,2],[0,2,3]]:
                top=q[indices];bottom=top.copy();bottom[:,2]-=.035
                polygon=Polygon(top[:,:2])
                if obstacles.intersects(polygon):
                    normal=np.cross(top[1]-top[0],top[2]-top[0])
                    if abs(normal[2])<1e-10:continue
                    for xy in triangulate(polygon.difference(obstacles)):
                        xy=np.asarray(xy);zz=top[0,2]-(normal[0]*(xy[:,0]-top[0,0])+normal[1]*(xy[:,1]-top[0,1]))/normal[2]
                        part=np.column_stack((xy,zz));below=part.copy();below[:,2]-=.035
                        volume=prism(part,below,i)
                        if volume is not None:volumes.append(volume)
                    continue
                volume=prism(top,bottom,i)
                if volume is not None:volumes.append(volume)
    print(profile,'bridge prisms',len(volumes),'ground prisms',len(selected),flush=True)
    for i in selected:
        ids=mesh['triangles'][int(i)];top=ground['vertices'][ids];bottom=top.copy();bottom[:,2]=ground['floors'][ids]-.005
        volume=prism(top,bottom,2000+int(i),3+mesh['materials'][int(i)])
        if volume is not None:volumes.append(volume)
    for i,section in enumerate(minzu_sections):
        q=np.asarray(section['points'])
        if region is not None and not Polygon(q[:,:2]).intersects(region):continue
        for indices in [[0,1,2],[0,2,3]]:
            top=q[indices];bottom=np.asarray(section['bottom'])[indices]
            volumes.append(prism(top,bottom,1000000+i,8))
    solid=mf.Manifold.batch_boolean(volumes,mf.OpType.Add)
    print('Resolving union...',flush=True);result=solid.to_mesh64()
    assert solid.status()==mf.Error.NoError,solid.status()
    tags=np.asarray(result.face_id,dtype=np.int64);faces=np.asarray(result.tri_verts,dtype=np.int64);vertices=np.asarray(result.vert_properties)[:,:3]
    print('Resolved',len(faces),'triangles; materials',np.unique(tags%16,return_counts=True),flush=True)
    np.savez_compressed(ROOT/f'work/road-repair/solid-{profile}{"-sample" if region is not None else ""}.npz',vertices=vertices,triangles=faces,tags=tags,selected=selected)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('profile',choices=['detail','smooth']);p.add_argument('--region',nargs=3,type=float);args=p.parse_args()
    region=box(args.region[0]-args.region[2],args.region[1]-args.region[2],args.region[0]+args.region[2],args.region[1]+args.region[2]) if args.region else None
    prepare(args.profile,region)
