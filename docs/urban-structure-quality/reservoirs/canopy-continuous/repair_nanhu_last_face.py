"""Reproduce the final single-face refinement after enabling the Nanhu sampler."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
import shapely
sys.path.insert(0,'scripts')
from prepare_local_canopy import recut
b=Path('work/urban-structure/p5/full-city-review')
source=b/'forest-candidate-continuous.json'
plan=json.loads(source.read_text());region=next(r for r in plan['regions'] if r['id']=='nearby')
audit=b/'canopy-nanhu-native/nearby-smooth-clearance.json';native=b/'canopy-nanhu-native/nearby-smooth.npz'
terrain=Path('work/urban-structure/p5/reservoirs/integration/budget/summary-fix-staging/work/p5/final-integration/access-runtime/smooth.npz')
ids=json.loads(audit.read_text())['failedClearanceFaceIndices'];assert len(ids)==1
triangles=np.load(native)['triangles'][ids]
domain=shapely.union_all(shapely.polygons(triangles[:,:,:2])).buffer(.0001,join_style='mitre')
region['smooth'],record=recut(region['smooth'],np.load(terrain)['triangles'],domain,.002,True)
record['sourceFailedFaces']=ids;record['repairAreaSquareMeters']=domain.area*10000
plan['nanhuSamplerLastFaceRepair']=record
output=b/'forest-candidate-nanhu.json'
if output.exists():
 assert json.loads(output.read_text())==plan,'Existing candidate differs; do not overwrite'
else:output.write_text(json.dumps(plan,separators=(',',':'))+'\n')
record['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,audit,native,terrain,Path(__file__),Path('scripts/prepare_local_canopy.py')]}
record['outputSha256']=hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.report.json').write_text(json.dumps(record,indent=2)+'\n')
