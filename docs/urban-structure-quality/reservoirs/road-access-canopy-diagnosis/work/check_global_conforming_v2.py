from pathlib import Path
import subprocess,concurrent.futures,json
b=Path('work/urban-structure/p5/full-city-review');out=b/'global-conforming-v2-native'
def run(name):
 profile=name.split('-')[-1]
 cmd=['work/venv/bin/python','scripts/check_canopy_exports.py','--directory',str(out),'--name',name,'--terrain',str(b/'precision-decoded'/('terrain-'+profile+'.npz')),'--city-source','blender/build_city.py']
 with (out/(name+'-audit.log')).open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 return dict(name=name,exitCode=r.returncode,command=cmd)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 records=list(pool.map(run,['nearby-detail','nearby-smooth','all-detail','all-smooth']))
(out/'audit-results.json').write_text(json.dumps(records,indent=2)+'\n');print(records,flush=True)

raise SystemExit(0 if all(r["exitCode"] == 0 for r in records) else 1)
