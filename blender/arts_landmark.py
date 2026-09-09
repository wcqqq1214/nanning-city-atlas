"""Guangxi Culture & Arts Center: three halls under a continuous louver canopy.

Exterior, masterplan and sections: https://www.gmp.de/en/projects/3231/guangxi-culture-arts-center
Canopy control points derive from OSM way 819620330. The hall profiles, facade
and podium are independently modelled approximations, enlarged for the atlas.
Local u/v axes follow the parallel aluminum fins; world X/Y are east/north.
"""
import math


DISPLAY_SCALE = 1.2
SITE_ANGLE = math.radians(-20)
PODIUM = .038
CANOPY = .205
FIN_PITCH = .034
FIN_WIDTH = .008
FIN_DEPTH = .024
PROFILE_POWER = 2.6
HALLS = (
    # u, v, half-width, half-length, rise above canopy, crest bias
    (-.3801, -.2128, .435, .495, .305, .18),  # southwest opera house
    (.6716, -.2664, .305, .365, .240, -.12),  # eastern concert hall
    (.2057, .6921, .275, .315, .205, .10),    # northern multipurpose hall
)
CANOPY_OUTLINE = (
    (.0625, -.8024), (.2142, -.7745), (.7307, -.8092),
    (.8986, -.7716), (1.0538, -.6506), (1.1234, -.5198),
    (1.1641, -.2137), (1.1406, -.0984), (1.0898, .0070),
    (.8660, .2834), (.7828, .3996), (.7212, .5575),
    (.5890, .9966), (.5048, 1.0831), (.3905, 1.1236),
    (.0372, 1.1122), (-.0587, 1.0538), (-.1213, .9841),
    (-.2152, .7273), (-.2976, .6153), (-.4345, .5245),
    (-.7707, .3376), (-.8802, .2039), (-.9258, .0393),
    (-.9488, -.4127), (-.9031, -.5542), (-.8329, -.6928),
    (-.7149, -.8139), (-.6085, -.8806), (-.4665, -.9168),
    (-.2402, -.9106), (-.0845, -.8715),
)


def outline(samples=5):
    """Closed Catmull-Rom curve through the mapped canopy control points."""
    result = []
    for i in range(len(CANOPY_OUTLINE)):
        points = [CANOPY_OUTLINE[(i + k) % len(CANOPY_OUTLINE)]
                  for k in (-1, 0, 1, 2)]
        for j in range(samples):
            t = j / samples
            result.append(tuple(.5 * (2*b + (-a+c)*t + (2*a-5*b+4*c-d)*t*t
                                      + (-a+3*b-3*c+d)*t*t*t)
                                for a, b, c, d in zip(*points)))
    return result


def intervals(points, u):
    """Intersect a louver plane with the possibly concave canopy perimeter."""
    hits = []
    for a, b in zip(points, points[1:] + points[:1]):
        if min(a[0], b[0]) <= u < max(a[0], b[0]):
            t = (u-a[0]) / (b[0]-a[0])
            hits.append(a[1] + t*(b[1]-a[1]))
    hits.sort()
    return list(zip(hits[::2], hits[1::2]))


def canopy_level(u, v):
    return CANOPY + .009*math.sin(u*2.2) + .007*math.cos(v*2.8)


def hall_level(hall, u, v):
    cx, cy, rx, ry, rise, bias = hall
    q = abs((u-cx)/rx)**PROFILE_POWER + abs((v-cy)/ry)**PROFILE_POWER
    return canopy_level(u, v) + rise*max(0, 1-q)**.58*(1+bias*(v-cy)/ry)


def roof_level(u, v):
    return max(hall_level(h, u, v) for h in HALLS)


def roof_normal(u, v):
    delta = .0001
    du = (roof_level(u+delta, v)-roof_level(u-delta, v))/(2*delta)
    dv = (roof_level(u, v+delta)-roof_level(u, v-delta))/(2*delta)
    length = math.sqrt(du*du+dv*dv+1)
    return (-du/length, -dv/length, 1/length)


