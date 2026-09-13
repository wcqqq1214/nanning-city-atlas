from pathlib import Path
import sys,json,hashlib
import numpy as np
import shapely
from shapely.geometry import box
sys.path.insert(0,str(Path.cwd()/'scripts'))
from conform_canopy_edges import conform_edges
b=Path('work/urban-structure/p5/full-city-review');source=b/'forest-candidate-conforming-v2.json';output=b/'forest-candidate-global-conforming-v2.json'
assert not output.exists()
plan=json.loads(source.read_text());report={}
for region in plan['regions']:
 if region['id'] not in ['nearby','all']:continue
 for profile in ['detail','smooth']:
  old=region[profile]
  new,r=conform_edges(old,triangulation='boundary')
  a=shapely.union_all(shapely.polygons(np.asarray(old['points'])[old['triangles'],:2]));c=shapely.union_all(shapely.polygons(np.asarray(new['points'])[new['triangles'],:2]))
  r['coverageDifferenceSquareMeters']=a.symmetric_difference(c).area*10000
  assert r['coverageDifferenceSquareMeters']<=.01
  region[profile]=new;report[region['id']+'-'+profile]=r;print(region['id'],profile,r,flush=True)
output.write_text(json.dumps(plan,separators=(',',':'))+'\n')
report['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,Path(__file__),Path('scripts/conform_canopy_edges.py')]}
report['outputSha256']=hashlib.sha256(output.read_bytes()).hexdigest();output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
