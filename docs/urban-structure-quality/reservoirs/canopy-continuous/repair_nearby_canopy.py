import json,sys,hashlib
from pathlib import Path
import numpy as np
import shapely
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from prepare_local_canopy import recut
base=root/'work/urban-structure/p5/full-city-review'
source=base/'forest-candidate-coplanar.json';plan=json.loads(source.read_text())
region=next(r for r in plan['regions'] if r['id']=='nearby')
reports={};inputs=[source,Path(__file__),root/'scripts/prepare_local_canopy.py']
for profile in ['detail','smooth']:
 path=base/('canopy-production-native/nearby-'+profile+'.npz')
 audit=path.with_name(path.stem+'-clearance.json')
 terrain=root/('work/urban-structure/p5/reservoirs/integration/budget/summary-fix-staging/work/p5/final-integration/access-runtime/'+profile+'.npz')
 inputs.extend([path,audit,terrain]);ids=json.loads(audit.read_text())['failedClearanceFaceIndices']
 triangles=np.load(path)['triangles'][ids]
 domain=shapely.union_all(shapely.polygons(triangles[:,:,:2])).buffer(.0001,join_style='mitre')
 mesh,report=recut(region[profile],np.load(terrain)['triangles'],domain,.002,True)
 region[profile]=mesh
 report['repairDomainSquareMeters']=domain.area*10000
 report['sourceFailedFaces']=len(ids)
 reports[profile]=report
 print(profile,report,flush=True)
output=base/'forest-candidate-continuous.json'
reports['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
plan['continuousCanopyRepair']=reports
output.write_text(json.dumps(plan,separators=(',',':'))+'\n')
output.with_suffix('.report.json').write_text(json.dumps(reports,indent=2)+'\n')