def hall_outline(hall, angle, radius=1):
    cx, cy, rx, ry, _, _ = hall
    c, s = math.cos(angle), math.sin(angle)
    return (cx + rx*math.copysign(abs(c)**(2/PROFILE_POWER), c)*radius,
            cy + ry*math.copysign(abs(s)**(2/PROFILE_POWER), s)*radius)


def build_arts(b, x, y, z, ground=None):
    boundary = outline()
    cos_a, sin_a = math.cos(SITE_ANGLE), math.sin(SITE_ANGLE)

    def point(u, v, h):
        return (x + DISPLAY_SCALE*(u*cos_a-v*sin_a),
                y + DISPLAY_SCALE*(u*sin_a+v*cos_a), z + DISPLAY_SCALE*h)

    if ground is not None:
        # A level podium with a terrain-following foundation avoids floating
        # above the coarse display DEM without altering the river or terrain.
        z = max(z, max(ground(*point(u*1.12, v*1.12, 0)[:2])
                       for u, v in boundary) + .025)

    def normal(n):
        return (n[0]*cos_a-n[1]*sin_a, n[0]*sin_a+n[1]*cos_a, n[2])

    def face(vertices, key, smooth=False):
        b.face([point(*p) for p in vertices], key,
               normals=[normal(roof_normal(p[0], p[1])) for p in vertices] if smooth else None)

    def beam(a, c, radius, key='arts_frame'):
        b.beam(point(*a), point(*c), radius*DISPLAY_SCALE, key)

    def prism(lower, upper, key):
        face(list(reversed(lower)), key)
        face(upper, key)
        for i in range(len(lower)):
            j = (i+1) % len(lower)
            face([lower[i], lower[j], upper[j], upper[i]], key)

    # The shared stone podium follows the three-lobed plan. Shallow continuous
    # stair terraces replace the old rectangular slab and unrelated gold blocks.
    for i in range(12):
        scale = 1.12-i*.010
        lower = []
        for u, v in boundary:
            h = i*.003
            if i == 0:
                h = ((ground(*point(u*scale, v*scale, 0)[:2])-z-.025)/DISPLAY_SCALE
                     if ground is not None else -.070)
            lower.append((u*scale, v*scale, h))
        upper = [(u*scale, v*scale, (i+1)*.003) for u, v in boundary]
        prism(lower, upper, 'arts_stone')

    # Thin, subtly warped canopy skin. Its underside and smooth perimeter are
    # closed; the exposed slats above it continue through all three upper shells.
    lower = [(u, v, canopy_level(u, v)-.016) for u, v in boundary]
    upper = [(u, v, canopy_level(u, v)-.008) for u, v in boundary]
    # A star-shaped fan provides a stable tessellation of the concave roof.
    center = (.11, .05)
    for i in range(len(boundary)):
        j = (i+1) % len(boundary)
        for ring, flip in [(upper, False), (lower, True)]:
            vertices = [(*center, canopy_level(*center)-(.016 if flip else .008)), ring[i], ring[j]]
            face(list(reversed(vertices)) if flip else vertices, 'arts_soffit')
        face([lower[i], lower[j], upper[j], upper[i]], 'arts_white')

    # Recessed glazed foyers and the smooth weather skin below each louver shell.
    for hall in HALLS:
        segments, rings = 96, 18
        perimeter = [hall_outline(hall, i*math.tau/segments) for i in range(segments)]
        for i, (u, v) in enumerate(perimeter):
            uu, vv = perimeter[(i+1) % segments]
            lower = [(hall[0]+(a-hall[0])*.91, hall[1]+(c-hall[1])*.91, PODIUM)
                     for a, c in [(u, v), (uu, vv)]]
            high = [(a, c, canopy_level(a, c)-.014) for a, c in [(u, v), (uu, vv)]]
            face([lower[0], lower[1], high[1], high[0]], 'arts_glass')
            if i % 2 == 0:
                beam(lower[0], high[0], .0016)
            for t in (.06, .53, .97):
                ends = [tuple(a*(1-t)+c*t for a, c in zip(lo, hi)) for lo, hi in zip(lower, high)]
                beam(*ends, .0011)
        for k in range(rings):
            for i in range(segments):
                params = [(k/rings, i), ((k+1)/rings, i),
                          ((k+1)/rings, i+1), (k/rings, i+1)]
                vertices = []
                for radius, index in params:
                    u, v = hall_outline(hall, index*math.tau/segments, radius)
                    vertices.append((u, v, hall_level(hall, u, v)-.007))
                # A triangle fan at the crest avoids collapsed central quads.
                face(vertices[:3] if k == 0 else vertices, 'arts_shell', smooth=True)

    # Every fin is an actual thin solid, not a stripe texture or a low-sided cone.
    # The side faces remain flat aluminum panels; the top strip follows the curve.
    first = math.ceil(min(p[0] for p in boundary)/FIN_PITCH)
    last = math.floor(max(p[0] for p in boundary)/FIN_PITCH)
    for index in range(first, last+1):
        u = index*FIN_PITCH
        for start, end in intervals(boundary, u):
            count = max(2, math.ceil((end-start)/.030))
            for k in range(count):
                v, vv = start+(end-start)*k/count, start+(end-start)*(k+1)/count
                footprint = [(u-FIN_WIDTH/2, v), (u+FIN_WIDTH/2, v),
                             (u+FIN_WIDTH/2, vv), (u-FIN_WIDTH/2, vv)]
                top = [(a, c, roof_level(a, c)+FIN_DEPTH) for a, c in footprint]
                bottom = [(a, c, roof_level(a, c)-.003) for a, c in footprint]
                face(top, 'arts_white', smooth=True)
                face(list(reversed(bottom)), 'arts_white')
                if k == 0:
                    face([bottom[0], bottom[1], top[1], top[0]], 'arts_white')
                if k == count-1:
                    face([bottom[3], top[3], top[2], bottom[2]], 'arts_white')
                for a, c in [(3, 0), (1, 2)]:
                    face([bottom[a], bottom[c], top[c], top[a]], 'arts_white')
            # Inclined louver feet frame the foyers below the shared canopy.
            for hall in HALLS:
                cx, cy, rx, ry, _, _ = hall
                q = abs((u-cx)/rx)**PROFILE_POWER
                if q >= .985:
                    continue
                half = ry*(1-q)**(1/PROFILE_POWER)
                for side in (-1, 1):
                    v = cy+side*half
                    foot = v-side*.052
                    width, depth = FIN_WIDTH*.70, .016
                    lower = [(a, c, PODIUM) for a, c in
                             [(u-width, foot-depth), (u+width, foot-depth),
                              (u+width, foot+depth), (u-width, foot+depth)]]
                    upper = [(a, c, canopy_level(u, v)-.010) for a, c in
                             [(u-width, v-depth), (u+width, v-depth),
                              (u+width, v+depth), (u-width, v+depth)]]
                    prism(lower, upper, 'arts_white')

    # Transverse underside members, sparse enough to stay readable at this scale.
    for index in range(-9, 12):
        v = index*.09
        swapped = [(c, a) for a, c in boundary]
        for start, end in intervals(swapped, v):
            beam((start, v, canopy_level(start, v)-.020),
                 (end, v, canopy_level(end, v)-.020), .0025, 'arts_soffit')

    # Glazed entry doors and terrace handrails are grouped at the three foyers.
    for hall in HALLS:
        cx, cy, rx, ry, _, _ = hall
        v = cy-ry*.94
        for side in (-1, 1):
            uu = cx+side*.043
            face([(uu-.035, v, PODIUM), (uu+.035, v, PODIUM),
                  (uu+.035, v, PODIUM+.087), (uu-.035, v, PODIUM+.087)], 'arts_glass')
            beam((uu+side*.009, v-.002, PODIUM+.033),
                 (uu+side*.009, v-.002, PODIUM+.059), .0013)
        for i in range(9):
            angle = math.pi*1.20+i*math.pi*.60/8
            a, c = hall_outline(hall, angle, 1.075)
            beam((a, c, PODIUM), (a, c, PODIUM+.030), .0012)
            if i:
                beam(previous, (a, c, PODIUM+.030), .0012)
            previous = (a, c, PODIUM+.030)
