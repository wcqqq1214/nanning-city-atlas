"""Tingzi waterfront: three spires, arcaded streets and a blue-grey rotunda.

Exterior reference: China News Service, Chen Guanyan, 2023-05-28.
https://www.gx.chinanews.com.cn/sh/2023-05-28/detail-ihcpswxf4323137.shtml
Street direction and pier outline follow the cached OSM survey. Facade details
and heights are an independently drawn, illustrative reconstruction, not a scan.
"""
import math

MATERIAL_KEYS = ['tingzi_wall', 'tingzi_trim', 'tingzi_glass', 'tingzi_roof',
                 'tingzi_dome', 'tingzi_paving', 'tingzi_deck']
ANGLE = math.radians(42.1)
ANCHOR_SHIFT = (-.33+.53*math.cos(ANGLE)+.025*math.sin(ANGLE),
                -.94+.53*math.sin(ANGLE)-.025*math.cos(ANGLE))
ORIGIN = (-.33-ANCHOR_SHIFT[0], -.94-ANCHOR_SHIFT[1])
SITE = [(-1.22, -.72), (.80, -.72), (.80, .43), (-1.22, .43)]
PIER = [(.754, 1.111), (.783, 1.035), (.696, 1.001), (.724, .929),
        (.810, .962), (.912, .699), (.827, .665), (.849, .608),
        (.936, .642), (1.012, .448), (1.160, .506), (.901, 1.169)]
PIER = [(x-ANCHOR_SHIFT[0], y-ANCHOR_SHIFT[1]) for x, y in PIER]


def site_xy(u, v):
    return (ORIGIN[0]+u*math.cos(ANGLE)-v*math.sin(ANGLE),
            ORIGIN[1]+u*math.sin(ANGLE)+v*math.cos(ANGLE))


def inside_site(x, y, margin=0):
    dx, dy = x-ORIGIN[0], y-ORIGIN[1]
    u, v = dx*math.cos(ANGLE)+dy*math.sin(ANGLE), -dx*math.sin(ANGLE)+dy*math.cos(ANGLE)
    # This replaces the visitor complex, while retaining the neighbouring theatre.
    pier_x, pier_y = x+ANCHOR_SHIFT[0], y+ANCHOR_SHIFT[1]
    return (-1.28-margin < u < .87+margin and -.79-margin < v < .50+margin) or (
        .66-margin < pier_x < 1.20+margin and .40-margin < pier_y < 1.21+margin)


def terrace_level(x, y, z, ground):
    # Sample the interior as well as the boundary, so a coarse terrain grid
    # cannot poke through the terrace between its four corners.
    return max(ground(x+site_xy(u, v)[0], y+site_xy(u, v)[1]) if ground else z
               for u in [-1.22+i*2.02/8 for i in range(9)]
               for v in [-.72+i*1.15/6 for i in range(7)])+.028


