"""Check the complete city's prepared-building coverage and Buildings ancestry."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from check_reduced_terrain_exports import match_faces
from check_mapped_building_exports import roof_coverage
from validate_cultural_landmarks import glb


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['scene-root','expected','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();root=args.scene_root.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=json.loads((args.expected/'report.json').read_text());native=dict(np.load(args.expected/'native.npz'));assert sha(args.expected/'native.npz')==report['nativeSha256']
    for name,digest in report['inputs'].items():assert sha(Path(name))==digest,name
    source={b['id']:b for b in json.loads((root/'public/data/geography.json').read_text())['buildings']}
    result={'status':'actual full-city prepared geometry and source roof coverage; visual site review remains separate','profiles':{}}
    for profile,name in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
        path=root/'public/models'/name;doc,decode=glb(path);nodes=doc['nodes'];parent=next(i for i,n in enumerate(nodes) if n.get('name')=='Buildings');descendants=set()
        def visit(i):
            assert i not in descendants,'Cycle or duplicate child in Buildings hierarchy';descendants.add(i)
            for child in nodes[i].get('children',[]):visit(child)
        visit(parent);triangles=[];normals=[];materials=[];mesh_count=0
        for i,node in enumerate(nodes):
            if 'mesh' not in node or not node.get('name','').startswith('Buildings_quality_'):continue
            assert i in descendants,'Prepared building ignores Buildings layer';assert not any(k in node for k in ['matrix','translation','rotation','scale'])
            mesh_count+=1
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                data=decode(primitive);points=np.asarray(data.points,dtype=float)[:,[0,2,1]];points[:,1]*=-1;normal=np.asarray(data.normals,dtype=float)[:,[0,2,1]];normal[:,1]*=-1
                label=doc['materials'][primitive['material']]['name'];assert label in ['Warm porcelain','Cool porcelain','Sandstone porcelain','Roof'],label
                triangles.extend(points[data.faces]);normals.extend(normal[data.faces]);materials.extend([1 if label=='Roof' else 0]*len(data.faces))
        actual={'triangles':np.asarray(triangles),'cornerNormals':np.asarray(normals),'materials':np.asarray(materials)}
        match=match_faces(native,actual,position_meters=.05,normal_degrees=.5,include_mapping=True);indices=native['buildingIndices'][match.pop('nativeIndexByActualFace')]
        coverage=roof_coverage(actual,indices,report['records'],source,.05)
        result['profiles'][profile]={'modelSha256':sha(path),'meshesUnderBuildings':mesh_count,'geometry':match,'roofCoverage':coverage}
    result['inputs']={str(args.expected/'report.json'):sha(args.expected/'report.json'),str(Path(__file__).resolve()):sha(Path(__file__))}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print({p:{'triangles':v['geometry']['triangles'],'buildings':v['roofCoverage']['buildings'],'courtyards':v['roofCoverage']['courtyards']} for p,v in result['profiles'].items()})


if __name__=='__main__':main()
