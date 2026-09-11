"""Capture native road heights without exporting or changing the editable city."""
import json,hashlib
from pathlib import Path
import numpy as np

def capture_road_inputs(env):
    root=env['ROOT'];out=root/'work/road-repair';out.mkdir(parents=True,exist_ok=True)
    height=env['height'];surface=lambda x,y,m:env['terrain_surface'](x,y,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=m)
    viaduct=env['Viaduct'](height,surface);minzu=env['MinzuAvenue'](viaduct.road_level,surface)
    from road_interfaces import capture, PaintCapture
    (out/'minzu-sections.json').write_text(json.dumps(capture(minzu)))
    bridges=[env['RiverBridge'](spec,height,minzu.road_level,lambda x,y:env['displayed_ground_bounds'](x,y)[1]) for spec in env['RIVER_BRIDGE_SPECS'].values()]
    class Capture:
        def __init__(self):self.paint=[];self.walls=[]
        def capture_vertices(self,vertices,floors):self.vertices=vertices;self.floors=floors
        def face(self,vertices,material):
            if material=='viaduct_line':self.paint.append(vertices)
            elif material=='viaduct_concrete':self.walls.append(vertices)
    for mobile,profile in [(False,'detail'),(True,'smooth')]:
        paint=PaintCapture()
        env['build_minzu_details'](paint,minzu,lightweight=mobile,native=True)
        np.save(out/f'minzu-paint-{profile}.npy',np.asarray(paint.faces))
        net=env['ElevatedRoads'](height,surface,bridges=bridges,lightweight=mobile,minzu=minzu)
        capture=Capture()
        env['build_ground_roads'](capture,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=mobile,bridges=bridges,elevated=net)
        np.savez_compressed(out/f'inputs-{profile}.npz',vertices=np.asarray(capture.vertices),floors=np.asarray(capture.floors),paint=np.asarray(capture.paint),walls=np.asarray(capture.walls))
        (out/f'levels-{profile}.json').write_text(json.dumps(net.levels,separators=(',',':')))
        piers=[]
        for i,(r,path) in enumerate(zip(net.routes,net.paths)):
            for s in r['piers']:
                x,y=path.at(s)[:2];piers.append([i,s,x,y,min(height(x,y),surface(x,y,False),surface(x,y,True))-.01])
        (out/f'piers-{profile}.json').write_text(json.dumps(piers,separators=(',',':')))
        print('Captured native road surfaces',profile,flush=True)
    buildings=[]
    for i,b in enumerate(env['GEO']['buildings']):
        ring=b['rings'][0][:-1]
        if len(ring)<3:continue
        x=sum(p[0] for p in ring)/len(ring);y=sum(p[1] for p in ring)/len(ring)
        if i in env['RAILWAY_BUILDINGS'] or env['inside_landmark'](x,y):continue
        if any(n in b.get('name','') for n in ['龙象塔','华润大厦A','地王国际商会中心']):continue
        z=max(.4,height(x,y))+.07
        if env['inside_nanhu'](x-env['NANHU_X'],y-env['NANHU_Y']):z=height(x,y)+.018
        buildings.append([i,z,z+b['height']/100*1.55])
    (out/'building-levels.json').write_text(json.dumps(buildings,separators=(',',':')))
    inputs=['data/elevated-roads-plan.json.gz','data/ground-roads-plan.json.gz','data/ground-roads-context.json','data/minzu-plan.json','data/bridges-plan.json','public/data/terrain.json','public/data/geography.json','blender/elevated_roads.py','blender/ground_roads.py']
    inputs+=['blender/minzu_avenue.py','blender/road_interfaces.py']
    (out/'input-hashes.json').write_text(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs},indent=2))
