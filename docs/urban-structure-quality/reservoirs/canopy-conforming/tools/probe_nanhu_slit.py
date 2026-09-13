from pathlib import Path
import sys,json
import numpy as np
sys.path.insert(0,str(Path.cwd()/'scripts'))
from validate_cultural_landmarks import glb
base=Path('work/urban-structure/p5/full-city-review')
source=Path('work/urban-structure/p5/reservoirs/integration/budget/nanhu-staging/public/models/nanning-city-mobile.glb')
doc,decode=glb(source)
eye=np.array([60.,4.,11.]);forward=np.array([56.,.5,6.])-eye;forward/=np.linalg.norm(forward)
right=np.cross(forward,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,forward)
pixels=[(414,390),(445,427),(444,427),(446,427),(482,463)]
results=[]
for px,py in pixels:
 direction=forward+right*((px/1280*2-1)*1.6*np.tan(np.radians(20)))+up*((1-py/800*2)*np.tan(np.radians(20)));direction/=np.linalg.norm(direction)
 hits=[]
 for node in doc['nodes']:
  if 'mesh' not in node:continue
  for pi,p in enumerate(doc['meshes'][node['mesh']]['primitives']):
   d=decode(p);tri=np.asarray(d.points,dtype=float)[d.faces]
   assert not any(k in node for k in ['matrix','translation','rotation','scale']),node
   e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];h=np.cross(direction,e2);det=np.sum(e1*h,axis=1);valid=abs(det)>1e-12
   inv=np.divide(1,det,out=np.zeros_like(det),where=valid);s=eye-tri[:,0];u=inv*np.sum(s*h,axis=1);q=np.cross(s,e1);v=inv*(q@direction);t=inv*np.sum(e2*q,axis=1)
   indices=np.flatnonzero(valid&(u>=0)&(v>=0)&(u+v<=1)&(t>0))
   for i in indices:
    hits.append({'node':node['name'],'primitive':pi,'face':int(i),'distance':float(t[i]),'point':(eye+t[i]*direction).tolist(),'triangle':tri[i].tolist(),'material':doc['materials'][p['material']]['name']})
 hits.sort(key=lambda r:r['distance']);results.append({'pixel':[px,py],'hits':hits[:5]});print(results[-1],flush=True)
(base/'nanhu-slit-raycast.json').write_text(json.dumps(results,indent=2)+'\n')
