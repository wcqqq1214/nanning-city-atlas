from pathlib import Path
import sys,json,struct,ast,hashlib
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path.cwd()/'scripts'))
from decoded_surface import face_arrays
from check_reduced_terrain_exports import match_faces
b=Path('work/urban-structure/p5/full-city-review/global-uncompressed-native')
tree=ast.parse(Path('blender/build_city.py').read_text());definition=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets));names={k.value:v.args[0].value for k,v in zip(definition.keys,definition.values)};labels=[names[k] for k in ['forest_deep','forest_jade','forest_light']]
reports={}
for name in ['nearby-detail','nearby-smooth','all-detail','all-smooth']:
 path=b/(name+'.glb');raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);binary=28+size
 def accessor(index):
  a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];assert 'byteStride' not in v
  dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];width={'SCALAR':1,'VEC3':3}[a['type']]
  return np.frombuffer(raw,dtype=dtype,count=a['count']*width,offset=binary+v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width)
 faces=[];normals=[];materials=[]
 for node in doc['nodes']:
  if 'mesh' not in node:continue
  for p in doc['meshes'][node['mesh']]['primitives']:
   f,n=face_arrays(SimpleNamespace(points=accessor(p['attributes']['POSITION']),normals=accessor(p['attributes']['NORMAL']),faces=accessor(p['indices']).reshape(-1,3)))
   faces.extend(f);normals.extend(n);materials.extend([labels.index(doc['materials'][p['material']]['name'])]*len(f))
 actual={'triangles':np.asarray(faces),'cornerNormals':np.asarray(normals),'materials':np.asarray(materials)}
 native=dict(np.load(b/(name+'.npz')))
 try:report={'passed':True,'geometry':match_faces(native,actual,position_meters=0,normal_degrees=.5)}
 except ValueError as e:report={'passed':False,'error':str(e)}
 report.update(nativeFaces=len(native['triangles']),actualFaces=len(actual['triangles']),sha256=hashlib.sha256(raw).hexdigest());reports[name]=report
 np.savez_compressed(b/(name+'-decoded.npz'),**actual)
 print(name,report,flush=True)
(b/'uncompressed-correspondence.json').write_text(json.dumps(reports,indent=2)+'\n')
