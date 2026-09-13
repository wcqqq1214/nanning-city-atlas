from pathlib import Path
from collections import Counter
import hashlib,json,numpy as np
from shapely.geometry import Polygon,shape
b=Path(__file__).resolve().parent;foot=shape(json.loads((b/'plan.json').read_text())['dams'][0]['footprint'])
def outside(data):
 rows={}
 for i,(face,material) in enumerate(zip(data['triangles'],data['materials'])):
  if Polygon(face[:,:2]).difference(foot.buffer(.00002)).area*10000<=.01:continue
  xy=[tuple(p[:2]) for p in face];start=min(range(3),key=lambda k:xy[k:]+xy[:k]);key=(int(material),tuple(xy[start:]+xy[:start]))
  assert key not in rows,'Ambiguous outside topology'
  rows[key]=(np.roll(face,-start,axis=0),np.roll(data['cornerNormals'][i],-start,axis=0))
 return rows
report={}
for profile in ['detail','smooth']:
 old=dict(np.load(b/'before'/(profile+'.npz')));new=dict(np.load(b/'after'/(profile+'.npz')));a=outside(old);c=outside(new)
 assert a.keys()==c.keys(),'Outside horizontal topology/material changed'
 heights=[];normal=[];changed=0
 for key,(f,n) in a.items():
  g,m=c[key];error=np.abs(f[:,2]-g[:,2])*100;heights.extend(error)
  changed+=int(np.any(error>0));denom=np.linalg.norm(n,axis=1)*np.linalg.norm(m,axis=1)
  valid=denom>1e-15;normal.extend(np.degrees(np.arccos(np.clip((n[valid]*m[valid]).sum(axis=1)/denom[valid],-1,1))))
 exact={field:bool(np.array_equal(old[field],new[field])) for field in ['waterTriangles','waterIndices','waterCornerNormals','bankTriangles','bankCornerNormals']}
 assert all(exact.values())
 report[profile]={'outsideFaces':len(a),'outsideXYTopologyAndMaterialExact':True,'outsideFacesWithZDifference':changed,'maximumOutsideHeightDifferenceMeters':max(heights),'maximumOutsideNormalDifferenceDegrees':max(normal),'waterAndBankExact':exact,'exactOutsideGeometryPreserved':changed==0}
report['status']='diagnostic only; exact scope assertion failed, small outside-boundary drift quantified; full visual acceptance pending'
report['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),b/'plan.json',*[b/v/(q+'.npz') for v in ['before','after'] for q in ['detail','smooth']]]}
(b/'scope-quantified.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='inputs'})
