"""Verify actual native and Draco courtyard roofs against source footprints."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb


def decoded(path):
    doc,decode=glb(path);faces=[];normals=[];materials=[]
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        assert node['name'].startswith('Buildings_quality_')
        assert not any(k in node for k in ['matrix','translation','rotation','scale'])
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            mesh=decode(primitive)
            vertices=np.asarray(mesh.points)[:,[0,2,1]].copy();vertices[:,1]*=-1
            normal=np.asarray(mesh.normals)[:,[0,2,1]].copy();normal[:,1]*=-1
            faces.extend(vertices[mesh.faces]);normals.extend(normal[mesh.faces])
            materials.extend([['building','roof'].index(doc['materials'][primitive['material']]['name'])]*len(mesh.faces))
    return {'triangles':np.asarray(faces),'materials':np.asarray(materials),'cornerNormals':np.asarray(normals)}


def roof_coverage(geometry,indices,records,source,tolerance_meters):
    triangle=geometry['triangles'];material=geometry['materials'];worst=0.;rows=[]
    for i,record in enumerate(records):
        b=source[record['id']];shape=Polygon(b['rings'][0],b['rings'][1:])
        roofs=triangle[(indices==i)&(material==1)]
        assert len(roofs)>0,record['id']
        area=np.cross(roofs[:,1]-roofs[:,0],roofs[:,2]-roofs[:,0])[:,2]
        assert np.all(area>0),f'Degenerate or reversed roof: {record["id"]}'
        polygons=[Polygon(t[:,:2]) for t in roofs];roof=unary_union(polygons)
        tolerance=tolerance_meters/100
        # Both directions are necessary: containment alone can hide missing
        # wings, and comparing total area can hide a covered courtyard.
        assert shape.difference(roof.buffer(tolerance)).area<1e-10,record['id']
        assert roof.difference(shape.buffer(tolerance)).area<1e-10,record['id']
        overlap=sum(p.area for p in polygons)-roof.area
        assert overlap<1e-9,f'Overlapping roof faces: {record["id"]}'
        for ring in b['rings'][1:]:
            interior=Polygon(ring).buffer(-tolerance)
            assert roof.intersection(interior).area<1e-10,f'Covered courtyard: {record["id"]}'
        error=shape.hausdorff_distance(roof)*100;worst=max(worst,error)
        if len(b['rings'])>1:rows.append({'id':b['id'],'courtyards':len(b['rings'])-1,'boundaryHausdorffMeters':error})
    return {'buildings':len(records),'buildingsWithCourtyards':len(rows),
            'courtyards':sum(r['courtyards'] for r in rows),'maximumBoundaryHausdorffMeters':worst,
            'coverageToleranceMeters':tolerance_meters,'courtyardRecords':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    args=p.parse_args();root=args.directory
    report=json.loads((root/'report.json').read_text());source={b['id']:b for b in json.loads(args.candidate.read_text())['buildings']}
    assert report['inputs'][str(args.candidate)]==hashlib.sha256(args.candidate.read_bytes()).hexdigest()
    native=dict(np.load(root/'native.npz'))
    t=native['triangles'];n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(n,axis=1)
    assert np.all(length>1e-12),'Degenerate native face'
    native['cornerNormals']=np.repeat((n/length[:,None])[:,None,:],3,axis=1)
    actual=decoded(root/'buildings.glb')
    compressed=match_faces(native,actual,position_meters=.05,normal_degrees=.5,include_mapping=True)
    mapping=np.asarray(compressed.pop('nativeIndexByActualFace'))
    result={'status':'isolated mapped footprint/native/Draco checks passed; final support and full-city integration pending',
            'nativeRoofCoverage':roof_coverage(native,native['buildingIndices'],report['records'],source,.005),
            'compressedRoofCoverage':roof_coverage(actual,native['buildingIndices'][mapping],report['records'],source,.05),
            'compressedGeometry':compressed,
            'omittedDegenerateSourceTriangles':sum(r['omittedDegenerateRoofTriangles'] for r in report['records']),
            'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.candidate,root/'report.json',root/'native.npz',root/'buildings.glb']},
            'tools':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(__file__).with_name('check_reduced_terrain_exports.py')]}}
    (root/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['nativeRoofCoverage','compressedRoofCoverage']},indent=2))


if __name__=='__main__':main()
