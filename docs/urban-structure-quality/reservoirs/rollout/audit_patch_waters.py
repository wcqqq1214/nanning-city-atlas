"""Frozen candidate boundary inventory; proximity does not establish hydraulics."""
import sys,json,math,hashlib
from pathlib import Path
import numpy as np
import rasterio
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
sys.path.insert(0,str(Path.cwd()/'scripts'))
from prepare_geodata import geom_for
from audit_reservoir_sources import SourceRaster,statistics
root=Path.cwd();base=root/'work/urban-structure/p5/reservoirs/rollout';geo_path=base/'candidate.json';geo=json.loads(geo_path.read_text());snapshot_path=root/'work/geodata/osm.json';snapshot=json.loads(snapshot_path.read_text());raster_path=root/'work/geodata/Copernicus_DSM_COG_10_N22_00_E108_00_DEM.tif'
water_tag=lambda e:e.get('tags',{}).get('natural')=='water' or e.get('tags',{}).get('waterway')=='riverbank'
elements=snapshot['elements'];members={m['ref'] for e in elements if e['type']=='relation' and water_tag(e) for m in e.get('members',[]) if m['type']=='way'}
cx,cy=geo['center'];kx=1113.2*math.cos(math.radians(cy));project=lambda lon,lat:((lon-cx)*kx,(lat-cy)*1113.2);clip=box(*geo['bounds']);waters=[]
for e in elements:
 if not water_tag(e) or (e['type']=='way' and e['id'] in members):continue
 p=geom_for(e,project=project,clip=clip)
 if p is not None and not p.is_empty and p.area>0:
  # Actual serialized coordinate arithmetic; do not propagate precision-grid metadata.
  from shapely import from_wkb
  waters.append((f"osm/{e['type']}/{e['id']}",e,from_wkb(p.wkb)))
records=[];sources={};paths=[geo_path,snapshot_path,raster_path,Path(__file__)]
with rasterio.open(raster_path) as dataset:
 sampler=SourceRaster(dataset,geo['center'])
 for path in sorted(base.glob('*/plan.json')):
  plan=json.loads(path.read_text());paths.append(path);patch=box(*plan['bounds']);selected={e['geographyWaterIndex'] for e in plan['waterBodies']};focus=unary_union([Polygon(geo['water'][i][0],geo['water'][i][1:]) for i in selected]);xy=np.asarray(plan['points']);weights=np.asarray(plan['weights']);neighbors=[]
  for index,rings in enumerate(geo['water']):
   water=Polygon(rings[0],rings[1:]);inside=water.intersection(patch)
   if index in selected or inside.area<1e-10:continue
   boundary=water.boundary.intersection(patch);near=np.array([boundary.distance(Point(p))<.0001 for p in xy]);matches=[]
   for ref,e,p in waters:
    area=p.intersection(water).area
    if area<.0001:continue
    matches.append({'sourceRef':ref,'sourceCoverageFraction':area/p.area,'displayCoverageFraction':area/water.area})
    if ref not in sources:sources[ref]={'sourceRef':ref,'feature':e,'rawPixelStatisticsMetersByInset':{str(i):statistics(sampler.pixels(p.buffer(-i/100))) for i in [0,10,30]}}
   neighbors.append({'index':index,'areaInPatchSquareMeters':inside.area*10000,'distanceToSelectedWaterMeters':inside.distance(focus)*100,'nearBoundaryVertexCount':int(near.sum()),'maximumBoundaryRestoreWeight':float(weights[near].max()) if near.any() else None,'sourceMatches':sorted(matches,key=lambda m:-m['displayCoverageFraction']),'needsInterfaceReview':True})
  records.append({'id':plan['id'],'bounds':plan['bounds'],'selectedWaterIndices':sorted(selected),'otherWaters':neighbors})
for a in records:
 a['overlappingOtherPatches']=[b['id'] for b in records if a!=b and box(*a['bounds']).intersection(box(*b['bounds'])).area>1e-8]
 t=json.loads((root/'work/urban-structure/p5/staging/data/reservoir-terrain-plan.json').read_text());a['overlapWithTianbaoSquareMeters']=box(*a['bounds']).intersection(box(*t['bounds'])).area*10000
 assert not a['overlappingOtherPatches'] and a['overlapWithTianbaoSquareMeters']==0
report={'status':'source and interface inventory; no adjacent water levels applied','groups':records,'sourceWaterEvidence':list(sources.values()),'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(base/'patch-water-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for r in records:print(r['id'],[(w['index'],w['maximumBoundaryRestoreWeight'],[(m['sourceRef'],round(m['displayCoverageFraction'],3)) for m in w['sourceMatches']]) for w in r['otherWaters']],flush=True)
