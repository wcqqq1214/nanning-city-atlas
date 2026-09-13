"""Reproduce canopy clearance failures with the production validator sampler."""
import ast
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

root = Path('work/urban-structure/p5/reservoirs/integration/budget/summary-fix-staging').resolve()
sys.path.insert(0, str(root/'blender'))
from forest_canopy import REGIONS, build_canopy, terrain_surface, coarse_terrain_surface
from mountain_terrain import canopy_factor
from station_landmarks import ground_blend as station_ground_blend
from railways import TerrainCut

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--forest', type=Path)
parser.add_argument('--output', type=Path, default=Path(__file__).with_name('canopy-failures.json'))
args = parser.parse_args()
if args.forest:
    REGIONS = json.loads(args.forest.read_text())['regions']

g = json.loads((root/'public/data/geography.json').read_text())
t = json.loads((root/'public/data/terrain.json').read_text())
catalog = json.loads((root/'data/landmarks.json').read_text())
station_sites = {}
for place in catalog:
    if place['id'] in ['nanning-station', 'east-station']:
        station_sites[place['id']] = ((place['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1])),
                                    (place['lat']-g['center'][1])*1113.2, None)
railway_cuts = TerrainCut(json.loads((root/'public/data/overview.json').read_text())['railways']['terrainCuts'])
tree = ast.parse((root/'scripts/validate_assets.py').read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ['terrain_ground', 'raw_ground']]
assert len(functions) == 2
exec(compile(ast.Module(body=functions, type_ignores=[]), str(root/'scripts/validate_assets.py'), 'exec'))
report = {'scope':'production sampler reproduction; complete mesh overlap audit remains separate', 'profiles':{}}
output = args.output

class Probe:
    def __init__(self, mobile):
        self.mobile = mobile; self.count = 0; self.failed = []
    def face(self, vertices, color, normals=None):
        for weights in [(1/3,1/3,1/3),(.5,.5,0),(.5,0,.5),(0,.5,.5)]:
            x,y,z = [sum(v[k]*w for v,w in zip(vertices,weights)) for k in range(3)]
            floor = terrain_surface(x,y,raw_ground,g['bounds'],t['cols'],t['rows'],self.mobile)
            if z-floor <= .095*canopy_factor(x,y):
                coarse = coarse_terrain_surface(x,y,raw_ground,g['bounds'],t['cols'],t['rows'],self.mobile)
                self.failed.append({'face':self.count,'vertices':vertices,'point':[x,y,z],
                                    'clearanceMeters':(z-floor)*100,'floorMeters':floor*100,
                                    'finalMinusCoarseMeters':(floor-coarse)*100})
        self.count += 1

for region in REGIONS:
    if region['id'] == 'qingxiu':continue
    for profile in ['detail','smooth']:
        probe = Probe(profile=='smooth')
        build_canopy(probe,region,raw_ground,g['bounds'],t['cols'],t['rows'],probe.mobile)
        report['profiles'][region['id']+'/'+profile]={'faces':probe.count,'failedSamples':len(probe.failed),'failures':probe.failed}
        report['inputs']={str(root/p):hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['data/forest-plan.json','blender/forest_canopy.py','scripts/validate_assets.py']}
        if args.forest:report['inputs'][str(args.forest.resolve())]=hashlib.sha256(args.forest.read_bytes()).hexdigest()
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(region['id'],profile,probe.count,'faces',len(probe.failed),'failed samples',flush=True)
