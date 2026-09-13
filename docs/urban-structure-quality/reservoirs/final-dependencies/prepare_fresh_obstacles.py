from pathlib import Path
import json,sys,shutil,hashlib
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from prepare_ground_roads import capture_context,load
out=root/'work/p5/final-integration';report=json.loads((out/'landmark-context-report.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in report['inputHashes'].items():assert sha(root/p)==h,p
assert sha(out/'landmark-context.glb')==report['modelSha256']
capture_context(load('public/data/geography.json'),load('data/minzu-plan.json'),load('data/viaduct-plan.json'),context_model='work/p5/final-integration/landmark-context.glb')
shutil.copy2(root/'data/ground-roads-context.json',out/'fresh-landmark-obstacles.json')
print('Fresh obstacles captured from current production landmarks',flush=True)
