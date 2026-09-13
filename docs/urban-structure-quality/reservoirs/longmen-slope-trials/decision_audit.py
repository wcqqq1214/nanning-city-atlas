"""Report rejected Longmen trials; do not treat target fields as native exports."""
from pathlib import Path
import hashlib,json,numpy as np
root=Path.cwd();base=root/'work/urban-structure/p5/reservoirs/integration/budget';out=root/'work/urban-structure/p5/reservoirs/slope-calibration/longmen';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def stats(t,material):
 normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);area=abs(normal[:,2])*5000
 mask=(material==1)&(area>=1);ids=np.flatnonzero(mask)
 grade=np.linalg.norm(normal[ids,:2],axis=1)/abs(normal[ids,2]);a=area[ids];order=np.argsort(grade)
 worst=ids[grade.argmax()]
 return {'faceCountAtLeast1m2':len(ids),'maximumDisplayGrade':float(grade.max()),'areaWeightedMeanDisplayGrade':float(np.average(grade,weights=a)),'areaWeightedP95DisplayGrade':float(grade[order[np.searchsorted(np.cumsum(a[order]),.95*a.sum())]]),'worstTriangleAreaSquareMeters':float(area[worst]),'worstTriangleSceneXYZ':t[worst].tolist(),'worstTriangleCenterSceneXYZ':t[worst].mean(axis=0).tolist()}
report={'decision':'Neither trial activated; preserve source footprint and estimated water levels. Proceed with integration, retain steep-slope visual review as unresolved.','metrics':'Display rise/run including terrain exaggeration 1.35; dam-material triangles with horizontal area at least 1 m². Not engineering slopes.','profiles':{},'inputs':{},'limitations':['Linear native exports predate final boundary-tolerance plan; compare actual native arrays only, not that later plan.','Narrow-crest statistics are target-field estimates inside fully weighted dam faces, not Blender or visual acceptance.','No reliable engineering crest dimensions or dam material established; water heights and crest parameters remain display estimates.']}
for profile in ['detail','smooth']:
 report['profiles'][profile]={}
 for version,path in [('accepted',base/'candidates/longmen-reservoir-closure-v1/native'/f'{profile}.npz'),('linearRejected',out/'native'/f'{profile}.npz')]:
  data=np.load(path);report['profiles'][profile][version]=stats(data['triangles'],data['materials']);report['inputs'][str(path.relative_to(root))]=sha(path)
p=out/'narrow-crest/plan.json';plan=json.loads(p.read_text());ids=np.asarray(plan['triangles']);material=np.asarray([1 if key=='dam_slope' else 0 for key in plan['materials']]);mask=material==1
assert np.all(np.asarray(plan['weights'])[ids[mask]]==1)
xyz=np.column_stack((plan['points'],np.asarray(plan['targetMeters'])*1.35/100));report['narrowCrestTargetField']=stats(xyz[ids],material);report['inputs'][str(p.relative_to(root))]=sha(p)
old=json.loads((base/'staging/data/reservoir-plans/longmen-reservoir-closure-v1.json').read_text());assert old['waterBodies']==plan['waterBodies'];assert old['dams'][0]['footprint']==plan['dams'][0]['footprint'];report['narrowSourceWaterAndDamFootprintUnchanged']=True
(out/'decision.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
