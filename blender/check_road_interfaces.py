"""Capture actual builders at Zhuxi without allocating the complete city scene."""
import bpy
import numpy as np
import hashlib,json


def capture_interfaces(env):
    root=env['ROOT'];out=root/'work/zhuxi-repair';out.mkdir(parents=True,exist_ok=True)
    height=env['height']
    surface=lambda x,y,m:env['terrain_surface'](x,y,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=m)
    viaduct=env['Viaduct'](height,surface);minzu=env['MinzuAvenue'](viaduct.road_level,surface)
    bridges=[env['RiverBridge'](spec,height,minzu.road_level,lambda x,y:env['displayed_ground_bounds'](x,y)[1]) for spec in env['RIVER_BRIDGE_SPECS'].values()]
    class RegionBatch(env['Batch']):
        def face(self,vertices,key,normals=None):
            if key=='viaduct_line':return
            if max(v[0] for v in vertices)<73.8 or min(v[0] for v in vertices)>79.3:return
            if max(v[1] for v in vertices)<-12.8 or min(v[1] for v in vertices)>-7.65:return
            super().face(vertices,key,normals)
    keys=list(dict.fromkeys(env['VIADUCT_MATERIALS']+env['GROUND_ROAD_MATERIALS']+env['ZHUXI_MATERIALS']))
    for lightweight,profile in [(False,'detail'),(True,'smooth')]:
        net=env['ElevatedRoads'](height,surface,bridges=bridges,lightweight=lightweight,minzu=minzu)
        batch=RegionBatch('InterfaceAudit',keys)
        env['build_elevated_structure'](batch,net)
        env['build_ground_roads'](batch,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=lightweight,bridges=bridges,elevated=net)
        env['build_minzu_structure'](batch,minzu,lightweight=lightweight)
        env['build_minzu_details'](batch,minzu,lightweight=lightweight)
        env['build_zhuxi_details'](batch,net)
        obj=batch.finish();mesh=obj.data;mesh.calc_loop_triangles()
        points=np.asarray([v.co[:] for v in mesh.vertices]);ids=np.asarray([t.vertices[:] for t in mesh.loop_triangles])
        tags=np.asarray([keys[t.material_index] for t in mesh.loop_triangles]);faces=points[ids]
        roads=faces[np.isin(tags,['viaduct_asphalt','road_secondary','road_local'])]
        structure=faces[np.isin(tags,['viaduct_concrete','viaduct_soffit'])]
        lamps=faces[tags=='viaduct_metal']
        np.savez_compressed(out/f'native-interfaces-{profile}.npz',roads=roads,structure=structure,lamps=lamps)
        bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
        print(profile,'native interfaces',len(roads),len(structure),len(lamps),flush=True)
    inputs=['blender/build_city.py','blender/road_interfaces.py','blender/elevated_roads.py',
            'blender/minzu_avenue.py','blender/ground_roads.py','blender/road_solids.py',
            'blender/zhuxi_interchange.py','data/road-solids-detail.npz',
            'data/road-solids-smooth.npz','data/zhuxi-details.json']
    (out/'native-inputs.json').write_text(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs}))
