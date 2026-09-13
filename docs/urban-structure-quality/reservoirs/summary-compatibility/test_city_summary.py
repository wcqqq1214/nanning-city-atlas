"""Exercise the actual city summary with legacy and compound block schemas."""
import ast
from pathlib import Path
import unittest


def scale_summary(blocks):
    source = Path(__file__).resolve().parents[1] / 'blender/build_city.py'
    tree = ast.parse(source.read_text())
    statement = next(node for node in tree.body if isinstance(node, ast.Assign)
                     and isinstance(node.targets[0], ast.Subscript)
                     and isinstance(node.targets[0].slice, ast.Constant)
                     and node.targets[0].slice.value == 'buildingScaleOverrides')
    env = {'GEO': {'urbanBlocks': blocks}, 'summary': {}}
    exec(compile(ast.Module(body=[statement], type_ignores=[]), str(source), 'exec'), env)
    return env['summary']['buildingScaleOverrides']


class CitySummaryTests(unittest.TestCase):
    def test_compound_metres_and_legacy_multiplier_can_coexist(self):
        blocks = [
            {'id': 'legacy', 'template': {'displayHeightScale': 1.2},
             'layoutSource': 'estimate', 'buildingIds': ['a']},
            {'id': 'compound', 'template': {'type': 'warehouse-loading-court',
                                          'warehouseHeightMeters': 18},
             'layoutSource': 'estimate', 'buildingIds': ['b', 'c']},
        ]
        self.assertEqual(scale_summary(blocks), [
            {'blockId': 'legacy', 'scale': 1.2, 'layoutSource': 'estimate', 'buildings': 1},
            {'blockId': 'compound', 'scale': 1.0, 'layoutSource': 'estimate', 'buildings': 2},
        ])

    def test_city_without_block_overrides(self):
        self.assertEqual(scale_summary([]), [])


if __name__ == '__main__':
    unittest.main()
