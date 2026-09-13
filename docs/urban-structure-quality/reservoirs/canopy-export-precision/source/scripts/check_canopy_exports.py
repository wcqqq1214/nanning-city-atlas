"""Check captured woodland GLBs against native geometry and final ground."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np

from check_canopy_clearance import check
from check_reduced_terrain_exports import match_faces
from decoded_surface import face_arrays
from validate_cultural_landmarks import glb


def decoded(path, material_names):
    doc, decode = glb(path)
    triangles, normals, materials = [], [], []
    for node in doc['nodes']:
        if 'mesh' not in node:
            continue
        if not (node.get('name', '').startswith('Vegetation_') and '_canopy' in node['name']):
            raise ValueError('Unexpected mesh in isolated canopy export')
        if any(k in node for k in ['matrix', 'translation', 'rotation', 'scale']):
            raise ValueError('Expected baked canopy positions')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            faces, corner = face_arrays(decode(primitive))
            material = material_names.index(doc['materials'][primitive['material']]['name'])
            triangles.append(faces)
            normals.append(corner)
            materials.extend([material]*len(faces))
    return dict(triangles=np.concatenate(triangles), cornerNormals=np.concatenate(normals),
                materials=np.asarray(materials))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--terrain', type=Path, required=True)
    parser.add_argument('--city-source', type=Path, required=True)
    args = parser.parse_args()
    tree = ast.parse(args.city_source.read_text())
    definition = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'MATS' for t in n.targets))
    names = {k.value: v.args[0].value for k, v in zip(definition.keys, definition.values)}
    material_names = [names[k] for k in ['forest_deep', 'forest_jade', 'forest_light']]
    native_path = args.directory/(args.name+'.npz')
    glb_path = args.directory/(args.name+'.glb')
    native = dict(np.load(native_path))
    actual = decoded(glb_path, material_names)
    # Zero position tolerance is intentional: compression must retain all native
    # shared edge stations. Smooth corner normals retain their existing limit.
    geometry = match_faces(native, actual, position_meters=0, normal_degrees=.5)
    np.savez_compressed(args.directory/(args.name+'-decoded.npz'), **actual)
    clearance = check(actual['triangles'], np.load(args.terrain)['triangles'],
                      minimum_clearance_meters=9.5, coverage_tolerance_meters=.002)
    clearance['scope'] = 'actual decoded canopy against the supplied final terrain triangles'
    report = {'passed': clearance['passed'], 'geometry': geometry, 'clearance': clearance,
              'inputs': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [native_path, glb_path, args.terrain, args.city_source, Path(__file__)]}}
    (args.directory/(args.name+'-audit.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'inputs'}, indent=2), flush=True)
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
