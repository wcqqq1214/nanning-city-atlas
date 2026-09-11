"""Check ground-road coverage and continuous clearance against decoded terrain."""
import gzip
import hashlib
import json
from pathlib import Path
import struct

import DracoPy
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]


def load_plan():
    path=ROOT/'data/ground-roads-plan.json.gz'
    if path.exists():return json.loads(gzip.decompress(path.read_bytes())),path
    path=ROOT/'data/ground-roads-plan.json'
    return json.loads(path.read_text()),path


def decoded_faces(filename):
    raw=(ROOT/'public/models'/filename).read_bytes();size=struct.unpack_from('<I',raw,12)[0]
    model=json.loads(raw[20:20+size]);binary=28+size
    groups={'road':[],'paint':[],'terrain':[],'elevated':[]};counts={};materials=set()
    for node in model['nodes']:
        name=node.get('name','')
        if 'mesh' not in node or not name.startswith(('GroundRoads_','Terrain_','ElevatedRoads_','MinzuAvenue_')):continue
        joined_road=name.startswith(('ElevatedRoads_','MinzuAvenue_'))
        for p in model['meshes'][node['mesh']]['primitives']:
            mat=model['materials'][p['material']]['name']
            if joined_road and mat!='Qingxiang sage asphalt':continue
            if name.startswith('GroundRoads_'):
                counts[mat]=counts.get(mat,0)+model['accessors'][p['indices']]['count']//3
                materials.add(p['material'])
                if mat=='Qingxiang warm concrete':continue
            ext=p['extensions']['KHR_draco_mesh_compression'];view=model['bufferViews'][ext['bufferView']]
            start=binary+view.get('byteOffset',0);mesh=DracoPy.decode(raw[start:start+view['byteLength']])
            faces=np.asarray(mesh.points[mesh.faces],dtype=np.float64)
            assert np.isfinite(faces).all()
            group='elevated' if joined_road else 'terrain' if name.startswith('Terrain_') else 'paint' if mat=='Qingxiang lane markings' else 'road'
            groups[group].append(faces)
    groups={k:np.concatenate(v) for k,v in groups.items()}
    nodes=model['nodes'];parent=next(n for n in nodes if n.get('name')=='GroundRoads');roads=next(n for n in nodes if n.get('name')=='Roads')
    assert nodes.index(parent) in roads['children'], 'Ground streets ignore the roads layer'
    q=next(n for n in nodes if n.get('name')=='Landmark_qingxiang-viaduct')
    assert materials & {p['material'] for p in model['meshes'][q['mesh']]['primitives']}, 'Asphalt was not shared'
    return groups,counts,parent['extras']['planHash']


def planes(faces):
    p=faces[:,:,[0,2,1]]
    normal=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
    valid=np.abs(normal[:,2])>1e-11
    p=p[valid];normal=normal[valid]
    coefficients=np.column_stack((-normal[:,0]/normal[:,2],-normal[:,1]/normal[:,2],np.einsum('ij,ij->i',normal,p[:,0])/normal[:,2]))
    return shapely.polygons(p[:,:,:2]),coefficients,valid


def clearance(upper,lower,label,max_vertical_separation=None):
    up,up_plane,valid=planes(upper);low,low_plane,_=planes(lower)
    index=STRtree(low);minimum=float('inf');pairs_count=0;worst=None
    for start in range(0,len(up),3000):
        pairs=index.query(up[start:start+3000],predicate='intersects')
        if pairs.shape[1]==0:continue
        ui=pairs[0]+start;li=pairs[1]
        intersections=shapely.intersection(up[ui],low[li])
        if max_vertical_separation is not None:
            probes=shapely.get_coordinates(shapely.centroid(intersections))
            delta=up_plane[ui]-low_plane[li]
            keep=np.abs(delta[:,0]*probes[:,0]+delta[:,1]*probes[:,1]+delta[:,2])<max_vertical_separation
            ui,li,intersections=ui[keep],li[keep],intersections[keep]
            if len(ui)==0:continue
        coordinates,owners=shapely.get_coordinates(intersections,return_index=True)
        a,b=up_plane[ui[owners]],low_plane[li[owners]]
        dz=(a[:,0]-b[:,0])*coordinates[:,0]+(a[:,1]-b[:,1])*coordinates[:,1]+a[:,2]-b[:,2]
        local=int(dz.argmin())
        if float(dz[local])<minimum:
            minimum=float(dz[local]);owner=int(owners[local])
            worst={'xy':coordinates[local].tolist(),'upperPlane':a[local].tolist(),'lowerPlane':b[local].tolist(),
                   'upperTriangle':list(shapely.get_coordinates(up[ui[owner]]).tolist()),'lowerTriangle':list(shapely.get_coordinates(low[li[owner]]).tolist())}
        pairs_count+=len(ui)
    assert pairs_count>len(up)*.95, f'{label}: missing support coverage'
    print(f'{label}: continuous XY-overlap clearance {minimum*100:.4f} m; {pairs_count} face pairs',flush=True)
    if minimum<0: print('Clearance location:',worst,flush=True)
    return minimum,int((~valid).sum()),len(upper)


