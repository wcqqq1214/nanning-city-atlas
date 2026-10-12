"""Check courtyard holes and ground support without historical geography."""
import sys
import unittest
from pathlib import Path
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from prepare_urban_blocks import roof_triangles
from urban_blocks import build_massing


class BlockTests(unittest.TestCase):
    def test_hole_and_ground_support(self):
        shape = box(0, 0, 1, 1).difference(box(.3, .3, .7, .7))
        roof = roof_triangles(shape)
        self.assertLess(unary_union([Polygon(t) for t in roof]).symmetric_difference(shape).area, 1e-8)
        building = {'id': 'test-courtyard', 'height': 18, 'rings': [list(r.coords) for r in [shape.exterior, *shape.interiors]], 'roofTriangles': roof}
        class Capture:
            def __init__(self): self.faces = []
            def face(self, vertices, material): self.faces.append((vertices, material))
        capture = Capture()
        surface = lambda x, y: (.5+x*.1+y*.03, .52+x*.1+y*.03)
        result = build_massing(capture, building, surface, 'building')
        self.assertAlmostEqual(result['floor'], .662)
        self.assertAlmostEqual(result['top'], .842)
        for face, material in capture.faces:
            if material != 'roof':
                for x, y, z in face[:2]:
                    self.assertLess(z, surface(x, y)[0])
        # Hole walls exist and their roofs never cover the central void.
        self.assertGreater(len(capture.faces), len(roof)+4)


if __name__ == '__main__':
    unittest.main()
