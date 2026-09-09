"""Guangxi Sports Center: the built stadium, arena and aquatics hall.

Plan control points are traced from OSM, stored in data/sports-center-footprints.json.
The two separate stadium leaves follow those footprints, not the unbuilt linked
roof in early masterplan renderings. Heights and facade details are an exterior
reconstruction from photographs, not construction drawings. Units are 100 m.
"""
import json
import math
from pathlib import Path


PLAN = json.loads((Path(__file__).resolve().parents[1] /
                   'data/sports-center-footprints.json').read_text())
SITE_PADS = ((0, 0, 1.72, 2.30),
             (-2.301, -3.935, .79, 1.19),
             (.674, -3.915, .82, 1.27))
MATERIAL_KEYS = ['sports_roof', 'sports_soffit', 'sports_frame', 'sports_glass',
                 'sports_stone', 'sports_track', 'sports_turf', 'sports_turf_light',
                 'sports_line', 'sports_seat_red', 'sports_seat_gold', 'sports_screen']


def pad_distance(u, v, pad):
    cx, cy, rx, ry = pad
    return (math.hypot((u-cx)/rx, (v-cy)/ry)-1)*min(rx, ry)


def inside_site(u, v):
    """Replace only the three venue envelopes, retaining the surrounding city."""
    return any(abs(u-cx) < rx and abs(v-cy) < ry for cx, cy, rx, ry in SITE_PADS)


def interpolate(points, y):
    """Monotone cubic interpolation along a mapped north/south roof edge."""
    p = sorted(points, key=lambda q: q[1])
    if y <= p[0][1]:
        return p[0][0]
    if y >= p[-1][1]:
        return p[-1][0]
    slopes = [(b[0]-a[0])/(b[1]-a[1]) for a, b in zip(p, p[1:])]
    tangents = [slopes[0]]
    for i in range(1, len(p)-1):
        a, b = slopes[i-1], slopes[i]
        tangents.append(2*a*b/(a+b) if a*b > 0 else 0)
    tangents.append(slopes[-1])
    for i, (a, b) in enumerate(zip(p, p[1:])):
        if a[1] <= y <= b[1]:
            h = b[1]-a[1]
            t = (y-a[1])/h
            return ((2*t**3-3*t*t+1)*a[0] + (t**3-2*t*t+t)*h*tangents[i]
                    + (-2*t**3+3*t*t)*b[0] + (t**3-t*t)*h*tangents[i+1])


def roof_point(side, t, u):
    edge = PLAN['roofEast' if side == 1 else 'roofWest']
    lo, hi = min(p[1] for p in edge['outer']), max(p[1] for p in edge['outer'])
    v = lo + (hi-lo)*t
    outer, inner = interpolate(edge['outer'], v), interpolate(edge['inner'], v)
    # Twisting cantilevers have high tips and a shallow saddle along each leaf.
    wave = t if side == 1 else 1-t
    arch = max(0, math.sin(math.pi*t))
    z = (.78 + .105*math.cos(math.tau*wave+.55)
         + .115*arch**2 + arch**.5*(.13*u + .07*math.sin(math.pi*u)))
    return (outer+(inner-outer)*u, v, z)


def oval(rx, ry, a):
    c, s = math.cos(a), math.sin(a)
    power = 2/2.3
    return (rx*math.copysign(abs(c)**power, c), ry*math.copysign(abs(s)**power, s))


def track_point(radius, a):
    return (radius*math.cos(a), radius*math.sin(a) + math.copysign(.42195, math.sin(a)))


def hall_section(name, t):
    outline = PLAN[name]['outline']
    lo, hi = min(p[1] for p in outline), max(p[1] for p in outline)
    y = lo+(hi-lo)*t
    hits = []
    for a, b in zip(outline, outline[1:]):
        if min(a[1], b[1]) <= y < max(a[1], b[1]):
            hits.append(a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]))
    if len(hits) < 2:
        tip = min(outline, key=lambda p: abs(p[1]-y))
        return tip[0], tip[0], y
    return min(hits), max(hits), y


