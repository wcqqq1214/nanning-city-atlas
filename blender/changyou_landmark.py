"""Five-storey Changyou Tower, with curved tile roofs and a raised colonnade.

Footprint: OSM way 808502329. Five exposed storeys and five roof tiers, 49.9 m
including a 10 m base: Guangxi News, 2013-06-09; completed exterior: Nanguo
Morning Post, Zou Cailin, 2026-05-10. Heights retain the atlas's 1.55 exaggeration.
Small timber details are illustrative, not a measured conservation survey.
"""
import math

MATERIAL_KEYS = ['changyou_tile', 'changyou_tile_rib', 'changyou_eave',
                 'changyou_wood', 'changyou_dark', 'changyou_stone', 'changyou_window']
ANGLE = math.radians(-25.28)
PODIUM = .155
WIDTH, DEPTH = .54, .435


def inside_site(x, y, margin=0):
    u = x*math.cos(ANGLE)+y*math.sin(ANGLE)
    v = -x*math.sin(ANGLE)+y*math.cos(ANGLE)
    return abs(u) < WIDTH/2+.045+margin and -DEPTH/2-.065-margin < v < DEPTH/2+.14+margin


def build_changyou(b, x, y, z, ground=None):
    c, s = math.cos(ANGLE), math.sin(ANGLE)

    def p(u, v, h):
        return (x+u*c-v*s, y+u*s+v*c, z+h)

    def face(points, key, normals=None):
        b.face([p(*q) for q in points], key,
               [(a*c-d*s, a*s+d*c, h) for a, d, h in normals] if normals else None)

    def box(u, v, h, w, d, rise, key, roof=None):
        px, py, pz = p(u, v, h)
        b.box(px, py, pz, w, d, rise, key, roof, ANGLE)

    def beam(a, d, radius, key='changyou_wood'):
        b.beam(p(*a), p(*d), radius, key)

    def cylinder(u, v, h, radius, rise, key, segments=10):
        px, py, pz = p(u, v, h)
        b.cone(px, py, pz, radius, radius, rise, key, segments)

    def railing(a, d, level, height=.026, key='changyou_wood', spacing=.034):
        length = math.dist(a, d)
        count = max(1, round(length/spacing))
        points = [(a[0]+(d[0]-a[0])*i/count, a[1]+(d[1]-a[1])*i/count) for i in range(count+1)]
        for u, v in points:
            beam((u, v, level), (u, v, level+height+.003), .0024, key)
        for h in [.006, height]:
            beam((*a, level+h), (*d, level+h), .0023, key)
        for aa, dd in zip(points, points[1:]):
            # Repeated open lattice, rather than solid balcony walls.
            beam((*aa, level+.008), (*dd, level+height-.003), .0013, key)
            beam((*dd, level+.008), (*aa, level+height-.003), .0013, key)

    # Thirty-eight visible/peripheral and interior supports under the platform.
    supports = [(u, side*(DEPTH/2-.019)) for side in [-1, 1]
                for u in [-WIDTH/2+.021+i*(WIDTH-.042)/8 for i in range(9)]]
    supports += [(side*(WIDTH/2-.021), v) for side in [-1, 1]
                 for v in [-DEPTH/2+.085+i*(DEPTH-.170)/4 for i in range(5)]]
    supports += [(u, v) for v in [-.075, .075] for u in [-.18, -.09, 0, .09, .18]]
    for u, v in supports:
        xx, yy, _ = p(u, v, 0)
        base = (ground(xx, yy)-z if ground else 0)-.018
        box(u, v, base, .016, .016, PODIUM-base-.013, 'changyou_stone')
        box(u, v, base, .025, .025, .013, 'changyou_stone')
        box(u, v, PODIUM-.022, .027, .027, .014, 'changyou_stone')
    box(0, 0, PODIUM-.015, WIDTH, DEPTH, .019, 'changyou_stone')
    box(0, 0, PODIUM-.022, WIDTH+.007, DEPTH+.007, .006, 'changyou_tile_rib')
    # Paired stone flights toward the inland entrance, with low side parapets.
    for side in [-1, 1]:
        u = side*(WIDTH/2-.045)
        for i in range(13):
            v = DEPTH/2+.124-i*.0098
            xx, yy, _ = p(u, v, 0)
            lower = ground(xx, yy)-z if ground else 0
            top = lower+(PODIUM-lower)*(i+1)/13
            box(u, v, lower-.008, .063, .0105, max(.004, top-lower+.008), 'changyou_stone')
        beam((u+side*.035, DEPTH/2+.125, .035),
             (u+side*.035, DEPTH/2, PODIUM+.035), .004, 'changyou_stone')
    for a, d in [((-.263, -.210), (.263, -.210)), ((-.263, -.210), (-.263, .18)),
                 ((.263, -.210), (.263, .18))]:
        railing(a, d, PODIUM+.004, .030, 'changyou_stone')

    def roof(w, d, base, rise, top=False, center=(0, 0)):
        ridge = w*(.25 if top else .31)
        lift = .013 if top else .009

        def roof_face(points, key, normals=None):
            aa, bb, cc = points[:3]
            winding = (bb[0]-aa[0])*(cc[1]-aa[1])-(bb[1]-aa[1])*(cc[0]-aa[0])
            if winding < 0:
                points = points[::-1]
                normals = normals[::-1] if normals else None
            face(points, key, normals)

        def q(a, t, axis, side):
            # Concave roof slopes and lifted corners, with a straight ridge.
            height = base+rise*(.30*t+.70*t*t)+(.003+lift*abs(a)**8)*(1-t)**5
            if axis == 0:
                return (center[0]+a*((1-t)*w/2+t*ridge), center[1]+side*(1-t)*d/2, height)
            return (center[0]+side*((1-t)*w/2+t*ridge), center[1]+a*(1-t)*d/2, height)

        def normal(a, t, axis, side):
            t = min(.999, t)
            da = [v-u for u, v in zip(q(a-.0001, t, axis, side), q(a+.0001, t, axis, side))]
            dt = [v-u for u, v in zip(q(a, t-.0001, axis, side), q(a, t+.0001, axis, side))]
            n = (da[1]*dt[2]-da[2]*dt[1], da[2]*dt[0]-da[0]*dt[2], da[0]*dt[1]-da[1]*dt[0])
            length = math.sqrt(sum(v*v for v in n))
            return tuple(v/length*(1 if n[2] >= 0 else -1) for v in n)

        for axis in [0, 1]:
            count = 22 if axis == 0 else 14
            for side in [-1, 1]:
                for i in range(count):
                    a, aa = -1+2*i/count, -1+2*(i+1)/count
                    for j in range(7):
                        t, tt = j/7, (j+1)/7
                        params = [(a, t), (aa, t), (aa, tt), (a, tt)]
                        if axis == 1 and j == 6:
                            params = params[:3]
                        roof_face([q(u, v, axis, side) for u, v in params], 'changyou_tile',
                             [normal(u, v, axis, side) for u, v in params])
                        # Narrow raised tile courses follow the same curved surface.
                        if j < 6 or axis == 0:
                            params = [(a+.016, t), (a+.027, t), (a+.027, tt), (a+.016, tt)]
                            roof_face([(u, v, h+.0012) for u, v, h in [q(u, v, axis, side) for u, v in params]],
                                 'changyou_tile_rib')
                    e, ee = q(a, 0, axis, side), q(aa, 0, axis, side)
                    face([e, ee, (ee[0], ee[1], ee[2]-.006), (e[0], e[1], e[2]-.006)], 'changyou_eave')
                # Ridge and curled hip trim remain visible in an oblique close view.
                for a in ([-1, 1] if axis == 0 else []):
                    for j in range(7):
                        e, ee = q(a, j/7, axis, side), q(a, (j+1)/7, axis, side)
                        if math.dist(e, ee) > .00001:
                            beam(e, ee, .002, 'changyou_tile_rib')
        beam((center[0]-ridge, center[1], base+rise+.002),
             (center[0]+ridge, center[1], base+rise+.002), .0032, 'changyou_tile_rib')
        for side in [-1, 1]:
            beam((center[0]+side*ridge, center[1], base+rise),
                 (center[0]+side*(ridge+.015), center[1], base+rise+.014), .003, 'changyou_tile_rib')
        if top:
            # Intersecting gables join in one cross-shaped roof surface. Four
            # triangular timber ends reproduce the completed tower's top tier.
            gx, gy, peak = .075, .062, base+rise+.034
            def cross_roof(u, v):
                t = min(abs(u)/gx, abs(v)/gy)
                return (u, v, peak-.069*(.3*t+.7*t*t))
            for i in range(12):
                for j in range(12):
                    u, uu = -gx+2*gx*i/12, -gx+2*gx*(i+1)/12
                    v, vv = -gy+2*gy*j/12, -gy+2*gy*(j+1)/12
                    roof_face([cross_roof(u, v), cross_roof(uu, v), cross_roof(uu, vv), cross_roof(u, vv)], 'changyou_tile')
            for axis in [0, 1]:
                span, side_span = (gx, gy) if axis == 0 else (gy, gx)
                for side in [-1, 1]:
                    def gp(t, h):
                        return (side*span, t, h) if axis == 0 else (t, side*span, h)
                    gable = [gp(-side_span, base+.028), gp(side_span, base+.028)]
                    for j in range(13):
                        t = 1-j/6
                        gable.append(gp(t*side_span, peak-.069*(.3*abs(t)+.7*t*t)))
                    face(gable, 'changyou_wood')
                    for half in [-1, 1]:
                        for j in range(6):
                            t, tt = half*side_span*j/6, half*side_span*(j+1)/6
                            def edge(t):
                                z = peak-.069*(.3*abs(t)/side_span+.7*(t/side_span)**2)
                                return gp(t, z)
                            beam(edge(t), edge(tt), .0028, 'changyou_eave')
                beam(gp(0, peak), tuple(-v if k < 2 else v for k, v in enumerate(gp(0, peak))), .003, 'changyou_tile_rib')

    for level in range(5):
        base = PODIUM+.008+level*.111
        w, d = .366-level*.030, .274-level*.020
        box(0, 0, base, w, d, .071, 'changyou_dark')
        box(0, 0, base, w+.034, d+.034, .009, 'changyou_wood')
        for axis in [0, 1]:
            length, depth = (w, d) if axis == 0 else (d, w)
            count = 7 if axis == 0 else 5
            for side in [-1, 1]:
                for i in range(count):
                    offset = -length/2+(i+.5)*length/count
                    u, v = (offset, side*(depth/2+.002)) if axis == 0 else (side*(depth/2+.002), offset)
                    if axis == 0:
                        box(u, v, base+.020, length/count*.73, .003, .042, 'changyou_window')
                    else:
                        box(u, v, base+.020, .003, length/count*.73, .042, 'changyou_window')
                    beam((u, v, base+.02), (u, v, base+.063), .0018, 'changyou_wood')
                    uu, vv = (offset, side*(depth/2+.017)) if axis == 0 else (side*(depth/2+.017), offset)
                    cylinder(uu, vv, base+.01, .0038, .065, 'changyou_wood', 8)
                    # Bracket blocks and cantilever arms under the eaves.
                    box(uu, vv, base+.064, .010, .010, .008, 'changyou_eave')
                    beam((uu, vv, base+.066), (uu+(.014*side if axis else 0), vv+(.014*side if not axis else 0), base+.075),
                         .0023, 'changyou_wood')
        for a, e in [((-w/2-.019, -d/2-.020), (w/2+.019, -d/2-.020)),
                     ((-w/2-.019, d/2+.020), (w/2+.019, d/2+.020)),
                     ((-w/2-.020, -d/2), (-w/2-.020, d/2)),
                     ((w/2+.020, -d/2), (w/2+.020, d/2))]:
            railing(a, e, base+.008, .020)
        roof(w+.080, d+.080, base+.078, .075 if level == 4 else .037, top=level == 4)
    # Projecting entrance roofs break up the bottom tier's rectangular outline.
    for side in [-1, 1]:
        box(0, side*.158, PODIUM+.008, .105, .077, .066, 'changyou_wood')
        roof(.136, .120, PODIUM+.076, .033, center=(0, side*.148))
