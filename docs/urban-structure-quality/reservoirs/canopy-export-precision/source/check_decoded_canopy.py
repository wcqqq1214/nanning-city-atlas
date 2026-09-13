from pathlib import Path
import subprocess,sys,json,concurrent.futures
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review/conforming-decoded';out=b/'audit';out.mkdir(exist_ok=True)
def run(pair):
 region,profile=pair;name=region+'-'+profile;cmd=[sys.executable,'scripts/check_canopy_clearance.py','--canopy',str(b/(name+'.npz')),'--terrain',str(b/('terrain-'+profile+'.npz')),'--coverage-tolerance-meters','.002','--output',str(out/(name+'.json'))]
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 return {'name':name,'exitCode':r.returncode,'command':cmd}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
 records=[]
 for record in executor.map(run,[(r,p) for r in ['nearby','all'] for p in ['detail','smooth']]):
  records.append(record);(out/'result.json').write_text(json.dumps(records,indent=2)+'\n');print(record['name'],record['exitCode'],flush=True)
