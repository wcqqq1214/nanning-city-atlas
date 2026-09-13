from pathlib import Path
from collections import defaultdict,Counter
import sys,ast,json,hashlib,numpy as np
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from check_canopy_exports import decoded
b=root/'work/urban-structure/p5/full-city-review/global-conforming-native';tree=ast.parse((root/'blender/build_city.py').read_text());definition=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets));names={k.value:v.args[0].value for k,v in zip(definition.keys,definition.values)};labels=[names[k] for k in ['forest_deep','forest_jade','forest_light']]
def key(t,m):
 points=[tuple(v) for v in t];return (int(m),min(tuple(points[i:]+points[:i]) for i in range(3)))
reports={}
for name in ['nearby-smooth','all-detail','all-smooth']:
 source=b/(name+'.npz');model=b/(name+'.glb');a=dict(np.load(source));z=decoded(model,labels);old=defaultdict(list);new=defaultdict(list)
 for i,(t,m) in enumerate(zip(a['triangles'],a['materials'])):old[key(t,m)].append(i)
 for i,(t,m) in enumerate(zip(z['triangles'],z['materials'])):new[key(t,m)].append(i)
 missing=[];normals=[]
 for k,indices in old.items():
  if len(indices)>len(new[k]):
   for i in indices[:len(indices)-len(new[k])]:
    t=a['triangles'][i];missing.append({'nativeFace':i,'triangle':t.tolist(),'area3D':float(np.linalg.norm(np.cross(t[1]-t[0],t[2]-t[0]))/2),'normals':a['cornerNormals'][i].tolist()})
  for i in indices:
   if not new[k]:continue
   best=180.
   for j in new[k]:
    for p in [(0,1,2),(1,2,0),(2,0,1)]:
     if not np.array_equal(a['triangles'][i],z['triangles'][j][list(p)]):continue
     n=a['cornerNormals'][i];m=z['cornerNormals'][j][list(p)];ln=np.linalg.norm(n,axis=1);lm=np.linalg.norm(m,axis=1);den=ln*lm;cos=np.divide((n*m).sum(axis=1),den,out=np.ones(3),where=den>1e-20);angle=np.degrees(np.arccos(np.clip(cos,-1,1)));angle[(ln>1e-10)&(lm<=1e-10)]=180;angle[ln<=1e-10]=0;best=min(best,float(angle.max()))
   if best>.5:
    t=a['triangles'][i];normals.append({'nativeFace':i,'bestMaximumNormalDifferenceDegrees':best,'area3D':float(np.linalg.norm(np.cross(t[1]-t[0],t[2]-t[0]))/2),'triangle':t.tolist(),'nativeNormals':a['cornerNormals'][i].tolist(),'actualNormals':z['cornerNormals'][new[k][0]].tolist()})
 reports[name]={'nativeFaces':len(a['triangles']),'actualFaces':len(z['triangles']),'missingFaces':missing,'normalFailures':normals,'unexpectedPositionFaces':sum(len(v) for k,v in new.items() if k not in old),'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,model]}}
 print(name,'missing',len(missing),'normal failures',len(normals),flush=True)
(b/'exact-export-diagnostic.json').write_text(json.dumps(reports,indent=2)+'\n')
