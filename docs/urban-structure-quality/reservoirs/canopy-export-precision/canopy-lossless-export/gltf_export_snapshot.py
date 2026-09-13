"""Export the city with extra Draco precision for narrow railway and road-marking meshes.

Blender 5.2 exposes a scene-wide quantization option. Scope its per-node encoder
to this one export, restoring it afterwards; never modify installed add-on files.
Decoded-mesh audits guard narrow geometry and ground-road/terrain clearance.
Terrain, park paths and cultural landmarks use 18-bit precision; resolved roads
and the citywide water mesh use 22-bit precision for joins and local lake levels.
"""
import bpy
from io_scene_gltf2.io.exp import draco


def export_city(filepath):
    original=getattr(draco,'__encode_node',None)
    if original is None:
        raise RuntimeError('Unsupported Blender Draco exporter; this city exporter is verified with Blender 5.2.1')

    def encode_node(node,dll,settings,cache):
        if node.name and node.name.startswith('Vegetation_') and '_canopy' in node.name:
            # Woodland surfaces share narrow terrain-cut edges across materials.
            # The default 14-bit grid moves vertices by up to 0.42 m in an
            # 8 km batch, collapsing slivers and reopening those shared edges.
            settings={**settings,'gltf_draco_position_quantization':0}
        elif node.name and node.name.startswith(('Terrain_reservoir_','Reservoir_')):
            # Even 30-bit per-material quantization can move a shared float32
            # shoreline to different coordinates. Zero disables position
            # quantization while retaining Draco topology/attribute encoding.
            settings={**settings,'gltf_draco_position_quantization':0}
        elif node.name and node.name.startswith('Terrain_grading_'):
            # A small grading patch has near-collinear height stations shared
            # across paving/earth materials. Preserve its native float32
            # positions instead of quantizing them with an 8 km terrain batch.
            settings={**settings,'gltf_draco_position_quantization':30}
        elif node.name and (node.name=='Water' or node.name.startswith(('GroundRoads_','ElevatedRoads_','MinzuAvenue_'))):
            # Resolved solids meet along narrow, sloping seams across 8 km
            # batches. 18-bit material quantization can move those edges by
            # centimetres and recreate crossings; retain millimetre precision.
            settings={**settings,'gltf_draco_position_quantization':22}
        elif node.name and node.name.startswith(('Railways_','Railway_Details_','MinzuAvenue_','RiverBridge_Details_','Terrain_',
                                                         'Buildings_quality_','ParkPaths_qingxiu','Landmark_qingxiu','Landmark_gx-museum','Landmark_ethnic-museum')):
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
