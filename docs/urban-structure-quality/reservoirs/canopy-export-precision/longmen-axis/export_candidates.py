from pathlib import Path
import subprocess,json,time
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review/longmen-axis';stage=root/'work/urban-structure/p5/reservoirs/integration/budget/nanhu-staging';records=[]
for name,plan in [('before',stage/'data/reservoir-plans/longmen-reservoir-closure-v1.json'),('after',b/'plan.json')]:
 cmd=['/opt/homebrew/bin/blender','-b','--python-exit-code','1','--python',str(stage/'blender/check_reservoir_terrain.py'),'--','--scene-root',str(stage),'--plan',str(plan),'--output',str(b/name)]
 start=time.time()
 with (b/(name+'-export.log')).open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 records.append({'version':name,'command':cmd,'exitCode':r.returncode,'seconds':round(time.time()-start,2)});(b/'exports.json').write_text(json.dumps(records,indent=2)+'\n');print(name,r.returncode,flush=True)
 if r.returncode:raise SystemExit(r.returncode)