def validate_ground_roads():
    plan,path=load_plan();geo=json.loads((ROOT/'public/data/geography.json').read_text())
    context=json.loads((ROOT/'data/ground-roads-context.json').read_text())
    report=json.loads((ROOT/'public/data/overview.json').read_text())['groundRoads']
    payload=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
    digest=hashlib.sha256(payload).hexdigest();assert report['planHash']==digest
    for name,fingerprint in plan['inputHashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==fingerprint,f'Stale ground-road input: {name}'
    mz=json.loads((ROOT/'data/minzu-plan.json').read_text());q=json.loads((ROOT/'data/viaduct-plan.json').read_text())
    excluded=set(mz['replacedRoads'])|{int(i) for i in q['roadOverrides']}
    expected={i for i,r in enumerate(geo['roads']) if i not in excluded and not r['bridge']}
    assert set(plan['roadIndices'])==expected and len(expected)==len(plan['roadIndices'])
    areas=[unary_union([Polygon(p[0],p[1:]) for p in tier]) for tier in plan['surfaces']]
    paved=unary_union(areas)
    # Stored outlines round to 0.1 mm; reject area overlap beyond that edge envelope.
    assert all(areas[i].buffer(-.000002).intersection(areas[j].buffer(-.000002)).area<1e-7
               for i in range(3) for j in range(i+1,3)), 'Overlapping road materials at junctions'
    water=unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    buildings=unary_union([Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings']])
    solids=unary_union([Polygon(p[0],p[1:]) for p in context['obstacles']])
    assert paved.intersection(water).area<1e-7,'Ground road covers water'
    assert paved.intersection(buildings).area<1e-7,'Ground road cuts through building'
    assert paved.intersection(solids).area<1e-7,'Ground road cuts through detailed landmark'
    forest=json.loads((ROOT/'data/forest-plan.json').read_text())
    canopy=unary_union([Polygon(p[0],p[1:]) for r in forest['regions'] for p in r['coverage']])
    assert paved.intersection(canopy).area<1e-7,'Ground road buried under woodland canopy'
    road_index=STRtree(list(shapely.get_parts(paved)))
    removed=set(plan['removedTrees'])
    for i,(x,y,r) in enumerate(geo['trees']):
        if i in removed:continue
        crown=shapely.Point(x,y).buffer(r*1.06,quad_segs=8)
        assert not len(road_index.query(crown,predicate='intersects')), 'Retained tree crown intersects road'
    for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
        groups,counts,model_hash=decoded_faces(filename);assert model_hash==digest
        report_counts=report[profile]
        metadata=json.loads((ROOT/f'data/road-solids-{profile}.json').read_text())
        assert report_counts['resolvedHash']==metadata['sha256']
        assert hashlib.sha256((ROOT/f'data/road-solids-{profile}.npz').read_bytes()).hexdigest()==metadata['sha256']
        assert report_counts['surfaceTriangles']==metadata['counts']['ground']
        assert abs(len(groups['road'])-report_counts['surfaceTriangles'])<report_counts['surfaceTriangles']*.02
        assert report_counts['markingTriangles']==metadata['counts']['groundPaint']
        assert abs(len(groups['paint'])-report_counts['markingTriangles'])<report_counts['markingTriangles']*.02
        minimum,collapsed,total=clearance(groups['road'],groups['terrain'],profile+' roads/terrain')
        assert minimum>0, f'{profile}: decoded road penetrates displayed terrain'
        assert collapsed/total<.02,'Excessive compressed surface degeneration'
        minimum,collapsed,total=clearance(groups['paint'],groups['road'],profile+' paint/road')
        assert minimum>0, f'{profile}: lane marking embedded in asphalt'
        assert collapsed/total<.02,'Compression erased lane markings'
        # Exact triangulation should neither lose broad areas nor duplicate junction surfaces.
        shapes,_,_=planes(groups['road']);actual=unary_union(shapes)
        expected_xy=shapely.transform(paved,lambda xy:xy*np.array([1,-1]))
        # Ground approaches and bridge decks share a resolved solid; the bridge
        # material owns the joined overlap, including resolved Minzu sections.
        # Count their actual asphalt triangles; omitting Minzu falsely reports
        # its three paved junction fragments as holes (about 7.5 m² in detail).
        bridge_shapes,_,_=planes(groups['elevated'])
        covered=unary_union([actual,unary_union(bridge_shapes)])
        missing=expected_xy.buffer(-.003).difference(covered)
        # Separate material primitives quantize their shared edges independently.
        # Bound both seam width (6 cm) and total area (0.01%); broad holes still fail.
        assert missing.buffer(-.0003).area<1e-7,'Export left a broad hole in paved coverage'
        assert missing.area<expected_xy.area*.0001,'Export lost too much paved coverage'
        print(f'{profile} quantized edge gaps: {missing.area*10000:.3f} m² / {expected_xy.area*10000:.0f} m²; no gap wider than 6 cm',flush=True)
        assert actual.difference(expected_xy.buffer(.003)).area<.001,'Export escaped road footprint'
        print(profile,'ground streets:',counts,flush=True)
    print('PASS: all ground roads, disjoint junctions, water/building/tree clearance, road layer and decoded terrain/marking clearance.',flush=True)


if __name__=='__main__':validate_ground_roads()
