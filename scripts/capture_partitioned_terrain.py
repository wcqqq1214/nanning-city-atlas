"""Capture native, pre-access terrain with production object ownership in Blender."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from terrain_partitions import collect_partitioned,partition_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene-root',type=Path,required=True)
    parser.add_argument('--profiles',nargs='+',choices=['detail','smooth'],default=['detail','smooth'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root=args.scene_root.resolve();sys.path.insert(0,str(root/'blender'))
    from capture_native_terrain import capture
    from terrain_reduction_runtime import collect
    from terrain_reduction_plan import mesh_digest
    from terrain_mesh import NATIVE_DATA_INPUTS
    # Use the emitter's upstream contract, as the existing native-ground
    # capture does. Resolved roads/forest meshes are downstream of reduction;
    # binding them here would invalidate the plan whenever they are rebuilt.
    paths=sorted(set([*root.joinpath('blender').glob('*.py'),
                      *(root/name for name in NATIVE_DATA_INPUTS)]))
    def fingerprints():
        return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    hashes=fingerprints()
    for profile in args.profiles:
        env=capture(profile)
        source=collect_partitioned(bpy.data.objects['Terrain'].children_recursive,collect)
        target=args.output/profile;target.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(target/'original.npz',**source)
        if fingerprints()!=hashes:raise ValueError('Source changed during terrain capture')
        report={'input':'native '+profile,'scope':'production terrain before site access or terrain reduction',
                'manifestContract':'terrain_mesh.NATIVE_DATA_INPUTS plus Blender source files',
                'sceneRoot':str(root),'inputHashes':hashes,'materialKeys':env['TERRAIN_MATERIALS'],
                'originalMeshSha256':mesh_digest(source['triangles'],source['materials']),
                'originalPartitionSha256':partition_digest(source['partitionNames'],source['partitionIndices']),
                'partitions':len(source['partitionNames']),'triangles':len(source['triangles']),
                'archiveSha256':hashlib.sha256((target/'original.npz').read_bytes()).hexdigest(),
                'toolHashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__).resolve(),ROOT/'blender/terrain_partitions.py']}}
        (target/'capture.json').write_text(json.dumps(report,indent=2)+'\n')
        print(profile,report['triangles'],'faces;',report['partitions'],'partitions',flush=True)


if __name__=='__main__':main()
