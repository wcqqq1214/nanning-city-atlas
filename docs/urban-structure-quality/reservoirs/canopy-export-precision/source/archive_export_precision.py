from pathlib import Path
import hashlib,json,shutil
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review';stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging'
out=root/'docs/urban-structure-quality/reservoirs/canopy-export-precision';out.mkdir(parents=True,exist_ok=False);files=[];external=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(p,target):
 q=out/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);files.append({'source':str(p.relative_to(root)),'path':target,'sha256':sha(q),'bytes':q.stat().st_size})
def link(p):external.append({'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size})
for folder in ['conforming-browser','conforming-decoded/audit','canopy-lossless-export']:
 for p in (b/folder).iterdir():
  if p.suffix in ['.json','.log','.png','.py']:copy(p,folder+'/'+p.name)
  elif p.suffix in ['.npz','.glb']:link(p)
for p in (b/'conforming-decoded').glob('*.npz'):link(p)
copy(b/'conforming-decoded/manifest.json','conforming-decoded/manifest.json')
for name in ['pipeline-report.json','validate-assets.log']:
 p=stage/'work/p5/conforming-integration'/name
 if p.exists():copy(p,'complete-conforming/'+name)
for p in (b/'precision-before').rglob('*'):
 if p.is_file():link(p)
for name in ['detail-20cm.json','detail-20cm-audit.json','conforming-codec-audit-result.json','conforming-detail-audit.json','conforming-smooth-audit.json']:
 copy(b/'budget-reduction'/name,'budget/'+name)
for p in (b/'budget-reduction/conforming-codec/public/models').glob('*'):
 if p.suffix=='.json':copy(p,'budget/'+p.name)
 else:link(p)
for name in ['detail-20cm.npz','smooth-20cm.npz']:
 p=b/'budget-reduction'/name
 if p.exists():link(p)
for p in (b/'longmen-axis').rglob('*'):
 if not p.is_file():continue
 if p.suffix in ['.json','.py','.png','.log']:copy(p,'longmen-axis/'+str(p.relative_to(b/'longmen-axis')))
 elif p.suffix in ['.npz','.glb','.blend']:link(p)
for name in ['scripts/check_canopy_exports.py','scripts/capture_canopy_surface.py','blender/gltf_export.py','scripts/prepare_reservoir_terrain.py','scripts/test_reservoir_terrain.py']:
 copy(root/name,'source/'+name)
for name in ['check_lossless_canopy.py','extract_conforming_canopy.py','check_decoded_canopy.py','build_precision_stage.py','archive_export_precision.py','precision-reservoir-tests.log']:
 copy(b/name,'source/'+name)
record={'status':'historical complete candidate and precision diagnosis; new full precision rebuild is separate and pending','files':files,'externalFiles':external,'scopeNotes':['Lossless canopy export alone passes exact geometry and clearance but fails terrain boundary coverage.','Old complete GLBs are preserved under precision-before; the active stage is rebuilding.','Longmen axis crest remains a local candidate; exact outside geometry and overall visual acceptance have not passed.']}
(out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(len(files),'copied',len(external),'external')
