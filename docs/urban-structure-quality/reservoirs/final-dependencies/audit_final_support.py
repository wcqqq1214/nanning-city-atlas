from pathlib import Path
import hashlib,json,sys
root=Path.cwd();sys.path.insert(0,str(root/'blender'))
from building_support_plan import BuildingSupportPlan
from building_placement import prepared,envelope,validate_road_envelope
from reservoir_runtime import dedicated_dam,DAM_IDS
from city_visibility import CityVisibility
from railways import REMOVED_BUILDINGS
out=root/'work/p5/final-integration';geo=json.loads((root/'public/data/geography.json').read_text());vis=CityVisibility(geo,json.loads((root/'data/landmarks.json').read_text()));support=BuildingSupportPlan.read(out/'final-support.json',root);base=BuildingSupportPlan.read(out/'base-support.json',root)
roads={p:json.loads((root/f'data/road-solids-{p}.json').read_text()) for p in ['detail','smooth']};captured={p:{r['index']:r for r in meta['buildingEnvelopes']} for p,meta in roads.items()};records=[];excluded=[]
for i,b in enumerate(geo['buildings']):
 if dedicated_dam(b):excluded.append(b['id']);continue
 if not prepared(b) or not vis.building_visible(b,railway_hidden=i in REMOVED_BUILDINGS):continue
 before=envelope(b,base);after=envelope(b,support)
 for profile in roads:validate_road_envelope(i,b,after,captured[profile])
 records.append({'id':b['id'],'kind':after['kind'],'siteReviewRequired':after['siteReviewRequired'],'maximumBaseToFinalDifferenceMeters':max(abs(before[k]-after[k])*100 for k in ['bottom','top'])})
assert set(excluded)==DAM_IDS
report={'status':'final support matches both road captures; full city and visual review remain pending','visiblePreparedBuildings':len(records),'compoundBuildings':sum(r['kind']=='compound' for r in records),'largeReliefSiteReviews':sum(r['siteReviewRequired'] for r in records),'maximumBaseToFinalDifferenceMeters':max(r['maximumBaseToFinalDifferenceMeters'] for r in records),'dedicatedDamsExcluded':excluded,'records':records,'inputs':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/'base-support.json',out/'final-support.json',root/'data/road-solids-detail.json',root/'data/road-solids-smooth.json']}}
(out/'final-support-audit.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k not in ['records','inputs','dedicatedDamsExcluded']})
