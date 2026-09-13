import json,subprocess,sys
from pathlib import Path
root=Path.cwd();base=root/'work/urban-structure/p5/reservoirs/rollout';results=[]
for name in sys.argv[1:]:
 directory=base/name;native=directory/'native';plan=directory/'plan.json'
 cmds=[('native-export',['/opt/homebrew/bin/blender','--background','--python-exit-code','1','--python',str(root/'blender/check_reservoir_terrain.py'),'--','--scene-root',str(root/'work/urban-structure/p5/staging'),'--plan',str(plan),'--output',str(native)]),
       ('native-audit',[str(root/'work/venv/bin/python'),str(root/'scripts/check_reservoir_terrain.py'),'--plan',str(plan),'--exports',str(native),'--output',str(directory/'native-audit.json')]),
       ('compressed-audit',[str(root/'work/venv/bin/python'),str(root/'scripts/check_reservoir_exports.py'),'--plan',str(plan),'--directory',str(native),'--output',str(directory/'compressed-audit.json')]),
       ('render',['/opt/homebrew/bin/blender','--background','--python-exit-code','1','--python',str(root/'blender/render_reservoir_terrain.py'),'--','--plan',str(plan),'--exports',str(native),'--output',str(directory/'views'),'--adaptive-height','--no-shadows'])]
 for step,cmd in cmds:
  with (directory/(step+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  results.append({'group':name,'step':step,'command':cmd,'exitCode':r.returncode});(base/('validation-commands-'+sys.argv[1]+'.json')).write_text(json.dumps(results,indent=2)+'\n');print(name,step,r.returncode,flush=True)
  if r.returncode:
   print((directory/(step+'.log')).read_text()[-4500:],flush=True);break
