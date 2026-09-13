from pathlib import Path
import subprocess,json,hashlib,time,sys
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review/longmen-axis';old=root/'work/urban-structure/p5/reservoirs/integration/budget/nanhu-staging/data/reservoir-plans/longmen-reservoir-closure-v1.json';records=[]
for name,plan in [('before',old),('after',b/'plan.json')]:
 views={'planSha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'views':[{'name':'dam-profile','target':[-42.35,86.46,1.3],'orthoScale':1.4,'cameraOffsetFactors':[0,-1,.65]},{'name':'dam-plan','target':[-42.35,86.46,1.3],'orthoScale':1.3,'cameraOffsetFactors':[0,-.05,1]}]}
 extra=b/(name+'-views.json');extra.write_text(json.dumps(views,indent=2)+'\n')
 commands=[('audit',[sys.executable,'scripts/check_reservoir_exports.py','--plan',str(plan),'--directory',str(b/name),'--output',str(b/(name+'-audit.json'))]),('render',['/opt/homebrew/bin/blender','-b','--python-exit-code','1','--python','blender/render_reservoir_terrain.py','--','--plan',str(plan),'--exports',str(b/name),'--output',str(b/(name+'-views')),'--no-shadows','--extra-views',str(extra)])]
 for phase,cmd in commands:
  with (b/(name+'-'+phase+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  records.append({'version':name,'phase':phase,'exitCode':r.returncode,'command':cmd});(b/'review-result.json').write_text(json.dumps(records,indent=2)+'\n');print(name,phase,r.returncode,flush=True)
  if r.returncode:raise SystemExit(r.returncode)
