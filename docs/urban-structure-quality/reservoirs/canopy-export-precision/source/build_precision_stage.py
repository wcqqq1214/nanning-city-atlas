from pathlib import Path
import shutil,subprocess,json,hashlib,time
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review';stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging'
history=b/'precision-before';history.mkdir(exist_ok=False)
files=['public/models/nanning-city.glb','public/models/nanning-city-mobile.glb','blender/nanning-city.blend','public/data/overview.json','data/forest-plan.json','blender/gltf_export.py','data/elevated-roads-heights.json.gz']
record={'stage':str(stage),'before':{}}
for name in files:
 source=stage/name;target=history/name;target.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['cp','-c',str(source),str(target)],check=True)
 record['before'][name]=hashlib.sha256(source.read_bytes()).hexdigest()
shutil.copy2(root/'blender/gltf_export.py',stage/'blender/gltf_export.py')
record['newExportPolicySha256']=hashlib.sha256((stage/'blender/gltf_export.py').read_bytes()).hexdigest()
out=stage/'work/p5/precision-integration';out.mkdir(exist_ok=False)
cmd=['/opt/homebrew/bin/blender','-b','--python-exit-code','1','--python','blender/build_city.py','--','--site-access-plan','work/p5/conforming-integration/access-plan.json','--building-support-plan','work/p5/conforming-integration/final-support.json']
record['command']=cmd;(out/'setup.json').write_text(json.dumps(record,indent=2)+'\n');start=time.time()
with (out/'full-city.log').open('w') as f:r=subprocess.run(cmd,cwd=stage,stdout=f,stderr=subprocess.STDOUT)
record.update(exitCode=r.returncode,seconds=time.time()-start)
record['after']={name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in files}
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record,flush=True)
raise SystemExit(r.returncode)
