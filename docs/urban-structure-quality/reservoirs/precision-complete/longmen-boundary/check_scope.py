from pathlib import Path
from collections import Counter
import json,hashlib
import numpy as np
from shapely.geometry import Polygon,shape
b=Path('work/urban-structure/p5/full-city-review/longmen-boundary');plan=json.loads((b/'plan.json').read_text());foot=shape(plan['dams'][0]['footprint']);report={}
def keys(faces,materials):
 result=Counter()
 for face,material in zip(faces,materials):
  q=[tuple(p) for p in face];start=min(range(3),key=lambda i:q[i:]+q[:i]);result[(int(material),tuple(q[start:]+q[:start]))]+=1
 return result
for profile in ['detail','smooth']:
 old=np.load(Path('work/urban-structure/p5/full-city-review/longmen-axis/before')/(profile+'.npz'));new=np.load(b/'after'/(profile+'.npz'));a=keys(old['triangles'],old['materials']);c=keys(new['triangles'],new['materials']);removed=a-c;added=c-a
 for material,face in list(removed)+list(added):
  p=Polygon(np.asarray(face)[:,:2]);assert p.difference(foot.buffer(.00002)).area*10000<.01
 for field in ['waterTriangles','waterIndices','waterCornerNormals','bankTriangles','bankCornerNormals']:assert np.array_equal(old[field],new[field]),field
 report[profile]={'removedFaces':sum(removed.values()),'addedFaces':sum(added.values()),'unchangedFaces':sum((a&c).values()),'changedFacesConfinedToSourceDam':True,'waterAndBankArraysExact':True}
report['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [b/'plan.json',Path(__file__),*[d/(p+'.npz') for d in [Path('work/urban-structure/p5/full-city-review/longmen-axis/before'),b/'after'] for p in ['detail','smooth']]]}
(b/'scope-audit.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='inputs'})
