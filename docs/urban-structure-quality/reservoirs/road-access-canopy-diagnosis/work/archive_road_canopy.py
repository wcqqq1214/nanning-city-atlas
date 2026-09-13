from pathlib import Path
import json,hashlib,shutil
root=Path.cwd();b=root/'work/urban-structure/p5/full-city-review';out=root/'docs/urban-structure-quality/reservoirs/road-access-canopy-diagnosis';out.mkdir(parents=True,exist_ok=False);files=[];external=[];seen=set()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(p,target):
 q=out/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);files.append({'source':str(p.relative_to(root)),'path':target,'sha256':sha(q),'bytes':q.stat().st_size})
def link(p):
 name=str(p.relative_to(root))
 if name in seen:return
 seen.add(name);external.append({'path':name,'sha256':sha(p),'bytes':p.stat().st_size})
for folder in ['global-uncompressed-native','global-normal-precision-native','global-conforming-v2-native','global-conforming-v3-native','global-conforming-v3-preview','global-conforming-v3-browser']:
 for p in sorted((b/folder).rglob('*')):
  if not p.is_file():continue
  if p.suffix in ['.json','.log','.png']:copy(p,folder+'/'+str(p.relative_to(b/folder)))
  elif p.suffix in ['.glb','.npz']:link(p)
copy(b/'global-conforming-native/exact-export-diagnostic.json','first-candidate/exact-export-diagnostic.json')
for p in sorted(b.glob('road-access*')):
 if p.is_file():copy(p,'roads/'+p.name)
for p in sorted(b.glob('test_*.final.log')):copy(p,'tests/'+p.name)
names=['diagnose_global_canopy_export.py','global-canopy-exact-diagnostic.log','check_uncompressed_canopy.py','canopy_uncompressed_policy.py','global-uncompressed-export.log','uncompressed-correspondence.log','canopy_normal_precision_policy.py','global-normal-precision-export.log','diagnose_normal_precision_canopy.py','normal-precision-diagnostic.log','prepare_global_conforming_v2.py','global-conforming-v2-prepare.log','global-conforming-v2-export.log','check_global_conforming_v2.py','global-conforming-v2-audit.log','diagnose_global_canopy_v2.py','global-conforming-v2-diagnostic.log','prepare_global_conforming_v3.py','global-conforming-v3-prepare.log','global-conforming-v3-export.log','check_global_conforming_v3.py','global-conforming-v3-audit.log','graft_canopy_preview_v3.py','global_conforming_v3_browser.mjs','global-conforming-v3-browser.log','verify_canopy_export_hook_scope.py','canopy-export-hook-scope.json','canopy-export-hook-scope.log','canopy-export-fix-tests.log','canopy-export-fix-tests-v3.log','canopy-largest-rise-join.json','canopy-largest-rise-join.log','locate_canopy_rise_join.py','record_formal_invariants.py','road-canopy-formal-assets.json','road-canopy-final-tests.json','canopy-exporter-environment.json','archive_road_canopy.py']
for name in names:copy(b/name,'work/'+name)
for version in ['v2','v3']:
 link(b/('forest-candidate-global-conforming-'+version+'.json'));copy(b/('forest-candidate-global-conforming-'+version+'.report.json'),'plans/global-conforming-'+version+'.report.json')
for name in ['scripts/road_access_validation.py','scripts/test_road_access_validation.py','scripts/validate_ground_roads.py','scripts/validate_assets.py','scripts/conform_canopy_edges.py','scripts/test_conform_canopy_edges.py','scripts/test_local_canopy.py','scripts/test_site_access_plan.py','scripts/check_canopy_exports.py','scripts/capture_canopy_surface.py','blender/gltf_export.py','docs/URBAN_STRUCTURE_PLAN.md','docs/URBAN_STRUCTURE_CANOPY.md','docs/URBAN_STRUCTURE_QUALITY.md']:copy(root/name,'source/'+name)
stage=root/'work/urban-structure/p5/reservoirs/integration/budget/canopy-conforming-staging';batch=stage/'work/p5/precision-rebuild';copy(batch/'validate-bridges-independent.log','roads/validate-bridges-independent.log');link(batch/'access-plan.json')
for name in ['public/models/nanning-city.glb','public/models/nanning-city-mobile.glb','public/data/overview.json','public/data/geography.json','public/data/terrain.json','data/forest-plan.json']:link(b/'precision-complete-models'/name)
record={'status':'full roads and 13 bridges passed; four global canopy v3 exports passed; 32 review-only browser captures; P5 incomplete','files':files,'externalFiles':external,'limitations':['The full city remains the frozen precision-rebuild candidate; global canopy v3 and updated exporter have not been source-bound into a new full pipeline.','The browser graft is review-only; unchanged geometry, hierarchy and materials were checked, but summary counts are not final generated metadata.','Budgets remain above 26 MB/18 MB and non-infrastructure face caps; no reduction trial was activated.','Qingxiu compressed canopy, 317 sites, four template integration, mountain/waterfront rollout and final interaction/performance acceptance remain.','Formal P4 assets remain unchanged.']}
(out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(len(files),'copied files;',len(external),'external references')
