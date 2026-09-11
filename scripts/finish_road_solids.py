"""Build railings, paint and building clearance from resolved road surfaces."""
import gzip,hashlib,json,math,sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString,Point
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from viaduct import Path as RoadPath
from ground_roads import SteepEdges
from elevated_roads import plane
from zhuxi_interchange import marking_faces
from road_collision_checks import intersections
PLAN=json.loads(gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes()))
GROUND=json.loads(gzip.decompress((ROOT/'data/ground-roads-plan.json.gz').read_bytes()))

def stable_paint(faces):
    """Discard sub-1.5 cm slivers that cannot survive position quantization."""
    faces=np.asarray(faces,dtype=float).reshape(-1,3,3)
    area2=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)
    longest=np.max(np.linalg.norm(faces-np.roll(faces,1,axis=1),axis=2),axis=1)
    return faces[area2>longest*.00015]

class Surface:
    def __init__(self,faces):
        self.faces=np.asarray(faces);normal=np.cross(self.faces[:,1]-self.faces[:,0],self.faces[:,2]-self.faces[:,0])
        valid=np.abs(normal[:,2])>1e-10;self.faces=self.faces[valid];normal=normal[valid]
        self.shapes=shapely.polygons(self.faces[:,:,:2]);self.tree=STRtree(self.shapes)
        self.coeff=np.column_stack((-normal[:,0]/normal[:,2],-normal[:,1]/normal[:,2],np.einsum('ij,ij->i',normal,self.faces[:,0])/normal[:,2]))
    def z(self,i,xy):
        a,b,c=self.coeff[i];p=np.asarray(xy);return p[...,0]*a+p[...,1]*b+c
    def paint(self,source,steep):
        output=[]
        for tri in source:
            poly=Polygon(np.asarray(tri)[:,:2]);expected=float(np.mean(np.asarray(tri)[:,2]))-.002
            for i in self.tree.query(poly,predicate='intersects'):
                # Leave 1.5 cm at each support edge so 22-bit compression
                # cannot extend paint over a neighbouring step in the deck.
                p=poly.intersection(self.shapes[i].buffer(-.00015,join_style=2))
                if p.area<1e-8:continue
                xy=np.asarray(p.exterior.coords[:-1]);z=self.z(i,xy)
                if abs(float(np.mean(z))-expected)>.08:continue
                for j in range(1,len(xy)-1):
                    f=np.column_stack((xy[[0,j,j+1]],z[[0,j,j+1]]+.002))
                    if not steep.near(f.tolist()):output.append(f)
        return stable_paint(output)

def quad_faces(q):return [[q[0],q[1],q[2]],[q[0],q[2],q[3]]]

