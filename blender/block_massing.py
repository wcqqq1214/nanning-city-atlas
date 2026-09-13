"""Bounded compound massing; ground extrema come from the caller's final surface.

No bpy dependency. The P5 candidate renderer uses flat ground; city integration
must supply extrema over the complete footprint in both displayed terrain meshes.
"""


def build_compound(batch, building, ground_range, material, limit=None):
    low, high = ground_range
    if low > high:
        raise ValueError('Ground extrema are reversed')
    anchor = high+.002  # 0.2 m clearance; one scene unit is 100 m.
    parts = building['massing']
    visible = [p for p in parts if limit is None or limit > anchor+p['baseMeters']/100]
    if not visible:
        return None
    tops = []
    for part in visible:
        base = low-.005 if part['baseMeters'] == 0 else anchor+part['baseMeters']/100
        top = anchor+part['topMeters']/100
        if limit is not None:
            top = min(top, limit)
        for ring in part['rings']:
            for a, b in zip(ring, ring[1:]):
                batch.face([(*a, base), (*b, base), (*b, top), (*a, top)], material)
        upper_continues = any(other is not part and
            anchor+other['baseMeters']/100 <= top < anchor+other['topMeters']/100 and
            (limit is None or limit > top) for other in visible)
        triangles = part['roofTriangles'] if upper_continues else part['fullRoofTriangles']
        for triangle in triangles:
            batch.face([(*point, top) for point in triangle], 'roof')
        tops.append(top)
    return {'id': building['id'], 'floor': anchor, 'top': max(tops), 'supportRange': [low, high]}
