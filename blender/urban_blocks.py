"""Shared residential massing and support geometry (no bpy dependency)."""
import math


def support_samples(building, surface):
    """Densely sample both displayed surfaces, including inside long slab roofs."""
    outer = building['rings'][0][:-1]
    xs, ys = zip(*outer)
    # New slabs are rectangles; bounding-box samples are conservative when rotated.
    nx = max(1, math.ceil((max(xs)-min(xs))/.06))
    ny = max(1, math.ceil((max(ys)-min(ys))/.06))
    return [surface(min(xs)+(max(xs)-min(xs))*i/nx, min(ys)+(max(ys)-min(ys))*j/ny)
            for i in range(nx+1) for j in range(ny+1)]


def support_level(building, surface):
    return max(level[1] for level in support_samples(building, surface)) + .012


def build_massing(batch, building, surface, material, limit=None):
    z = support_level(building, surface)
    top = z + building['height']/100*building.get('displayHeightScale', 1.0)
    if limit is not None:
        top = min(top, limit)
    if top <= z:
        return None
    for ring in building['rings']:
        for a, b in zip(ring, ring[1:]):
            count = max(1, math.ceil(math.dist(a, b)/.06))
            for i in range(count):
                p, q = [tuple(a[k]+(b[k]-a[k])*t/count for k in [0, 1]) for t in [i, i+1]]
                # Sink the skirt into the lower of the two actual triangle surfaces.
                lower = [surface(*v)[0]-.015 for v in [p, q]]
                batch.face([(*p, lower[0]), (*q, lower[1]), (*q, top), (*p, top)], material)
    for tri in building['roofTriangles']:
        batch.face([(*point, top) for point in tri], 'roof')
    return {'id': building['id'], 'floor': z, 'top': top,
            'supportRange': [min(p[0] for p in support_samples(building, surface)), z-.012]}


def palette_records(geo):
    """Replay old palette slots, including removed houses, before drawing new slabs.

    This keeps every retained house and subsequent tree at its previous RNG draw.
    Building geometry uses the current array and road indices, never these slots.
    """
    originals = {b['id']: b for b in geo.get('buildingQuality', {}).get('originalBuildings', [])}
    rows = [originals.get(b['id'], b) for b in geo['buildings'] if 'legacyIndex' in b]
    rows += [b for block in geo.get('urbanBlocks', []) for b in block['removedBuildings']]
    return sorted(rows, key=lambda b: b['legacyIndex'])
