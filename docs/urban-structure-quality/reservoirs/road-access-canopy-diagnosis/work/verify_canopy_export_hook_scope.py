from pathlib import Path
from types import SimpleNamespace
import sys,importlib.util,json
source=Path.cwd()/'blender/gltf_export.py';spec=importlib.util.spec_from_file_location('scope_policy',source);policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
extract=policy.primitive_extract;cls=extract.PrimitiveCreator;attribute='_PrimitiveCreator__get_normals';real=getattr(cls,attribute);original_bpy=policy.bpy;original_draco=getattr(policy.draco,'__encode_node');rounding=extract.ROUNDING_DIGIT;results=[]
try:
 for fail in [False,True]:
  calls=[]
  def normal(creator):
   calls.append({'name':creator.blender_mesh.name,'rounding':extract.ROUNDING_DIGIT})
   if fail and creator.blender_mesh.name.startswith('Vegetation_'):raise RuntimeError('deliberate normal extraction failure')
  setattr(cls,attribute,normal)
  def export(**kwargs):
   for name in ['Terrain_0_0','Vegetation_all_canopy_0_0']:
    getattr(cls,attribute)(SimpleNamespace(blender_mesh=SimpleNamespace(name=name)))
  policy.bpy=SimpleNamespace(ops=SimpleNamespace(export_scene=SimpleNamespace(gltf=export)))
  try:policy.export_city(Path('unused.glb'))
  except RuntimeError as e:assert fail and str(e)=='deliberate normal extraction failure'
  else:assert not fail
  assert calls==[{'name':'Terrain_0_0','rounding':rounding},{'name':'Vegetation_all_canopy_0_0','rounding':15}]
  assert getattr(cls,attribute) is normal
  assert getattr(policy.draco,'__encode_node') is original_draco
  assert extract.ROUNDING_DIGIT==rounding
  results.append({'forcedFailure':fail,'calls':calls,'hooksAndRoundingRestored':True})
finally:
 setattr(cls,attribute,real);policy.bpy=original_bpy
out=Path('work/urban-structure/p5/full-city-review/canopy-export-hook-scope.json');out.write_text(json.dumps(results,indent=2)+'\n');print('PASS: canopy-only normal precision; normal extraction failure and success restore both hooks and rounding')
