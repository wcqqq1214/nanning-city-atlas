"""Continue only after the current road and native-ground jobs complete."""
from pathlib import Path
import json,subprocess,sys,time
root=Path.cwd();out=root/'work/p5/final-integration';records=json.loads((out/'road-rebuild-report.json').read_text())
assert len(records)==9 and all(r['exitCode']==0 for r in records),'Complete all road rebuild steps first'
native=json.loads((out/'native-ground/report.json').read_text());assert set(native['profiles'])=={'detail','smooth'}
py=sys.executable;bl='/opt/homebrew/bin/blender'
commands=[('road-ground-audit',[py,'scripts/check_site_road_support.py','--native','work/p5/final-integration/native-ground','--roads','data','--plan','data/block-grading-plan.json','--context','work/terrain-resample/context','--output','work/p5/final-integration/road-ground-audit.json']),
('access-plan',[py,'scripts/prepare_site_access.py','--grading','data/block-grading-plan.json','--native-terrain','work/p5/final-integration/native-ground','--native-storage','--output','work/p5/final-integration/access-plan.json']),
('access-runtime',[bl,'-b','--python-exit-code','1','--python','blender/check_site_access_runtime.py','--','--candidate','work/p5/final-integration/access-plan.json','--output','work/p5/final-integration/access-runtime','--export']),
('access-context',[py,'scripts/prepare_site_access_context.py','--root',str(root),'--runtime',str(out/'access-runtime'),'--candidate',str(out/'access-plan.json'),'--output',str(out/'access-runtime/sources.json')]),
('final-support',[py,'scripts/prepare_building_support.py','--geography','public/data/geography.json','--detail','work/p5/final-integration/access-runtime/detail.glb','--smooth','work/p5/final-integration/access-runtime/smooth.glb','--context-sources','work/p5/final-integration/access-runtime/sources.json','--output','work/p5/final-integration/final-support.json'])]
results=[]
for name,cmd in commands:
 print('Starting',name,flush=True);start=time.time()
 with (out/(name+'.log')).open('w') as log:process=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 results.append({'step':name,'command':cmd,'exitCode':process.returncode,'seconds':round(time.time()-start,2)})
 (out/'access-rebuild-report.json').write_text(json.dumps(results,indent=2)+'\n');print('Finished',name,process.returncode,flush=True)
 if process.returncode:raise SystemExit(process.returncode)
