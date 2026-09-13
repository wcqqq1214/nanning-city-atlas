"""Fresh production landmark geometry for road obstacles, without city outputs."""
import ast,hashlib,json,sys
from pathlib import Path
import bpy
root=Path.cwd();sys.path.insert(0,str(root/'blender'))
from capture_native_terrain import capture
from gltf_export import export_city
source=root/'blender/build_city.py';tree=ast.parse(source.read_text())
start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='landmarks' for t in n.targets))
end=next(i for i,n in enumerate(tree.body[start:],start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='landmarks' and n.value.func.attr=='sort')
assert start<end
out=root/'work/p5/final-integration';env=capture('detail')
for key in ['tree_group','bridge_group']:
 obj=bpy.data.objects.new(key,None);bpy.context.collection.objects.link(obj);env[key]=obj
surface=lambda x,y,m:env['terrain_surface'](x,y,env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],m)
env['viaduct']=env['Viaduct'](env['height'],surface)
minzu=env['MinzuAvenue'](env['viaduct'].road_level,surface)
env['river_bridges']={i:env['RiverBridge'](spec,env['height'],minzu.road_level,lambda x,y:max(surface(x,y,False),surface(x,y,True))) for i,spec in env['RIVER_BRIDGE_SPECS'].items()}
exec(compile(ast.Module(body=tree.body[start:end+1],type_ignores=[]),str(source),'exec'),env)
objects=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('Landmark_')]
assert len(objects)>=20,len(objects)
for obj in list(bpy.data.objects):
 if obj.type=='MESH' and obj not in objects:bpy.data.objects.remove(obj,do_unlink=True)
export_city(out/'landmark-context.glb')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p.relative_to(root)):sha(p) for folder in ['blender','data'] for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.json']}
inputs.update({name:sha(root/name) for name in ['public/data/geography.json','public/data/terrain.json']})
(out/'landmark-context-report.json').write_text(json.dumps({'status':'current production landmark geometry for horizontal road obstacles; full city pending','sourceStatementLines':[tree.body[start].lineno,tree.body[end].end_lineno],'meshNames':[o.name for o in objects],'inputHashes':inputs,'modelSha256':sha(out/'landmark-context.glb')},indent=2)+'\n')
print('Fresh landmark capture',len(objects),flush=True)