def build_tingzi(b, x, y, z, ground=None):
    def p(u, v, h):
        dx, dy = site_xy(u, v)
        return (x+dx, y+dy, h)

    def face(points, key):
        b.face([p(*a) for a in points], key)

    def box(u, v, h, width, depth, rise, key, roof=None):
        xx, yy, _ = p(u, v, h)
        b.box(xx, yy, h, width, depth, rise, key, roof, angle=ANGLE)

    def beam(a, c, radius, key='tingzi_trim'):
        b.beam(p(*a), p(*c), radius, key)

    levels = [ground(*p(u, v, 0)[:2]) if ground else z for u, v in SITE]
    floor = terrace_level(x, y, z, ground)
    # Narrow stone terrace, with terrain-following retaining walls; no platform
    # is placed across the river or the separate OSM passenger pier.
    face([(u, v, floor) for u, v in SITE], 'tingzi_paving')
    for i, (u, v) in enumerate(SITE):
        j = (i+1) % len(SITE)
        uu, vv = SITE[j]
        face([(u, v, levels[i]-.018), (uu, vv, levels[j]-.018),
              (uu, vv, floor), (u, v, floor)], 'tingzi_wall')
    for i in range(24):
        u = -1.20+i*.082
        box(u, -.04, floor+.001, .005, .43, .002, 'tingzi_trim')
    for v in [-.265, .16]:
        box(-.20, v, floor+.002, 1.99, .012, .006, 'tingzi_trim')

    def arch_window(u, v, h, width, rise, normal=(0, -1), bars=True):
        # Dark inset and solid arch voussoirs are separated in depth to avoid
        # coplanar flicker. Tangent crosses the opening, normal faces outside.
        nx, ny = normal
        tx, ty = -ny, nx
        radius, trim = width/2, .008
        spring = rise-radius
        def q(t, zz, depth):
            return (u+tx*t+nx*depth, v+ty*t+ny*depth, h+zz)
        points = [q(-radius, 0, .002), q(radius, 0, .002)]
        points += [q(radius*math.cos(i/10*math.pi), spring+radius*math.sin(i/10*math.pi), .002)
                   for i in range(11)]
        face(points, 'tingzi_glass')
        for i in range(10):
            a, c = i/10*math.pi, (i+1)/10*math.pi
            face([q(radius*math.cos(a), spring+radius*math.sin(a), .006),
                  q((radius+trim)*math.cos(a), spring+(radius+trim)*math.sin(a), .006),
                  q((radius+trim)*math.cos(c), spring+(radius+trim)*math.sin(c), .006),
                  q(radius*math.cos(c), spring+radius*math.sin(c), .006)], 'tingzi_trim')
        for side in [-1, 1]:
            beam(q(side*(radius+trim/2), 0, .006), q(side*(radius+trim/2), spring, .006), trim/2)
        beam(q(-radius-trim, 0, .009), q(radius+trim, 0, .009), .006)
        if bars:
            beam(q(0, .006, .008), q(0, rise-.009, .008), .002, 'tingzi_wall')
            beam(q(-radius, spring*.58, .008), q(radius, spring*.58, .008), .002, 'tingzi_wall')

    def cornice(u, v, h, w, d):
        box(u, v, h, w+.012, d+.012, .009, 'tingzi_trim')
        box(u, v, h+.009, w+.024, d+.024, .006, 'tingzi_trim')

    def spire(u, v, h, radius, rise):
        # A proper triangle fan at the tip avoids zero-area cone faces.
        ring = [(u+radius*math.cos(a*math.tau/8), v+radius*math.sin(a*math.tau/8), h)
                for a in range(8)]
        for i in range(8):
            face([ring[i], ring[(i+1)%8], (u, v, h+rise)], 'tingzi_roof')
            beam(ring[i], (u, v, h+rise), .0016, 'tingzi_roof')
        beam((u, v, h+rise), (u, v, h+rise+.020), .002, 'accent')

    # Flat-roofed, three-storey arcade on the northwest side of the street.
    for center, length in [(-.63, 1.04), (.225, .55)]:
        box(center, .30, floor, length, .245, .325, 'tingzi_wall', 'tingzi_paving')
        for h in [.115, .218, .325]:
            cornice(center, .30, floor+h, length, .245)
        for side in [-1, 1]:
            box(center, .30+side*.120, floor+.34, length, .015, .026, 'tingzi_wall')
        n = round(length/.11)
        for i in range(n):
            u = center-length/2+(i+.5)*length/n
            for side in [-1, 1]:
                v = .30+side*.124
                for level in range(3):
                    arch_window(u, v, floor+.012+level*.103, .054, .079,
                                normal=(0, side), bars=level > 0)
            box(u+.047, .17, floor+.012, .013, .018, .305, 'tingzi_trim')
        for side in [-1, 1]:
            for level in range(3):
                arch_window(center+side*(length/2+.002), .30, floor+.016+level*.103,
                            .058, .077, (side, 0))
    # Two smaller red-roofed shops opposite the arcade.
    for u in [-.78, -.26]:
        w, d, top = .38, .27, floor+.214
        box(u, -.43, floor, w, d, .214, 'tingzi_wall')
        cornice(u, -.43, top, w, d)
        corners = [(u-w/2-.014, -.43-d/2-.014, top+.015),
                   (u+w/2+.014, -.43-d/2-.014, top+.015),
                   (u+w/2+.014, -.43+d/2+.014, top+.015),
                   (u-w/2-.014, -.43+d/2+.014, top+.015)]
        a, c = (u-.09, -.43, top+.09), (u+.09, -.43, top+.09)
        for poly in [[corners[0], corners[1], c, a], [corners[1], corners[2], c],
                     [corners[2], corners[3], a, c], [corners[3], corners[0], a]]:
            face(poly, 'tingzi_roof')
        beam(a, c, .007, 'tingzi_roof')
        for side in [-1, 1]:
            for offset in [-.12, 0, .12]:
                for level in range(2):
                    arch_window(u+offset, -.43+side*.137, floor+.014+level*.103,
                                .063, .076, (0, side))

    # Three-spire riverfront facade. Photos show lancet windows, not clock faces.
    tower_u = .53
    box(tower_u, -.025, floor, .225, .64, .238, 'tingzi_wall')
    cornice(tower_u, -.025, floor+.238, .225, .64)
    for side in [-1, 1]:
        for v in [-.265, -.145, -.025, .095, .215]:
            arch_window(tower_u+side*.114, v, floor+.014, .078, .114, (side, 0), False)
            arch_window(tower_u+side*.114, v, floor+.153, .056, .066, (side, 0))
    for v, width, height, peak in [(-.295, .113, .342, .153),
                                  (-.025, .154, .545, .225),
                                  (.245, .113, .342, .153)]:
        box(tower_u, v, floor+.22, width, width, height-.22, 'tingzi_wall')
        for h in [.235, height-.108, height]:
            cornice(tower_u, v, floor+h, width, width)
        for nx, ny in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            for level in range(1 if height > .4 else 0):
                arch_window(tower_u+nx*(width/2+.001), v+ny*(width/2+.001),
                            floor+height-.242, width*.45, .092, (nx, ny))
            for offset in [-.27, .27]:
                # Small paired lancets under each spire's crown.
                arch_window(tower_u+nx*(width/2+.002)-ny*width*offset,
                            v+ny*(width/2+.002)+nx*width*offset,
                            floor+height-.077, width*.17, .055, (nx, ny), False)
        spire(tower_u, v, floor+height+.015, width*.66, peak)
        for a in [-1, 1]:
            for c in [-1, 1]:
                uu, vv = tower_u+a*width*.48, v+c*width*.48
                box(uu, vv, floor+height-.056, .014, .014, .084, 'tingzi_trim')
                spire(uu, vv, floor+height+.028, .014, .057)

    # Blue-grey dome on a low white colonnade, southeast of the three towers.
    du, dv, radius = .28, -.525, .166
    xx, yy, _ = p(du, dv, floor)
    b.cone(xx, yy, floor, radius+.022, radius+.022, .025, 'tingzi_trim', 32)
    b.cone(xx, yy, floor+.025, radius*.78, radius*.78, .182, 'tingzi_glass', 32)
    for i in range(12):
        a = i/12*math.tau
        u, v = du+radius*.90*math.cos(a), dv+radius*.90*math.sin(a)
        box(u, v, floor+.025, .025, .025, .014, 'tingzi_trim')
        beam((u, v, floor+.039), (u, v, floor+.203), .0075)
        box(u, v, floor+.194, .027, .027, .015, 'tingzi_trim')
    for h, r, thick in [(floor+.207, radius+.010, .017), (floor+.224, radius+.020, .010)]:
        b.cone(xx, yy, h, r, r, thick, 'tingzi_trim', 40)
    base, rise = floor+.234, .132
    def dome(a, t):
        return (xx+radius*math.cos(a)*math.cos(t),
                yy+radius*math.sin(a)*math.cos(t), base+rise*math.sin(t))
    def normal(a, t):
        n = (math.cos(a)*math.cos(t)/radius, math.sin(a)*math.cos(t)/radius, math.sin(t)/rise)
        length = math.sqrt(sum(k*k for k in n))
        return tuple(k/length for k in n)
    for i in range(48):
        a, c = i/48*math.tau, (i+1)/48*math.tau
        for j in range(11):
            t, s = j/12*math.pi/2, (j+1)/12*math.pi/2
            b.face([dome(a, t), dome(c, t), dome(c, s), dome(a, s)], 'tingzi_dome',
                   [normal(a, t), normal(c, t), normal(c, s), normal(a, s)])
        b.face([dome(a, 11/12*math.pi/2), dome(c, 11/12*math.pi/2), (xx, yy, base+rise)],
               'tingzi_dome', [normal(a, 11/12*math.pi/2), normal(c, 11/12*math.pi/2), (0, 0, 1)])
        if i % 4 == 0:
            for j in range(11):
                b.beam(dome(a, j/12*math.pi/2), dome(a, (j+1)/12*math.pi/2), .0018, 'tingzi_trim')
    b.beam((xx, yy, base+rise), (xx, yy, base+rise+.035), .003, 'accent')

    # Actual mapped passenger pier: triangulation handles the notched outline.
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    dock = [Vector((x+u, y+v, .337)) for u, v in PIER]
    for tri in tessellate_polygon([dock]):
        b.face([tuple(dock[a] if isinstance(a, int) else a) for a in tri], 'tingzi_deck')
    for a, c in zip(PIER, PIER[1:]+PIER[:1]):
        b.face([(x+a[0], y+a[1], .283), (x+c[0], y+c[1], .283),
                (x+c[0], y+c[1], .337), (x+a[0], y+a[1], .337)], 'tingzi_wall')
        length = math.dist(a, c)
        for i in range(max(1, math.ceil(length/.055))):
            t = i/max(1, math.ceil(length/.055))
            u, v = x+a[0]+(c[0]-a[0])*t, y+a[1]+(c[1]-a[1])*t
            b.box(u, v, .323, .008, .008, .035, 'tingzi_trim')
        b.beam((x+a[0], y+a[1], .36), (x+c[0], y+c[1], .36), .003, 'tingzi_trim')
    return floor
