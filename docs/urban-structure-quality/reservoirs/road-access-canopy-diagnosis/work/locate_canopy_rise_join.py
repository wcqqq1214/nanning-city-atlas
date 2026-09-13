from pathlib import Path
import numpy as np,shapely,json,hashlib
from shapely.geometry import LineString
from shapely.strtree import STRtree
b=Path('work/urban-structure/p5/full-city-review');source=b/'forest-candidate-conforming-v2.json';plan=json.loads(source.read_text());mesh=next(r for r in plan['regions'] if r['id']=='all')['smooth'];points=np.asarray(mesh['points']);used=np.unique(mesh['triangles']);xy,unique=np.unique(points[used,:2],axis=0,return_index=True);ids=used[unique];tree=STRtree(shapely.points(xy));tolerance=1e-9;best=None
for fi,face in enumerate(mesh['triangles']):
 for ai,bi in zip(face,face[1:]+face[:1]):
  a,bp=points[ai],points[bi];d=bp[:2]-a[:2];length2=float(d@d)
  if length2<=tolerance*tolerance:continue
  for c in tree.query(LineString([a[:2],bp[:2]]).buffer(tolerance,cap_style='square')):
   index=int(ids[c])
   if index in face:continue
   p=points[index];t=float((p[:2]-a[:2])@d/length2)
   if t*np.sqrt(length2)<=tolerance or (1-t)*np.sqrt(length2)<=tolerance:continue
   if np.linalg.norm(p[:2]-a[:2]-t*d)>tolerance:continue
   difference=abs(float(p[2]-a[2]-t*(bp[2]-a[2])))*100
   if best is None or difference>best['differenceMeters']:
    best={'face':fi,'edgeIndices':[ai,bi],'stationIndex':index,'edge':[a.tolist(),bp.tolist()],'station':p.tolist(),'edgeFraction':t,'differenceMeters':difference,'interpolatedEdgeRiseMeters':float((a[2]+t*(bp[2]-a[2]))*100)}
record={'scope':'largest original rise mismatch joined by conforming; no final ground or visual inference','maximum':best,'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};(b/'canopy-largest-rise-join.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2),flush=True)