def build_sports(b, x, y, z, ground=None):
    if ground is not None:
        z = ground(x, y)
    def world(p):
        return (x+p[0], y+p[1], z+p[2])

    def face(points, key, normals=None):
        # At leaf tips the two edges meet; emit a triangle instead of a collapsed quad.
        vertices, kept_normals = [], []
        for i, p in enumerate(points):
            if not any(sum((p[k]-q[k])**2 for k in range(3)) < 1e-16 for q in vertices):
                vertices.append(p)
                if normals:
                    kept_normals.append(normals[i])
        if len(vertices) >= 3:
            b.face([world(p) for p in vertices], key, kept_normals if normals else None)

    def beam(a, c, radius=.005, key='sports_frame'):
        b.beam(world(a), world(c), radius, key)

    def box(cx, cy, level, width, depth, rise, key, angle=0):
        b.box(x+cx, y+cy, z+level, width, depth, rise, key, angle=angle)

    def line(points, width=.002, key='sports_line'):
        for a, c in zip(points, points[1:]):
            dx, dy = c[0]-a[0], c[1]-a[1]
            length = math.hypot(dx, dy)
            if length < 1e-8:
                continue
            nx, ny = -dy/length*width/2, dx/length*width/2
            face([(a[0]+nx, a[1]+ny, a[2]), (a[0]-nx, a[1]-ny, a[2]),
                  (c[0]-nx, c[1]-ny, c[2]), (c[0]+nx, c[1]+ny, c[2])], key)

    def surface(fn, count=72, across=10, thickness=.025):
        def normal(t, u):
            eps = .0001
            a, c = fn(max(0, t-eps), u), fn(min(1, t+eps), u)
            d, e = fn(t, max(0, u-eps)), fn(t, min(1, u+eps))
            v, w = [c[i]-a[i] for i in range(3)], [e[i]-d[i] for i in range(3)]
            n = [v[1]*w[2]-v[2]*w[1], v[2]*w[0]-v[0]*w[2], v[0]*w[1]-v[1]*w[0]]
            length = math.sqrt(sum(q*q for q in n))
            if length < 1e-12:
                return (0, 0, 1)
            return tuple(q/length*(1 if n[2] >= 0 else -1) for q in n)

        grid = [[fn(i/count, j/across) for j in range(across+1)] for i in range(count+1)]
        ns = [[normal(i/count, j/across) for j in range(across+1)] for i in range(count+1)]
        for i in range(count):
            for j in range(across):
                ids = [(i, j), (i+1, j), (i+1, j+1), (i, j+1)]
                pts = [grid[a][c] for a, c in ids]
                normals = [ns[a][c] for a, c in ids]
                if ((pts[1][0]-pts[0][0])*(pts[2][1]-pts[0][1])
                    - (pts[1][1]-pts[0][1])*(pts[2][0]-pts[0][0])) < 0:
                    pts.reverse()
                    normals.reverse()
                face(pts, 'sports_roof', normals)
                face([(p[0], p[1], p[2]-thickness) for p in reversed(pts)],
                     'sports_soffit', [tuple(-q for q in n) for n in reversed(normals)])
        boundary = grid[0] + [row[-1] for row in grid[1:]] + list(reversed(grid[-1][:-1])) + [row[0] for row in reversed(grid[1:-1])]
        for a, c in zip(boundary, boundary[1:]+boundary[:1]):
            face([a, c, (c[0], c[1], c[2]-thickness), (a[0], a[1], a[2]-thickness)], 'sports_roof')

    def podium(cx, cy, rx, ry, level):
        for i in range(4):
            ring = [(cx+u, cy+v, level+i*.008) for u, v in
                    [oval(rx-i*.025, ry-i*.025, j/96*math.tau) for j in range(96)]]
            for a, c in zip(ring, ring[1:]+ring[:1]):
                bottom_a = ground(x+a[0], y+a[1])-z-.035 if ground and i == 0 else level+(i-1)*.008
                bottom_c = ground(x+c[0], y+c[1])-z-.035 if ground and i == 0 else level+(i-1)*.008
                face([(a[0], a[1], bottom_a), (c[0], c[1], bottom_c), c, a], 'sports_stone')
            face(ring, 'sports_stone')

    # A graded terrace is shared by the field and stand. The terrain callback is
    # level here, including in the two export qualities; no DEM passes through it.
    field_level = .038
    podium(0, 0, 1.58, 1.87, .006)
    for r in [.48, .4748]:
        ring = [(*track_point(r, (i+.5)/128*math.tau), field_level) for i in range(128)]
        face(ring, 'sports_track')
    # Inner green apron; the track is a capsule with straight sides, not an ellipse.
    face([(*track_point(.365, (i+.5)/128*math.tau), field_level+.002)
          for i in range(128)], 'sports_turf')
    for lane in range(10):
        points = [(*track_point(.365+lane*.0122, (i+.5)/128*math.tau), field_level+.003)
                  for i in range(129)]
        line(points, .0013)
    # FIFA-sized 105 x 68 m pitch, alternating mowing strips and field markings.
    for i in range(14):
        box(0, -.525+(i+.5)*1.05/14, field_level+.002, .68, 1.05/14, .001,
            'sports_turf_light' if i % 2 else 'sports_turf')
    h = field_level+.0045
    line([(-.34, -.525, h), (.34, -.525, h), (.34, .525, h), (-.34, .525, h), (-.34, -.525, h)], .002)
    line([(-.34, 0, h), (.34, 0, h)], .002)
    line([(.0915*math.cos(i/48*math.tau), .0915*math.sin(i/48*math.tau), h) for i in range(49)], .002)
    for side in [-1, 1]:
        for width, depth in [(.4032, .165), (.1832, .055)]:
            line([(-width/2, side*.525, h), (-width/2, side*(.525-depth), h),
                  (width/2, side*(.525-depth), h), (width/2, side*.525, h)], .002)
        goal_y = side*.527
        for gx in [-.0366, .0366]:
            beam((gx, goal_y, h), (gx, goal_y, h+.0244), .0014, 'sports_line')
            beam((gx, goal_y, h+.0244), (gx, goal_y+side*.025, h), .0008, 'sports_line')
        beam((-.0366, goal_y, h+.0244), (.0366, goal_y, h+.0244), .0014, 'sports_line')
        # Finish/start markings across the straight, kept clear of the grass.
        line([(side*.366, -.29, h), (side*.475, -.29, h)], .002)

    # Two stepped seating tiers, with radial aisles and a continuous concourse.
    for rows, inner, outer, base, rise in [(16, (.52, .99), (.85, 1.30), .065, .21),
                                          (20, (.90, 1.37), (1.22, 1.70), .32, .29)]:
        for row in range(rows):
            r0, r1 = row/rows, (row+1)/rows
            dims0 = tuple(a+(c-a)*r0 for a, c in zip(inner, outer))
            dims1 = tuple(a+(c-a)*r1 for a, c in zip(inner, outer))
            lower, upper = base+rise*r0, base+rise*r1
            for j in range(96):
                a, c = j/96*math.tau, (j+1)/96*math.tau
                p, q = oval(*dims0, a), oval(*dims0, c)
                r, s = oval(*dims1, c), oval(*dims1, a)
                key = ('sports_stone' if j % 6 == 0 else
                       ('sports_seat_gold' if (j//6+row//5) % 4 == 0 else 'sports_seat_red'))
                face([(*p, upper), (*q, upper), (*r, upper), (*s, upper)], key)
                face([(*p, lower), (*q, lower), (*q, upper), (*p, upper)], key)
    for inner, outer, level in [((.85, 1.30), (.90, 1.37), .286), ((1.22, 1.70), (1.32, 1.78), .614)]:
        for j in range(96):
            a, c = j/96*math.tau, (j+1)/96*math.tau
            face([(*oval(*inner, a), level), (*oval(*outer, a), level),
                  (*oval(*outer, c), level), (*oval(*inner, c), level)], 'sports_stone')

    # Layered exterior concourses, glazed bays and tilted concrete support frames.
    for j in range(80):
        a, c = j/80*math.tau, (j+1)/80*math.tau
        p, q = oval(1.29, 1.74, a), oval(1.29, 1.74, c)
        for level in [.09, .27, .46]:
            face([(*p, level), (*q, level), (*q, level+.125), (*p, level+.125)], 'sports_glass')
            beam((*p, level+.135), (*q, level+.135), .009, 'sports_stone')
        if j % 2 == 0:
            foot = oval(1.47, 1.82, a)
            beam((*foot, .035), (*p, .625), .018, 'sports_frame')
            beam((*p, .10), (*p, .61), .006)
    for side in [-1, 1]:
        fn = lambda t, u, side=side: roof_point(side, t, u)
        surface(fn)
        for j in range(1, 8):
            points = [tuple(p[k]+(.003 if k == 2 else 0) for k in range(3))
                      for p in [fn(i/72, j/8) for i in range(73)]]
            line(points, .0028, 'sports_frame')
        for i in range(3, 72, 3):
            line([tuple(p[k]+(.003 if k == 2 else 0) for k in range(3))
                  for p in [fn(i/72, j/10) for j in range(11)]], .002, 'sports_frame')
        for i in range(8, 66, 7):
            t = i/72
            a, c = fn(t, .15), fn(t, .82)
            beam((a[0], a[1], a[2]-.05), (c[0], c[1], c[2]-.05), .012)
            foot = (a[0]*.96, a[1]*.90, .31)
            beam(foot, (a[0], a[1], a[2]-.04), .015, 'sports_stone')
            beam(foot, (c[0], c[1], c[2]-.055), .009)
    for side in [-1, 1]:
        box(0, side*1.53, .52, .35, .04, .21, 'sports_frame')
        box(0, side*1.50, .537, .318, .014, .172, 'sports_screen')

    # Southwest indoor arena: two eaves flank a raised longitudinal clerestory.
    # Southeast aquatics hall: a lower closed silver shell with checkerboard glazing.
    for name, pad in [('arena', SITE_PADS[1]), ('aquatics', SITE_PADS[2])]:
        cx, cy, rx, ry = pad
        level = ground(x+cx, y+cy)-z if ground else 0
        podium(cx, cy, rx*.97, ry*.96, level+.006)

        def hall_roof(t, u):
            left, right, yy = hall_section(name, t)
            arch = max(0, math.sin(math.pi*t))
            xx = left+(right-left)*u
            if name == 'arena':
                zz = .35+.13*arch + .065*math.sin(math.pi*u) - .11*math.exp(-((u-.5)/.085)**2)
            else:
                zz = .10+.13*arch+.20*arch**.65*math.sin(math.pi*u)**.65
            return xx, yy, level+zz

        # Avoid collapsed sampled tips by starting just inside their mapped extent.
        fn = lambda t, u: hall_roof(.001+t*.998, u)
        surface(fn, count=56, across=12, thickness=.018)
        for j in range(1, 12):
            line([(p[0], p[1], p[2]+.002) for p in [fn(i/56, j/12) for i in range(57)]], .002, 'sports_frame')
        for i in range(2, 56, 3):
            line([(p[0], p[1], p[2]+.002) for p in [fn(i/56, j/12) for j in range(13)]], .002, 'sports_frame')
        if name == 'arena':
            for i in range(2, 54):
                a, c = fn(i/56, .45), fn((i+1)/56, .45)
                d, e = fn(i/56, .55), fn((i+1)/56, .55)
                face([(p[0], p[1], p[2]+.014) for p in [a, d, e, c]], 'sports_glass')
        for side in [0, 1]:
            for i in range(56):
                a, c = fn(i/56, side), fn((i+1)/56, side)
                top = min(a[2], c[2])-.022
                for row in range(3):
                    lo = level+.038+(top-level-.038)*row/3
                    hi = level+.038+(top-level-.038)*(row+1)/3
                    key = 'sports_glass' if name == 'arena' or (i+row) % 3 else 'sports_roof'
                    face([(a[0], a[1], lo), (c[0], c[1], lo), (c[0], c[1], hi), (a[0], a[1], hi)], key)
                if i % 2 == 0:
                    beam((a[0], a[1], level+.033), (a[0], a[1], a[2]-.02), .004)
        # Entry stairs and glazed doors remain small enough for the real site.
        for side in [-1, 1]:
            for i in range(5):
                box(cx+side*(rx*.84+i*.022), cy, level+.003, .035, .38, .036-i*.006, 'sports_stone')
