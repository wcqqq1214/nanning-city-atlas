from pathlib import Path
import json,hashlib,shutil,subprocess
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review';stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging';out=root/'docs/urban-structure-quality/reservoirs/precision-complete';out.mkdir(parents=True,exist_ok=False);files=[];external=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(p,target):
 q=out/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);files.append({'source':str(p.relative_to(root)),'path':target,'sha256':sha(q),'bytes':q.stat().st_size})
def link(p):external.append({'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size})
for folder in ['precision-browser','precision-decoded','global-conforming-native','global-conforming-browser','global-conforming-preview','longmen-boundary']:
 for p in (b/folder).rglob('*'):
  if not p.is_file():continue
  if p.suffix in ['.json','.png','.log','.py']:copy(p,folder+'/'+str(p.relative_to(b/folder)))
  elif p.suffix in ['.glb','.npz','.blend']:link(p)
for name in ['pipeline-report.json','pipeline-command.json','full-city-result.json','final-support-audit.json','access-export-audit.json','validate-ground-roads.log']:
 p=stage/'work/p5/precision-rebuild'/name
 if p.exists():copy(p,'pipeline/'+name)
for name in ['precision-detail-audit.json','precision-smooth-audit.json','precision-codec-audit-result.json','precision-smooth-50cm.json','precision-smooth-50cm-audit.json','infrastructure-audit.json','composed-codec-tests.log','non-infrastructure-inventory.json','landmark-planar-probe/report.json']:
 p=b/'budget-reduction'/name
 if p.exists():copy(p,'budget/'+name)
for folder in ['precision-codec','infrastructure-codec']:
 for p in (b/'budget-reduction'/folder).rglob('*'):
  if not p.is_file():continue
  if p.suffix=='.json':copy(p,'budget/'+folder+'/'+str(p.relative_to(b/'budget-reduction'/folder)))
  elif p.suffix=='.glb':link(p)
for name in ['forest-candidate-global-conforming.json','forest-candidate-global-conforming.report.json','global-conforming.log','global-conforming-fixed.log','global-conforming-final.log','global-conforming-tests-final.log','global-local-canopy-tests.log','longmen-boundary-tests.log','prepare_global_conforming.py','graft_canopy_preview.py','archive_precision_complete.py']:
 p=b/name
 if p.suffix=='.json' and not name.endswith('.report.json') and name.startswith('forest-candidate'):link(p)
 else:copy(p,'source/'+name)
for name in ['scripts/conform_canopy_edges.py','scripts/test_conform_canopy_edges.py','scripts/prepare_reservoir_terrain.py','scripts/test_reservoir_terrain.py','scripts/check_flat_surfaces.py','scripts/test_flat_surfaces.py','scripts/check_canopy_exports.py','scripts/capture_canopy_surface.py','blender/gltf_export.py']:copy(root/name,'source/'+name)
freeze=b/'precision-complete-models';freeze.mkdir(exist_ok=False)
for name in ['public/models/nanning-city.glb','public/models/nanning-city-mobile.glb','public/data/overview.json','public/data/landmarks.json','public/data/geography.json','public/data/terrain.json','blender/nanning-city.blend','blender/gltf_export.py','data/forest-plan.json']:
 source=stage/name;target=freeze/name;target.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['cp','-c',str(source),str(target)],check=True);link(target)
record={'status':'precision complete candidate checked; global conforming is review-only with three failed export groups; P5 incomplete','files':files,'externalFiles':external,'limitations':['Full road validator failed the expected-footprint test; bridge validator in that chained command did not run.','Global conforming preview improves the inspected slits but nearby-smooth and both all-region exports fail strict correspondence.','50 cm terrain reduction is an independently checked native trial; sampler, dependents, visuals and final budget remain pending.']}
(out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(len(files),'files;',len(external),'external references')