def finish(profile):
    captured=json.loads((ROOT/'work/road-repair/input-hashes.json').read_text())
    for path,digest in captured.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Recapture native road surfaces after changing {path}'
    raw=np.load(ROOT/f'work/road-repair/solid-{profile}.npz');v=raw['vertices'];faces=raw['triangles'];tags=raw['tags'];types=tags%16
    mesh=GROUND['meshes'][profile]
    with np.load(ROOT/f'work/road-repair/inputs-{profile}.npz') as source:native={key:source[key] for key in source.files}
    levels=json.loads((ROOT/f'work/road-repair/levels-{profile}.json').read_text());paths=[RoadPath(r['points']) for r in PLAN['routes']]
    selected=set(int(i) for i in raw['selected']);keep=[i for i in range(len(mesh['triangles'])) if i not in selected]
    ground_faces=np.concatenate((native['vertices'][np.asarray(mesh['triangles'])[keep]],v[faces[(types>=3)&(types<=5)]]))
    ground_materials=np.concatenate((np.asarray(mesh['materials'])[keep],types[(types>=3)&(types<=5)]-3))
    elevated_faces=v[faces[types<=2]];elevated_materials=types[types<=2]
    asphalt=Surface(v[faces[types==0]]);ground_surface=Surface(ground_faces);all_roads=Surface(np.concatenate((asphalt.faces,ground_faces)))
    steep=SteepEdges(all_roads.faces.tolist())
    # Preserve old embankment walls only where their source triangles were not
    # replaced by the joined solid. New boundary walls come from that solid.
    def edge(a,b):return tuple(sorted((tuple(np.round(a,7)),tuple(np.round(b,7)))))
    removed_edges={edge(native['vertices'][a],native['vertices'][b]) for i in selected for a,b in zip(mesh['triangles'][i],mesh['triangles'][i][1:]+mesh['triangles'][i][:1])}
    walls=[]
    for q in native['walls']:
        if edge(q[0],q[1]) not in removed_edges:walls.extend(quad_faces(q))
    walls.extend(v[faces[types==7]])
    # Railings follow the exposed topological boundary; internal merge seams
    # and transitions to ground paving are open driving surfaces.
    edges=defaultdict(list)
    for i,tri in enumerate(faces):
        for a,b in zip(tri,np.roll(tri,-1)):edges[tuple(sorted((int(a),int(b))))].append((i,int(a),int(b)))
    boundary=[]
    for entries in edges.values():
        top=[e for e in entries if types[e[0]]==0]
        if len(top)==1 and not any(types[e[0]] in [3,4,5] for e in entries):
            fi,ai,bi=top[0];boundary.append((int(tags[fi]//16),ai,bi))
    starts=defaultdict(list);ends=defaultdict(list)
    for i,(owner,a,b) in enumerate(boundary):starts[owner,a].append(i);ends[owner,b].append(i)
    def straight(a,b,c):
        u=v[b]-v[a];w=v[c]-v[b];lu=np.linalg.norm(u);lw=np.linalg.norm(w)
        return lu>1e-8 and lw>1e-8 and np.dot(u,w)>0 and np.linalg.norm(np.cross(u,w))/(lu*lw)<1e-5
    def chain_start(i):
        owner,a,b=boundary[i];prev=ends[owner,a]
        return len(prev)!=1 or not straight(boundary[prev[0]][1],a,b)
    used=set();merged=[]
    for i in sorted(range(len(boundary)),key=lambda i:not chain_start(i)):
        if i in used:continue
        owner,a,b=boundary[i];used.add(i)
        while len(starts[owner,b])==1:
            j=starts[owner,b][0]
            if j in used:break
            c=boundary[j][2]
            if not straight(a,b,c):break
            used.add(j);b=c
        merged.append((owner,a,b))
    barriers=[];omitted_rails=0
    obstacles=shapely.union_all([Polygon(p[0],p[1:]) for p in json.loads((ROOT/'data/ground-roads-context.json').read_text())['obstacles']]).buffer(.005)
    shapely.prepare(obstacles)
    for owner,ai,bi in merged:
        a,b=v[ai].copy(),v[bi].copy();length=np.linalg.norm((b-a)[:2])
        if length<.003:continue
        path=paths[owner];mid=(a+b)/2;distance,s=path.nearest(*mid[:2])
        if s<.02 or s>path.length-.02 or distance<PLAN['routes'][owner]['width']*.70:continue
        # Place the parapet outside the driving surface, with a tiny seam
        # allowance so independent material quantization cannot move it inside.
        outward=np.array([b[1]-a[1],a[0]-b[0],0])/length
        a+=outward*.0003;b+=outward*.0003;a[2]+=.0003;b[2]+=.0003
        q=np.array([a,b,b+outward*.005,a+outward*.005]);poly=Polygon(q[:,:2]);blocked=False
        if obstacles.intersects(poly):omitted_rails+=1;continue
        base=plane(q[[0,1,2]].tolist())
        for i in all_roads.tree.query(poly,predicate='intersects'):
            cut=poly.intersection(all_roads.shapes[i])
            if cut.area<1e-9:continue
            xy=np.asarray(cut.exterior.coords[:-1]);delta=all_roads.z(i,xy)-(xy[:,0]*base[0]+xy[:,1]*base[1]+base[2])
            if delta.max()>.0005 and delta.min()<.0115:blocked=True;break
        if blocked:omitted_rails+=1;continue
        cap=q.copy();cap[:,2]+=.012
        barriers.extend(quad_faces(cap))
        for j,k in [(0,1),(1,2),(2,3),(3,0)]:barriers.extend(quad_faces([q[j],q[k],cap[k],cap[j]]))
    # Test the complete parapet faces as well: a near-vertical corner can pass
    # the footprint test while still piercing an adjacent sloping deck.
    barriers=np.asarray(barriers,dtype=float).reshape(-1,3,3)
    collisions=intersections(barriers,all_roads.faces,profile+' parapet clearance',tolerance=.0001,min_length=.0003,edge_tolerance=0)
    rejected={r['upperFace']//10 for r in collisions['records']}
    omitted_rails+=len(rejected)
    barriers=barriers[np.asarray([i//10 not in rejected for i in range(len(barriers))])]
    # Piers are tested against actual paving, including resolved approaches.
    piers=[];omitted_piers=0
    for owner,s,x,y,bottom in json.loads((ROOT/f'work/road-repair/piers-{profile}.json').read_text()):
        candidates=asphalt.tree.query(Point(x,y),predicate='intersects')
        if not len(candidates):omitted_piers+=1;continue
        j,t=paths[owner].section(s);expected=levels[owner][j]*(1-t)+levels[owner][j+1]*t
        z=min((float(asphalt.z(i,[x,y])) for i in candidates),key=lambda value:abs(value-expected));top=z-.035
        if top-bottom<.05:continue
        footprint=Point(x,y).buffer(.055);blocked=False
        for i in all_roads.tree.query(footprint,predicate='intersects'):
            cut=footprint.intersection(all_roads.shapes[i]);xy=shapely.get_coordinates(cut)
            if not len(xy):continue
            zz=all_roads.z(i,xy)
            if zz.max()>bottom+.01 and zz.min()<top-.01:blocked=True;break
        if blocked:omitted_piers+=1;continue
        piers.append([owner,s,x,y,bottom,top])
    ground_paint=ground_surface.paint(native['paint'],steep)
    source_paint=[]
    for i,r in enumerate(PLAN['routes']):
        for f in r['paint'][profile]:
            zs=[]
            for x,y,s in r['faces'][f['support']]:
                j,t=paths[i].section(s);zs.append(levels[i][j]*(1-t)+levels[i][j+1]*t)
            source_paint.append([(x,y,u*zs[0]+w*zs[1]+(1-u-w)*zs[2]+.002) for x,y,u,w in f['points']])
    for i,r in enumerate(PLAN['routes']):
        source_paint.extend(marking_faces(r,paths[i],levels[i],profile=='smooth'))
    elevated_paint=asphalt.paint(source_paint,steep)
    # Generic building heights are often inferred. Keep their footprint and
    # lower only conflicting blocks; very short remnants are omitted.
    geo=json.loads((ROOT/'public/data/geography.json').read_text());adjustments=[]
    for i,bottom,roof in json.loads((ROOT/'work/road-repair/building-levels.json').read_text()):
        b=geo['buildings'][i];poly=Polygon(b['rings'][0],b['rings'][1:]).buffer(.012);limit=roof
        for j in asphalt.tree.query(poly,predicate='intersects'):
            cut=poly.intersection(asphalt.shapes[j]);xy=shapely.get_coordinates(cut)
            if not len(xy):continue
            zz=asphalt.z(j,xy)
            if zz.max()+.012<bottom or zz.min()-.055>roof:continue
            limit=min(limit,float(zz.min())-.055)
        if limit<roof-1e-6:
            adjustments.append({'index':i,'oldTop':roof,'base':bottom,'top':None if limit-bottom<.04 else limit,'mappedHeight':b.get('mappedHeight',False)})
    arrays=dict(elevated=elevated_faces,elevatedMaterials=elevated_materials,railings=np.asarray(barriers).reshape(-1,3,3),piers=np.asarray(piers).reshape(-1,6),elevatedPaint=elevated_paint,
                ground=ground_faces,groundMaterials=ground_materials,groundWalls=np.asarray(walls).reshape(-1,3,3),groundPaint=ground_paint)
    target=ROOT/f'data/road-solids-{profile}.npz';np.savez_compressed(target,**arrays)
    inputs=['data/elevated-roads-plan.json.gz','data/ground-roads-plan.json.gz','data/ground-roads-context.json','data/minzu-plan.json','data/bridges-plan.json','public/data/terrain.json','public/data/geography.json']
    inputs+=['blender/road_terrain.py','blender/elevated_roads.py','blender/ground_roads.py','blender/minzu_avenue.py','blender/forest_canopy.py','blender/zhuxi_interchange.py']
    report={'profile':profile,'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'levels':levels,
            'buildings':adjustments,'omittedRailSegments':omitted_rails,'omittedPiers':omitted_piers,'counts':{k:len(a) for k,a in arrays.items()}}
    (ROOT/f'data/road-solids-{profile}.json').write_text(json.dumps(report,separators=(',',':')))
    print(profile,report['counts'],'buildings adjusted',len(adjustments),'mapped',sum(a['mappedHeight'] for a in adjustments),flush=True)

if __name__=='__main__':finish(sys.argv[1])
