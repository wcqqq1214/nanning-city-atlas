"""Audit runtime assets in full-city and scoped modes, without skipping geometry gates.

This standalone entry point can diagnose exports even when validate_assets.py
is blocked by an upstream source-plan error. It does not replace source checks.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from asset_budgets import MODEL_BYTE_LIMITS
from forest_canopy import REGIONS as FOREST_REGIONS
from validate_railways import validate_railways
from validate_minzu import validate_minzu
from validate_bridges import validate_bridges, SPECS as RIVER_BRIDGE_SPECS
from validate_ground_roads import validate_ground_roads
from validate_elevated_roads import validate_elevated_roads
from validate_road_solids import validate_road_solids
from validate_zhuxi import validate_zhuxi

from validate_malls import validate_malls
from validate_cultural_landmarks import validate as validate_cultural
from validate_terrain import validate as validate_terrain

def validate_runtime_assets(site_access_plan=None):
    places = json.loads((ROOT/'public/data/landmarks.json').read_text())
    overview = json.loads((ROOT/'public/data/overview.json').read_text())
    scoped = bool(overview.get('urbanScope'))
    if scoped:
        from check_urban_scope_exports import validate as validate_urban_scope
        validate_urban_scope()
    def inspect_model(filename, budget):
        raw=(ROOT/'public/models'/filename).read_bytes()
        magic,version,length=struct.unpack_from('<III',raw)
        assert magic==0x46546C67 and version==2 and length==len(raw)
        json_len,json_kind=struct.unpack_from('<II',raw,12)
        assert json_kind==0x4E4F534A
        model=json.loads(raw[20:20+json_len])
        assert 'KHR_draco_mesh_compression' in model['extensionsRequired']
        names={node.get('name') for node in model['nodes']}
        assert {'Buildings','Terrain','Water','Roads','Vegetation','Bridges','Plinth','Railways'} <= names
        assert all('Landmark_'+p['id'] in names for p in places if p['modelled'])
        vegetation = next(node for node in model['nodes'] if node.get('name')=='Vegetation')
        descendants = set()
        def collect_children(node):
            for index in node.get('children',[]):
                descendants.add(index)
                collect_children(model['nodes'][index])
        collect_children(vegetation)
        for region in FOREST_REGIONS:
            for suffix in ['canopy','crowns']:
                index = next(i for i,node in enumerate(model['nodes']) if node.get('name')==f'Vegetation_{region["id"]}_{suffix}')
                assert index in descendants, 'Forest mesh is disconnected from the vegetation layer'
                if not scoped:
                    assert model['nodes'][index].get('children'), 'Forest lost its spatial batches'
        nanhu_index = next(i for i,node in enumerate(model['nodes']) if node.get('name')=='Vegetation_nanhu')
        assert nanhu_index in descendants, 'Nanhu trees ignore the vegetation switch'
        assert len(raw) < budget, f'{filename} exceeds loading budget'
        counts={}
        for mesh in model['meshes']:
            counts[mesh['name']]=sum(model['accessors'][p['indices']]['count']//3 for p in mesh['primitives'])
            if mesh['name'] == 'Landmark_sports-center':
                track = next(p for p in mesh['primitives']
                             if model['materials'][p['material']]['name'] == 'Sports terracotta track')
                floor = model['accessors'][track['attributes']['POSITION']]['min'][1]
                marker = next(p for p in places if p['id'] == 'sports-center')['position'][1]
                assert marker < floor, 'Stadium ground anchor is above the running track'
        return len(raw),counts
    # Fine landmarks are identical in both qualities. Allow their shared geometry
    # within bounded file sizes, while requiring substantial terrain/tree savings.
    # The 60 m terrain and newly split ground streets add 4.3 / 1.6 MB.
    # Keep the detailed model below a 25 MiB asset budget.
    full_bytes,full=inspect_model('nanning-city.glb',MODEL_BYTE_LIMITS['detail'])
    mobile_bytes,mobile=inspect_model('nanning-city-mobile.glb',MODEL_BYTE_LIMITS['smooth'])
    assert 30_000 < full['Landmark_sports-center'] < 55_000, 'Detailed sports venue geometry missing or over budget'
    assert 15_000 < full['Landmark_tingzi'] < 30_000, 'Detailed Tingzi geometry missing or over budget'
    assert 15_000 < full['Landmark_bridge'] < 40_000, 'Detailed bridge geometry missing or over budget'
    assert 25_000 < full['Landmark_changyou'] < 45_000, 'Changyou detailed roof and colonnade missing or over budget'
    assert 15_000 < full['Landmark_nanhu'] < 22_000, 'Nanhu bridge and garden geometry missing or over budget'
    assert 6_000 < full['Landmark_nanning-station'] < 20_000, 'Nanning station geometry missing or over budget'
    assert 15_000 < full['Landmark_east-station'] < 45_000, 'East station geometry missing or over budget'
    assert 17_000 < full['Landmark_zhenning'] < 21_000, 'Detailed Zhenning fort missing or over budget'
    assert 45_000 < full['Landmark_qingxiang-viaduct'] < 60_000, 'Full-route structure missing or over budget'
    assert 0 < mobile['QingxiangViaduct_Details'] < full['QingxiangViaduct_Details'] < 20_000
    # Optimizing the full-detail trees also narrows the gap between profiles. Use
    # independent absolute budgets so improving detail cannot fail a ratio check.
    # The complete Qingxiang road adds 0.2 MB / 45k triangles to the mobile cap.
    assert sum(v for k,v in full.items() if not k.startswith(('Railways','Railway_Details','RiverBridge_Details_','GroundRoads_','ElevatedRoads_')) and k not in {'Landmark_'+identity for identity in RIVER_BRIDGE_SPECS}) < 1_650_000
    # The complete fort and Minzu road structure are shared across both profiles.
    assert sum(v for k,v in mobile.items() if not k.startswith(('Railways','Railway_Details','RiverBridge_Details_','GroundRoads_','ElevatedRoads_')) and k not in {'Landmark_'+identity for identity in RIVER_BRIDGE_SPECS}) < 1_000_000
    assert sum(v for k,v in full.items() if k.startswith(('Railways','Railway_Details'))) < 650_000
    assert sum(v for k,v in mobile.items() if k.startswith(('Railways','Railway_Details'))) < 500_000
    assert mobile_bytes < full_bytes and sum(mobile.values()) < sum(full.values())
    overview = json.loads((ROOT/'public/data/overview.json').read_text())
    for counts, profile, tree_count, triangles_per_tree in [
        (full,'detail',overview['stats']['trees'],30),(mobile,'smooth',overview['mobileTrees'],8)]:
        singles = sum(c for name,c in counts.items() if name.startswith('Vegetation_') and name.split('_')[1].lstrip('-').isdigit())
        assert singles == tree_count*triangles_per_tree, 'City trees lost their bounded shared geometry'
        for region in FOREST_REGIONS:
            surface = sum(c for name,c in counts.items() if name.startswith(f'Vegetation_{region["id"]}_canopy_'))
            if not scoped:
                assert surface == len(region[profile]['triangles']), 'Exported forest coverage is incomplete'
            crowns = sum(c for name,c in counts.items() if name.startswith(f'Vegetation_{region["id"]}_crowns_'))
            selected = region.get('smoothCrownClusters', region['crownClusters'][::2]) if profile=='smooth' else region['crownClusters']
            if not scoped:
                assert crowns == len(selected)*20
            else:
                assert crowns % 20 == 0 and crowns <= len(selected)*20, 'Scope split a tree crown'
        assert sum(c for name,c in counts.items() if name.startswith('Vegetation_nanhu')) == 83*30+36*92
    for name, count in full.items():
        # Resolved Minzu joins follow each profile's ground mesh. validate_minzu()
        # independently checks the shared native structure and both resolved meshes.
        if not name.startswith(('Terrain','Vegetation','Railway_Details','MinzuAvenue_','RiverBridge_Details_','GroundRoads','ElevatedRoads','ZhuxiInterchange')) and name != 'QingxiangViaduct_Details':
            if not (scoped and name == 'Plinth'):
                assert mobile[name]==count, f'Mobile lost geometry in {name}'
    print(f'GLB: detail {full_bytes:,} bytes / {sum(full.values()):,} triangles; smooth {mobile_bytes:,} bytes / {sum(mobile.values()):,} triangles. Buildings, roads, water and landmarks preserved.')
    # Cropped road totals still obey the original absolute triangle budgets.
    assert sum(v for k,v in full.items() if k.startswith('GroundRoads_')) < 530_000
    assert sum(v for k,v in mobile.items() if k.startswith('GroundRoads_')) < 350_000
    assert sum(v for k,v in full.items() if k.startswith('ElevatedRoads_')) < 500_000
    validate_geometry(site_access_plan)


def validate_geometry(site_access_plan=None):
    # Independent audits should all run, even when one source plan is stale.
    # Fail the suite at the end; never turn a diagnostic failure into PASS.
    checks = [(name, globals()[name]) for name in (
        'validate_railways', 'validate_minzu', 'validate_bridges',
        'validate_ground_roads', 'validate_elevated_roads', 'validate_road_solids',
        'validate_zhuxi', 'validate_malls', 'validate_cultural', 'validate_terrain')]
    failures = []
    for name, check in checks:
        try:
            if name == 'validate_ground_roads':
                check(site_access_plan=site_access_plan)
            else:
                check()
        except (AssertionError, ValueError) as error:
            failures.append(f'{name}: {error}')
            print(f'FAIL: {name}: {error}', flush=True)
    assert not failures, 'Runtime geometry checks failed:\n'+'\n'.join(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-access-plan', type=Path)
    args = parser.parse_args()
    validate_runtime_assets(args.site_access_plan)
