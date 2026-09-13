from pathlib import Path
import sys,json,hashlib
import numpy as np
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from validate_cultural_landmarks import glb
from decoded_surface import face_arrays
stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging';out=root/'work/urban-structure/p5/full-city-review/conforming-decoded';out.mkdir(exist_ok=False);report={}
for profile,name in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
 source=stage/'public/models'/name;doc,decode=glb(source);groups={key:[] for key in ['terrain','nearby','all']}
 for node in doc['nodes']:
  if 'mesh' not in node:continue
  name=node.get('name','');key='terrain' if name.startswith('Terrain_') else next((r for r in ['nearby','all'] if name.startswith('Vegetation_'+r+'_canopy_')),None)
  if key is None:continue
  if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Expected baked positions')
  for p in doc['meshes'][node['mesh']]['primitives']:
   faces,normals=face_arrays(decode(p));groups[key].append(faces)
 record={'input':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'groups':{}}
 for key,rows in groups.items():
  triangles=np.concatenate(rows);p=out/(key+'-'+profile+'.npz');np.savez_compressed(p,triangles=triangles)
  record['groups'][key]={'triangles':len(triangles),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 report[profile]=record;(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(profile,record['groups'],flush=True)
