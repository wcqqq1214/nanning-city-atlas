from pathlib import Path
import sys,json,hashlib,numpy as np,shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
root=Path.cwd();stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging';sys.path[:0]=[str(stage/'scripts'),str(stage/'blender')]
from validate_ground_roads import decoded_faces,planes,load_plan
from site_access_plan import SiteAccessPlan
source=stage/'work/p5/precision-rebuild/access-plan.json';access=SiteAccessPlan.read(source,stage);plan,path=load_plan();paved=unary_union([Polygon(p[0],p[1:]) for tier in plan['surfaces'] for p in tier]);reports=[]
for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
 groups,_,_=decoded_faces(filename);actual=unary_union(planes(groups['road'])[0]);patches=[]
 for site in access.payload['sites'].values():
  r=site[profile];p=np.asarray(r['topPoints']);patches.extend(Polygon(p[f,:2]) for f in r['triangles'])
 apron=unary_union(patches);expected=shapely.transform(paved,lambda xy:xy*np.array([1,-1]));extended=shapely.transform(paved.union(apron),lambda xy:xy*np.array([1,-1]))
 before=actual.difference(expected.buffer(.003));after=actual.difference(extended.buffer(.003));reports.append({'profile':profile,'outsideOldExpectedSquareMeters':before.area*10000,'outsideWithDeclaredAccessSquareMeters':after.area*10000,'declaredAccessAreaSquareMeters':apron.area*10000,'outsideOldBounds':before.bounds,'existingOutsideAreaLimitSquareMeters':10.0,'scope':'footprint diagnostic only; other road checks not rerun with extended domain'})
 print(reports[-1],flush=True)
out=root/'work/urban-structure/p5/full-city-review/road-access-scope-diagnostic.json';out.write_text(json.dumps({'profiles':reports,'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,path,Path(__file__),*[stage/'public/models'/f for f in ['nanning-city.glb','nanning-city-mobile.glb']]]}},indent=2)+'\n')
