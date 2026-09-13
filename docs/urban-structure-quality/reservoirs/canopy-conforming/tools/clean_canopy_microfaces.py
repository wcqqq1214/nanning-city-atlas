"""Apply the existing source-plan area floor without relaxing asset validation."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'scripts')
from prepare_local_canopy import MIN_CANOPY_AREA
b=Path('work/urban-structure/p5/full-city-review');source=b/'forest-candidate-nanhu.json';out=b/'forest-candidate-clean.json';assert not out.exists()
plan=json.loads(source.read_text());report={'status':'source candidate only; actual native/GLB and normal/visual checks pending','minimumAreaSceneUnits':MIN_CANOPY_AREA,'profiles':{}}
for region in plan['regions']:
 for profile in ['detail','smooth']:
  mesh=region[profile];triangles=np.asarray(mesh['points'])[mesh['triangles']]
  areas=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,2]/2
  assert np.all(areas>0),'Do not silently discard invalid source winding'
  removed=np.flatnonzero(areas<=MIN_CANOPY_AREA);loss=float(areas[removed].sum()*10000)
  assert loss<=.01,'Aggregate source coverage loss exceeds existing gate'
  keep=areas>MIN_CANOPY_AREA
  mesh['triangles']=[t for t,k in zip(mesh['triangles'],keep) if k]
  mesh['colors']=[c for c,k in zip(mesh['colors'],keep) if k]
  report['profiles'][region['id']+'/'+profile]={'beforeFaces':len(areas),'afterFaces':int(keep.sum()),'removedFaceIndices':removed.tolist(),'maximumLostCoverageSquareMeters':loss,'unchangedRetainedVerticesFacesAndColors':True}
report['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,Path(__file__),Path('scripts/prepare_local_canopy.py')]}
plan['microTriangleCleanup']=report
out.write_text(json.dumps(plan,separators=(',',':'))+'\n');report['outputSha256']=hashlib.sha256(out.read_bytes()).hexdigest();out.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:{j:v for j,v in r.items() if j!='removedFaceIndices'} for k,r in report['profiles'].items()},flush=True)
