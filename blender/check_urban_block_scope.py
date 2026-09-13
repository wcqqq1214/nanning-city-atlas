"""Compare native building faces/materials outside the explicitly replaced houses.

blender -b --python-exit-code 1 --python blender/check_urban_block_scope.py
Reads both .blend files; does not save either one.
"""
import bpy
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
geo = json.loads((ROOT/'public/data/geography.json').read_text())
shapes = [b['rings'][0] for block in geo['urbanBlocks'] for b in block['removedBuildings']]
shapes += [b['rings'][0] for b in geo['buildings'] if b.get('blockId')]
regions = [(min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r), r) for r in shapes]


def replaced(x, y):
    for west, south, east, north, ring in regions:
        if x < west-1e-5 or x > east+1e-5 or y < south-1e-5 or y > north+1e-5:
            continue
        inside = False
        for (ax, ay), (bx, by) in zip(ring, ring[1:]):
            cross = (x-ax)*(by-ay)-(y-ay)*(bx-ax)
            if abs(cross) < 1e-5 and min(ax,bx)-1e-5 <= x <= max(ax,bx)+1e-5 and min(ay,by)-1e-5 <= y <= max(ay,by)+1e-5:
                return True
            if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
                inside = not inside
        if inside:
            return True
    return False


def capture(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    result = Counter()
    removed = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not obj.name.startswith('Buildings_'):
            continue
        for face in obj.data.polygons:
            points = [tuple(obj.matrix_world @ obj.data.vertices[i].co) for i in face.vertices]
            x, y = [sum(p[k] for p in points)/len(points) for k in [0, 1]]
            if replaced(x, y):
                removed += 1
                continue
            key = (obj.data.materials[face.material_index].name,
                   tuple(sorted(tuple(round(v, 7) for v in p) for p in points)))
            result[hashlib.sha256(repr(key).encode()).hexdigest()] += 1
    return result, removed


old, removed_old = capture(ROOT/'work/urban-structure/baseline-73edbb7/blender/nanning-city.blend')
new, removed_new = capture(ROOT/'blender/nanning-city.blend')
report = {'outsideFacesBefore': sum(old.values()), 'outsideFacesAfter': sum(new.values()),
          'removedBeforeFaces': removed_old, 'newPilotFaces': removed_new,
          'missingOutsideFaces': sum((old-new).values()), 'addedOutsideFaces': sum((new-old).values()),
          'sameNativeGeometryAndMaterials': old == new}
(ROOT/'work/urban-structure/p1/native-scope.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
assert old == new, 'Native geometry/material changed outside the replacement footprints'
