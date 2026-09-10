"""Export the city with extra Draco precision only for narrow railway meshes.

Blender 5.2 exposes a scene-wide quantization option. Scope its per-node encoder
to this one export, restoring it afterwards; never modify installed add-on files.
The decoded-mesh audit in validate_railways.py guards rail-head preservation.
"""
import bpy
from io_scene_gltf2.io.exp import draco


def export_city(filepath):
    original=getattr(draco,'__encode_node',None)
    if original is None:
        raise RuntimeError('Unsupported Blender Draco exporter; this city exporter is verified with Blender 5.2.1')

    def encode_node(node,dll,settings,cache):
        if node.name and node.name.startswith(('Railways_','Railway_Details_')):
            settings={**settings,'gltf_draco_position_quantization':18}
        return original(node,dll,settings,cache)

    draco.__encode_node=encode_node
    try:
        bpy.ops.export_scene.gltf(filepath=str(filepath),export_format='GLB',
            export_cameras=False,export_lights=False,export_yup=True,
            export_apply=True,export_animations=False,export_extras=True,
            export_draco_mesh_compression_enable=True,
            export_draco_mesh_compression_level=6,export_draco_position_quantization=14)
    finally:
        draco.__encode_node=original
