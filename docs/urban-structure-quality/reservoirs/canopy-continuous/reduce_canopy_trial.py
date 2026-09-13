import sys,json,hashlib
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import box
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from prepare_terrain_reduction import Reducer
base=root/'work/urban-structure/p5/full-city-review'
stage=root/'work/urban-structure/p5/reservoirs/integration/budget/summary-fix-staging'
registry=stage/'data/reservoir-terrain-registry.json'
paths=[stage/e['path'] for e in json.loads(registry.read_text())['plans']]
domain=shapely.union_all([box(*json.loads(p.read_text())['bounds']) for p in paths])
source=base/'canopy-production-native/all-smooth.npz'
inputs=np.load(source);triangles=inputs['triangles'];materials=inputs['materials']
r=Reducer(triangles,materials,.2,2)
inside=shapely.covered_by(shapely.polygons(triangles[:,:,:2]),domain)
for i in np.flatnonzero(~inside):r.protected.update(r.faces[int(i)])
a,m,o,report=r.run(progress=lambda n,a,t:print(n,a,round(t,2),flush=True))
p=base/'canopy-production-native/all-smooth-reduced.npz'
np.savez_compressed(p,triangles=a,materials=m,originFaceIndices=o)
report['outsideOrBoundaryFacesFrozen']=int((~inside).sum())
report['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,registry,*paths,Path(__file__),root/'scripts/prepare_terrain_reduction.py']}
p.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
