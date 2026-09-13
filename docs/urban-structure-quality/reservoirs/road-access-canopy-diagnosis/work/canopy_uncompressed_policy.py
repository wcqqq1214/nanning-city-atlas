import bpy

def export_city(filepath):
    bpy.ops.export_scene.gltf(filepath=str(filepath),export_format='GLB',
        export_cameras=False,export_lights=False,export_yup=True,
        export_apply=True,export_animations=False,export_extras=True,
        export_draco_mesh_compression_enable=False)
