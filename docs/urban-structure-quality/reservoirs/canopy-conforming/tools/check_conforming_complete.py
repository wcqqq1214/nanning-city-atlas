import subprocess,concurrent.futures
from pathlib import Path
b=Path('work/urban-structure/p5/full-city-review');t=Path('work/urban-structure/p5/reservoirs/integration/budget/nanhu-staging/work/p5/nanhu-integration/access-runtime');out=b/'canopy-conforming-audit';out.mkdir(exist_ok=True)
def run(row):
 folder,name=row;profile=name.split('-')[-1]
 with (out/(name+'.log')).open('w') as f:
  r=subprocess.run(['work/venv/bin/python','scripts/check_canopy_clearance.py','--canopy',str(b/folder/(name+'.npz')),'--terrain',str(t/(profile+'.npz')),'--coverage-tolerance-meters','.002','--output',str(out/(name+'.json'))],stdout=f,stderr=subprocess.STDOUT)
 return name,r.returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:
 for r in e.map(run,[('canopy-conforming-native','nearby-detail'),('canopy-conforming-native','nearby-smooth'),('canopy-clean-native','all-detail'),('canopy-clean-native','all-smooth')]):print(r,flush=True)
