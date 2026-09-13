"""Optional, source-bound reservoir activation for city and preparation tools."""
import hashlib
import json
from pathlib import Path

from reservoir_terrain import ReservoirTerrain
from reservoir_group import ReservoirGroup
from water_control_runtime import WaterControls

ROOT=Path(__file__).resolve().parents[1]
PLAN_PATH=ROOT/'data/reservoir-terrain-plan.json'
REGISTRY_PATH=ROOT/'data/reservoir-terrain-registry.json'
MATERIAL_KEYS=['reservoir_ground','dam_slope','dam_crest']


def load(path=PLAN_PATH,root=ROOT):
    if not path.exists():return None
    root=root.resolve();payload=json.loads(path.read_text())
    bindings=payload.get('runtimeInputs',{})
    required={'public/data/geography.json','public/data/terrain.json'}
    if not required<=set(bindings):raise ValueError('Reprepare reservoir with runtime source bindings')
    for name,digest in bindings.items():
        file=(root/name).resolve();file.relative_to(root)
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('Reprepare reservoir after changing '+name)
    for key in ['geography','terrain','source']:
        item=payload['inputs'][key];file=Path(item['path']).resolve()
        name=str(file.relative_to(root))
        if bindings.get(name)!=item['sha256']:raise ValueError('Reservoir input is not bound to this runtime root')
        if key in ['geography','terrain'] and name!='public/data/'+key+'.json':
            raise ValueError('Reservoir must use the active city '+key)
    dem=json.loads((root/'public/data/terrain.json').read_text())
    geo=json.loads((root/'public/data/geography.json').read_text())
    if payload['center']!=geo['center']:raise ValueError('Reservoir coordinate origin mismatch')
    if payload.get('restoredCityBoundarySides') or payload.get('source',{}).get('mesh',{}).get('restoreAtCityBoundary'):
        expected=[side for k,side in enumerate(['west','south','east','north'])
                  if payload['source']['mesh'].get('restoreAtCityBoundary') and abs(payload['bounds'][k]-geo['bounds'][k])<1e-9]
        if payload.get('restoredCityBoundarySides')!=expected:raise ValueError('Only actual city cuts may restore boundary heights')
    interfaces=payload.get('waterInterfaceAudit',{})
    if interfaces.get('schemaVersion')!=1:
        raise ValueError('Reprepare reservoir with a complete water interface audit')
    if interfaces.get('unresolvedWaterIndices') or any(n['requiresInterfaceResolution'] for n in interfaces['neighbors']):
        raise ValueError('Resolve affected neighboring water interfaces before reservoir activation')
    for name,limit in [('columnRange',dem['cols']),('rowRange',dem['rows'])]:
        values=payload[name]
        if len(values)!=2 or any(type(v) is not int or v%2 for v in values) or not 0<=values[0]<values[1]<limit:
            raise ValueError('Reservoir replacement must align with both terrain profiles')
    buildings={b['id']:b for b in geo['buildings']}
    ids=set()
    def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    for dam in payload['dams']:
        b=buildings.get(dam['id'])
        if dam['id'] in ids or b is None or b.get('use')!='dam' or b.get('sourceRef')!=dam['sourceRef'] or digest(b['rings'])!=dam['expectedFootprintSha256']:
            raise ValueError('Reservoir dam exclusion does not match its mapped source')
        ids.add(dam['id'])
    for lake in payload['waterBodies']:
        rings=geo['water'][lake['geographyWaterIndex']]
        if rings!=lake['rings'] or digest(rings)!=lake['expectedPolygonSha256']:
            raise ValueError('Reservoir water differs from active geography')
    return ReservoirTerrain(payload,dem)


def load_registry(path=REGISTRY_PATH,root=ROOT,legacy_path=None):
    """Load an explicit hash-bound registry, or the existing single-plan input."""
    path=Path(path);root=Path(root).resolve()
    legacy_path=Path(legacy_path) if legacy_path is not None else root/'data/reservoir-terrain-plan.json'
    if not path.exists():
        plan=load(legacy_path,root)
        return (ReservoirGroup([plan]),[str(legacy_path.resolve().relative_to(root))]) if plan is not None else (None,[])
    if legacy_path.exists():raise ValueError('Choose the reservoir registry or the legacy plan, not both')
    registry=json.loads(path.read_text())
    if registry.get('schemaVersion')!=1 or not isinstance(registry.get('plans'),list) or not registry['plans']:
        raise ValueError('Invalid reservoir registry')
    plans=[];paths=[str(path.resolve().relative_to(root))]
    for entry in registry['plans']:
        file=(root/entry['path']).resolve();name=str(file.relative_to(root))
        if name in paths:raise ValueError('Duplicate reservoir plan path')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Rebuild reservoir registry after changing '+name)
        plan=load(file,root)
        if plan.payload['id']!=entry['id']:raise ValueError('Reservoir registry ID differs from its plan')
        plans.append(plan);paths.append(name)
    group=ReservoirGroup(plans)
    group.controls=WaterControls(registry.get('structures',[]),group,root)
    return group,paths+group.controls.input_paths


PLAN,PLAN_INPUT_PATHS=load_registry()
PLANS=PLAN.plans if PLAN is not None else ()
CONTROLS=getattr(PLAN,'controls',None)
DAM_IDS=(PLAN.dam_ids | (CONTROLS.ids if CONTROLS is not None else frozenset())) if PLAN is not None else frozenset()


def input_paths():
    paths=['blender/reservoir_runtime.py','blender/reservoir_group.py','blender/reservoir_terrain.py','blender/reservoir_water.py',
           'blender/water_control_runtime.py','blender/water_control_structures.py']
    return list(dict.fromkeys(paths+PLAN_INPUT_PATHS+[name for p in PLANS for name in p.payload['runtimeInputs']]))


def contains(x,y):return PLAN is not None and PLAN.contains(x,y)
def replaces_cell(i,j):return PLAN is not None and PLAN.replaces_cell(i,j)
def dedicated_dam(building):return building.get('id') in DAM_IDS
def build_water_controls(env,parent):return [] if CONTROLS is None else CONTROLS.build(env,parent)
def water_level(x,y):return None if PLAN is None else PLAN.water_level(x,y)
def custom_water_contains(x,y):return PLAN is not None and PLAN.custom_water_contains(x,y)
def custom_water_triangles():return [] if PLAN is None else PLAN.custom_water_triangles()
def surface(x,y,ground,bounds,columns,rows,lightweight,coarse):
    return None if PLAN is None else PLAN.sample(x,y,ground,bounds,columns,rows,lightweight,coarse)
