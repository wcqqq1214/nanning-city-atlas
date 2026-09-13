import sys,json,hashlib
from pathlib import Path
import numpy as np
import shapely
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from prepare_building_support import TerrainSurface
b=root/'work/urban-structure/p5/full-city-review/canopy-production-native'
t=root/'work/urban-structure/p5/reservoirs/integration/budget/summary-fix-staging/work/p5/final-integration/access-runtime'
report={}
for profile in ['smooth','detail']:
 groundpath=t/(profile+'.npz');ground=TerrainSurface(np.load(groundpath)['triangles'])
 surface=shapely.union_all(shapely.polygons(ground.triangles[:,:,:2]))
 for region in ['nearby','all']:
  p=b/(region+'-'+profile+'.npz');canopy=TerrainSurface(np.load(p)['triangles'])
  area=shapely.union_all(shapely.polygons(canopy.triangles[:,:,:2]));missing=area.difference(surface)
  row={'missingSquareMeters':missing.area*10000,'outsideEnvelopeSquareMeters':{}}
  for mm in [.1,.25,.5,1,2]:
   row['outsideEnvelopeSquareMeters'][str(mm)+'mm']=area.difference(surface.buffer(mm/100000,quad_segs=8)).area*10000
  row['inputs']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [groundpath,p,Path(__file__)]}
  report[region+'/'+profile]=row
  (b/'coverage-gap-width.json').write_text(json.dumps(report,indent=2)+'\n')
  print(region,profile,row,flush=True)
