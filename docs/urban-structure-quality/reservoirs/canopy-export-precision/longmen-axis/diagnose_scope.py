from pathlib import Path
from collections import Counter
import json,hashlib
import numpy as np
from shapely.geometry import Polygon,shape
b=Path('work/urban-structure/p5/full-city-review/longmen-axis');plan=json.loads((b/'plan.json').read_text());foot=shape(plan['dams'][0]['footprint']);report={}
def keys(faces,materials):
 result=Counter()
 for face,material in zip(faces,materials):
  q=[tuple(p) for p in face];start=min(range(3),key=lambda i:q[i:]+q[:i]);result[(int(material),tuple(q[start:]+q[:start]))]+=1
 return result
for profile in ['detail','smooth']:
 old=np.load(b/'before'/(profile+'.npz'));new=np.load(b/'after'/(profile+'.npz'));a=keys(old['triangles'],old['materials']);c=keys(new['triangles'],new['materials']);removed=a-c;added=c-a
 outside=[]
 for material,face in list(removed)+list(added):
  p=Polygon(np.asarray(face)[:,:2]);area=p.difference(foot.buffer(.00002)).area*10000
  if area>=.01:outside.append({'material':material,'triangle':face,'outsideSquareMeters':area})
 print(profile,'outside examples',sorted(outside,key=lambda r:-r['outsideSquareMeters'])[:3],flush=True)
 for field in ['waterTriangles','waterIndices','waterCornerNormals','bankTriangles','bankCornerNormals']:print(field,np.array_equal(old[field],new[field]),flush=True)
 report[profile]={'removedFaces':sum(removed.values()),'addedFaces':sum(added.values()),'unchangedFaces':sum((a&c).values()),'changedFacesConfinedToSourceDam':not outside,'outsideFaces':outside,'waterAndBankArraysExact':all(np.array_equal(old[f],new[f]) for f in ['waterTriangles','waterIndices','waterCornerNormals','bankTriangles','bankCornerNormals'])}
report['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [b/'plan.json',Path(__file__),*[b/v/(p+'.npz') for v in ['before','after'] for p in ['detail','smooth']]]}
(b/'scope-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='inputs'})
