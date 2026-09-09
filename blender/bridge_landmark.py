"""Nanning Bridge, a curved tied arch with two independent inclined steel ribs.

Geometry references: OPAC design elevation, plan and cross section, plus the
completed bridge photographs. https://www.opacengineers.com/features/Nanning
Mapped carriageways determine the plan alignment. The 300.5 m main span and
asymmetric arch planes are retained; heights are exaggerated for this atlas.
"""
import bisect
import math

MATERIAL_KEYS = ['nbridge_steel', 'nbridge_edge', 'nbridge_road', 'nbridge_concrete',
                 'nbridge_cable', 'nbridge_line']
MAIN_SPAN = 3.005
NORTH_APPROACH = 1.58
HALF_WIDTH = .218


class BridgePath:
    def __init__(self, roads):
        candidates = [r['points'] for r in roads if r['name'] == '南宁大桥' and r['bridge']]
        assert len(candidates) == 2, 'Nanning Bridge requires both mapped carriageways'
        aligned = [p if p[0][1] > p[-1][1] else p[::-1] for p in candidates]
        assert len(aligned[0]) == len(aligned[1]), 'Carriageway control stations differ'
        controls = [tuple((a[i]+b[i])/2 for i in range(2)) for a, b in zip(*aligned)]
        # Interpolate the aligned centre line with endpoint-preserving tangents.
        extended = [tuple(2*a-b for a, b in zip(controls[0], controls[1]))] + controls
        extended += [tuple(2*a-b for a, b in zip(controls[-1], controls[-2]))]
        self.points = []
        for i in range(len(controls)-1):
            a, b, c, d = extended[i:i+4]
            for j in range(48):
                t = j/48
                self.points.append(tuple(.5*(2*bb+(-aa+cc)*t+(2*aa-5*bb+4*cc-dd)*t*t
                                              +(-aa+3*bb-3*cc+dd)*t*t*t)
                                         for aa, bb, cc, dd in zip(a, b, c, d)))
        self.points.append(controls[-1])
        self.lengths = [0]
        for a, b in zip(self.points, self.points[1:]):
            self.lengths.append(self.lengths[-1]+math.dist(a, b))
        self.total = self.lengths[-1]

    def at(self, distance, offset=0, level=0):
        s = max(0, min(self.total, distance))
        i = max(0, min(len(self.points)-2, bisect.bisect_right(self.lengths, s)-1))
        a, b = self.points[i:i+2]
        length = self.lengths[i+1]-self.lengths[i]
        t = (s-self.lengths[i])/length
        nx, ny = -(b[1]-a[1])/length, (b[0]-a[0])/length
        return (a[0]+(b[0]-a[0])*t+nx*offset, a[1]+(b[1]-a[1])*t+ny*offset, level)


