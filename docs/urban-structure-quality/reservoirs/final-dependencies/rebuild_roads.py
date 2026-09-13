from pathlib import Path
import subprocess,time,json,sys
root=Path.cwd();out=root/'work/p5/final-integration';py=sys.executable;bl='/opt/homebrew/bin/blender'
commands=[('landmark-obstacles',[py,'work/p5/final-integration/prepare_fresh_obstacles.py']),
('ground-plan',[py,'scripts/prepare_ground_roads.py','--capture','--context-model','work/p5/final-integration/base-context/detail.glb','--obstacles-context','work/p5/final-integration/fresh-landmark-obstacles.json']),
('ground-context',[bl,'-b','--python-exit-code','1','--python','blender/build_city.py','--','--terrain-context','--context-ground']),
('elevated-plan',[py,'scripts/prepare_elevated_roads.py','--context-directory','work/terrain-resample/context']),
('road-inputs',[bl,'-b','--python-exit-code','1','--python','blender/build_city.py','--','--capture-road-inputs','--building-support-plan','work/p5/final-integration/base-support.json'])]
for profile in ['detail','smooth']:
 for name in ['prepare','finish']:commands.append((name+'-'+profile,[py,'scripts/'+name+'_road_solids.py',profile]))
records=[]
for name,command in commands:
 print('Starting',name,flush=True);start=time.time()
 with (out/(name+'.log')).open('w') as log:run=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 records.append({'step':name,'command':command,'exitCode':run.returncode,'seconds':round(time.time()-start,2)})
 (out/'road-rebuild-report.json').write_text(json.dumps(records,indent=2)+'\n');print('Finished',name,run.returncode,flush=True)
 if run.returncode:raise SystemExit(run.returncode)
