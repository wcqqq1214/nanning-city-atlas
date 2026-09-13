"""Compare shared visibility against executable pre-refactor city predicates.

Only the predicate AST is executed, never the Blender scene builder. The pinned
pre-P4 commit supplies the original exclusions; P4's polygon reservations are
checked separately. This is not a fresh road/railway dependency validation.
"""
import ast
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
import city_visibility as visibility
from landmark_sites import reservation_rings


def reference(geo, catalog, legacy):
    source = subprocess.check_output(['git', 'show', '73edbb7:blender/build_city.py'], cwd=ROOT, text=True)
    tree = ast.parse(source)
    predicate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'inside_landmark')
    loop = next(n for n in tree.body if isinstance(n, ast.For) and
                ast.unparse(n.target) == '(building_index, b)')
    body = []
    for statement in loop.body:
        if isinstance(statement, ast.Assign) and ast.unparse(statement.targets[0]) == 'z': break
        body.append(copy.deepcopy(statement))
    class Reject(ast.NodeTransformer):
        def visit_Continue(self, node): return ast.copy_location(ast.Return(ast.Constant(False)), node)
    function = ast.parse('def old_visible(b, building_index):\n    pass').body[0]
    function.body = [Reject().visit(n) for n in body]+[ast.Return(ast.Constant(True))]
    cx, cy = geo['center']
    def xy(lon, lat): return ((lon-cx)*1113.2*math.cos(math.radians(cy)), (lat-cy)*1113.2)
    places = {p['id']: p for p in catalog}
    origins = {i: xy(places[i]['lon'], places[i]['lat']) for i in visibility.CALIBRATION}
    clear = [(*xy(p['lon'], p['lat']), *p['clearExtent']) for p in catalog
             if 'clearExtent' in p and p['id'] not in visibility.CALIBRATION]
    if legacy:
        clear += [(*origins[i], *s['legacyClearExtentScene']) for i, s in visibility.CALIBRATION.items()
                  if s.get('legacyClearExtentScene')]
    env = {n: getattr(visibility, n) for n in ['inside_site', 'inside_mall', 'inside_tingzi',
                                            'inside_changyou', 'inside_station', 'intersects_mall']}
    for prefix, identity in [('SPORTS', 'sports-center'), ('TINGZI', 'tingzi'), ('CHANGYOU', 'changyou')]:
        env[prefix+'_X'], env[prefix+'_Y'] = xy(places[identity]['lon'], places[identity]['lat'])
    env.update(CLEAR_AREAS=clear, RAILWAY_BUILDINGS={-1},
               MALL_ORIGINS={i: xy(*s['center']) for i, s in visibility.MALL_SITES.items()},
               STATION_SITES={i: (*xy(*s['center']), 0) for i, s in visibility.STATIONS.items()})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[predicate, function], type_ignores=[])),
                 '<pinned city predicates>', 'exec'), env)
    original = env['inside_landmark']
    if not legacy:
        env['inside_landmark'] = lambda x, y: original(x, y) or any(
            abs(x-a)<3 and abs(y-b)<3 and visibility.inside_calibrated_site(i, x-a, y-b)
            for i, (a, b) in origins.items())
    return env


class VisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geo = json.loads((ROOT/'public/data/geography.json').read_text())
        cls.catalog = json.loads((ROOT/'data/landmarks.json').read_text())
        cls.shared = visibility.CityVisibility(cls.geo, cls.catalog)

    def test_all_current_buildings_and_railway_exclusion(self):
        for legacy in [False, True]:
            old = reference(self.geo, self.catalog, legacy)
            for b in self.geo['buildings']:
                self.assertEqual(self.shared.building_visible(b, legacy=legacy), old['old_visible'](b, 0), b['id'])
                self.assertFalse(self.shared.building_visible(b, railway_hidden=True, legacy=legacy))

    def test_boundaries_and_nearby_offsets(self):
        points = []
        for x, y, w, d in self.shared.legacy_clear_areas:
            points += [(x+u*w/2, y+v*d/2) for u in [-1, 0, 1] for v in [-1, 0, 1]]
        for identity, (x, y) in self.shared.calibration_origins.items():
            points += [(x+u, y+v) for ring in reservation_rings(identity) for u, v in ring]
        for legacy in [False, True]:
            old = reference(self.geo, self.catalog, legacy)
            for x, y in points:
                for dx, dy in [(0, 0), (1e-7, 0), (-1e-7, 0), (0, 1e-7), (0, -1e-7)]:
                    self.assertEqual(self.shared.inside_landmark(x+dx, y+dy, legacy),
                                     old['inside_landmark'](x+dx, y+dy), (x, y, dx, dy, legacy))

    def test_named_replacements_and_invalid_rings(self):
        for name in ['龙象塔', '华润大厦A座', '地王国际商会中心']:
            self.assertFalse(self.shared.building_visible({'name': name, 'rings': []}))
        self.assertFalse(self.shared.building_visible({'rings': [[[0, 0], [1, 0], [0, 0]]]}))


if __name__ == '__main__': unittest.main()