def build_bridge(b, roads, height):
    path = BridgePath(roads)
    start, end = NORTH_APPROACH, NORTH_APPROACH+MAIN_SPAN
    assert end < path.total
    north = height(*path.at(0)[:2])+.065
    south = height(*path.at(path.total)[:2])+.065
    deck = max(1.16, north+.22, south+.22)

    def level(s):
        if s < start:
            t = max(0, s/start)
            return north+(deck-north)*t*t*(3-2*t)
        if s > end:
            t = min(1, (s-end)/(path.total-end))
            return deck+(south-deck)*t*t*(3-2*t)
        return deck

    def at(s, offset=0, dz=0):
        return path.at(s, offset, level(s)+dz)

    def strip(s, t, a, c, dz, key):
        a, c = sorted((a, c))
        b.face([at(s, a, dz), at(t, a, dz), at(t, c, dz), at(s, c, dz)], key)

    # Continuous steel box deck, with a narrower soffit and sloping outer webs.
    section = [(-HALF_WIDTH, 0), (HALF_WIDTH, 0), (HALF_WIDTH, -.035),
               (.158, -.082), (-.158, -.082), (-HALF_WIDTH, -.035)]
    steps = 176
    for i in range(steps):
        s, t = path.total*i/steps, path.total*(i+1)/steps
        for j, (off, dz) in enumerate(section):
            off2, dz2 = section[(j+1)%len(section)]
            b.face([at(s, off, dz), at(t, off, dz), at(t, off2, dz2), at(s, off2, dz2)],
                   'nbridge_road' if j == 0 else 'nbridge_concrete')
        for side in [-1, 1]:
            strip(s, t, side*.176, side*.211, .010, 'nbridge_edge')
            strip(s, t, side*.008, side*.012, .005, 'nbridge_line')
            strip(s, t, side*.165, side*.169, .005, 'nbridge_line')
            # Slim outer parapet and inset horizontal safety rails.
            for dz in [.025, .044]:
                b.beam(at(s, side*.215, dz), at(t, side*.215, dz), .0022, 'nbridge_cable')
            b.beam(at(s, side*.179, .015), at(t, side*.179, .015), .004, 'nbridge_edge')
            if i % 2 == 0:
                b.beam(at(s, side*.215, .010), at(s, side*.215, .047), .0024, 'nbridge_cable')
        if i % 3 == 0:
            for offset in [-.115, -.064, .064, .115]:
                strip(s, min(s+.047, path.total), offset-.0018, offset+.0018, .005, 'nbridge_line')
    for s in [0, path.total]:
        b.face([at(s, off, dz) for off, dz in section], 'nbridge_concrete')
    for s in [start, end, .55, 1.05, 5.15, 5.72, 6.28, 6.84]:
        if s < path.total:
            strip(s, s+.008, -.21, .21, .012, 'nbridge_cable')

    # Each arch lies in its own tilted plane above the straight support chord.
    # This is distinct from the gently curved deck's transverse cable anchors.
    a, c = path.at(start), path.at(end)
    chord = math.dist(a[:2], c[:2])
    tangent = ((c[0]-a[0])/chord, (c[1]-a[1])/chord, 0)
    normal = (-tangent[1], tangent[0], 0)

    def arch(t, side):
        rise = (1.015 if side < 0 else 1.045)*4*t*(1-t)
        angle = math.radians(19.42 if side < 0 else 24.37)
        offset = side*(.185+rise*math.tan(angle))
        return (a[0]+(c[0]-a[0])*t+normal[0]*offset,
                a[1]+(c[1]-a[1])*t+normal[1]*offset, deck-.18+rise)

    def unit(v):
        d = math.sqrt(sum(k*k for k in v))
        return tuple(k/d for k in v)

    def cross(u, v):
        return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])

    def rib_ring(t, side):
        p = arch(t, side)
        before, after = arch(max(0, t-.0001), side), arch(min(1, t+.0001), side)
        axis = unit(tuple(cc-aa for aa, cc in zip(before, after)))
        angle = math.radians(19.42 if side < 0 else 24.37)
        plane_up = (side*normal[0]*math.tan(angle), side*normal[1]*math.tan(angle), 1)
        across = unit(cross(tangent, plane_up))
        up = unit(cross(axis, across))
        half_w = .026
        half_h = .044-.012*math.sin(t*math.pi)
        bevel = .004
        ring = [(-half_w+bevel, -half_h), (half_w-bevel, -half_h),
                (half_w, -half_h+bevel), (half_w, half_h-bevel),
                (half_w-bevel, half_h), (-half_w+bevel, half_h),
                (-half_w, half_h-bevel), (-half_w, -half_h+bevel)]
        return [tuple(p[i]+across[i]*u+up[i]*v for i in range(3)) for u, v in ring]

    for side in [-1, 1]:
        rings = [rib_ring(i/112, side) for i in range(113)]
        for i in range(112):
            for j in range(8):
                k = (j+1)%8
                b.face([rings[i][j], rings[i+1][j], rings[i+1][k], rings[i][k]], 'nbridge_steel')
        b.face(rings[0][::-1], 'nbridge_steel')
        b.face(rings[-1], 'nbridge_steel')
        for i in range(1, 30):
            t = i/30
            upper = arch(t, side)
            lower = at(start+(end-start)*t, side*.172, -.006)
            if upper[2] < lower[2]+.045:
                continue
            b.beam(lower, upper, .0027, 'nbridge_cable')
            # Cable shoes at the deck, and short collars at their upper anchors.
            axis = unit(tuple(cc-aa for aa, cc in zip(lower, upper)))
            b.beam(lower, tuple(lower[k]+axis[k]*.025 for k in range(3)), .0065, 'nbridge_edge')
            b.beam(tuple(upper[k]-axis[k]*.021 for k in range(3)), upper, .0055, 'nbridge_steel')
        # Concrete inclined arch springings into the main pier crossheads.
        for s, t in [(start, 0), (end, 1)]:
            root = path.at(s, side*.108, .40)
            b.beam(root, arch(t, side), .062, 'nbridge_concrete')

    # Approach supports stay outside the main navigation span.
    for s in [.08, .57, 1.08, start, end, 5.14, 5.73, 6.30, 6.87, path.total-.08]:
        if s > path.total:
            continue
        main = abs(s-start) < .001 or abs(s-end) < .001
        px, py, _ = at(s)
        bottom = max(.15, height(px, py)-.045)
        top = level(s)-.095
        if top <= bottom+.02:
            continue
        b.beam(path.at(s, -.153, top), path.at(s, .153, top), .037 if main else .025, 'nbridge_concrete')
        for side in [-1, 1]:
            b.beam(path.at(s, side*.105, bottom), path.at(s, side*.105, top),
                   .046 if main else .027, 'nbridge_concrete')
        if main:
            b.beam(path.at(s, -.15, bottom+.025), path.at(s, .15, bottom+.025), .052, 'nbridge_concrete')
    for i in range(1, 21):
        s = path.total*i/22
        for side in [-1, 1]:
            base = at(s, side*.197, .025)
            mast = at(s, side*.197, .165)
            head = at(s, side*.142, .183)
            b.beam(base, mast, .0025, 'nbridge_cable')
            b.beam(mast, head, .0022, 'nbridge_cable')
            b.beam(head, at(s, side*.127, .183), .004, 'nbridge_edge')
    return at((start+end)/2)
