"""Capture the actual canopy consumer from an explicit city candidate root.

This captures woodland surfaces only. Qingxiu has a varying canopy factor and
is excluded; crowns and compressed GLB geometry require separate checks.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--forest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--access-plan', type=Path, required=True)
    parser.add_argument('--regions', nargs='+', choices=['nearby', 'all'], default=['nearby', 'all'])
    parser.add_argument('--profiles', nargs='+', choices=['detail', 'smooth'], default=['detail', 'smooth'])
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = args.root.resolve()
    sys.path.insert(0, str(root/'blender'))
    source = root/'blender/build_city.py'
    tree = ast.parse(source.read_text())
    stop = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'BUILDING_SUPPORT' for t in n.targets))
    namespace = {'__file__': str(source), '__name__': '__canopy_capture__'}
    # Execute the real city initialization and full ground pipeline, including
    # Nanhu, expo, sports terraces and railway cuts. The older asset validator's
    # raw_ground callback omits three of those corrections and is not equivalent.
    exec(compile(ast.Module(body=tree.body[:stop], type_ignores=[]), str(source), 'exec'), namespace)
    namespace['configure_site_access'](namespace, args.access_plan)
    from terrain_reduction_runtime import collect
    import importlib.util
    patch_root = Path.cwd()
    sampler_path = patch_root/'blender/nanhu_terrain.py'
    spec = importlib.util.spec_from_file_location('candidate_nanhu', sampler_path)
    sampler = importlib.util.module_from_spec(spec);spec.loader.exec_module(sampler)
    import forest_canopy
    forest_canopy.nanhu_surface = sampler.surface
    replacement = next(n for n in ast.parse((patch_root/'blender/forest_canopy.py').read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'terrain_surface')
    exec(compile(ast.Module(body=[replacement], type_ignores=[]), str(patch_root/'blender/forest_canopy.py'), 'exec'), forest_canopy.__dict__)
    namespace['terrain_surface'] = forest_canopy.terrain_surface
    g = namespace['GEO']
    args.output.mkdir(parents=True, exist_ok=True)
    paths = [args.forest, args.access_plan, source, Path(__file__), sampler_path, patch_root/'blender/forest_canopy.py', *sorted((root/'blender').glob('*.py')),
             *sorted(p for p in (root/'data').rglob('*') if p.is_file() and p.suffix in ['.json', '.npz', '.gz']),
             *sorted((root/'public/data').glob('*.json'))]
    report = {'scope': 'actual woodland surface consumer; native coordinates', 'regions': args.regions, 'meshes': {},
              'inputs': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}

    for region in json.loads(args.forest.read_text())['regions']:
        if region['id'] not in args.regions:
            continue
        for profile in args.profiles:
            name = region['id']+'-'+profile
            capture = namespace['Batch']('Vegetation_'+name+'_canopy', namespace['CANOPY_MATERIALS'], spatial=True, weld=True)
            namespace['build_canopy'](capture, region, namespace['height'], g['bounds'], namespace['COLS'], namespace['ROWS'], profile == 'smooth')
            group = capture.finish()
            triangles, materials, normals = collect(group.children_recursive)
            path = args.output/(name+'.npz')
            np.savez_compressed(path, triangles=triangles, materials=materials, cornerNormals=normals)
            report['meshes'][name] = {'faces': len(triangles), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (args.output/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
            print(name, len(triangles), flush=True)
            for obj in list(group.children_recursive):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.objects.remove(group, do_unlink=True)


if __name__ == '__main__':
    main()
