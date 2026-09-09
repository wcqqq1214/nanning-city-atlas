"""Nanning's Hibiscus Hall, rebuilt from gmp's exterior views and dome section.

Reference: https://www.gmp.de/en/projects/403/nanning-international-convention-and-exhibition-center-china
The 12 folds form a continuous, concave membrane with a serrated open crown.
Dimensions remain exaggerated for the atlas; this is not a surveyed BIM model.
"""
import math


PETALS = 12
ROOF_BASE = .76
ROOF_HEIGHT = 1.30
ROOF_RADIUS = .96
ROOF_THICKNESS = .007
RADIAL_STEPS = 36
HALF_PANEL_STEPS = 3
WING_ROOF_STEPS = 12
SITE_ANGLE = math.radians(-62)


def site_distance(dx, dy):
    """Signed distance to the model's podium in the city coordinate system."""
    c, s = math.cos(SITE_ANGLE), math.sin(SITE_ANGLE)
    xx, yy = dx * c + dy * s, -dx * s + dy * c

    def rectangle(cx, cy, width, depth):
        a, b = abs(xx - cx) - width / 2, abs(yy - cy) - depth / 2
        return math.hypot(max(0, a), max(0, b)) + min(max(a, b), 0)

    return min(math.hypot(xx, yy) - 1.10,
               rectangle(0, 1.22, 3.36, 3.04),
               rectangle(0, -.99, 2.86, 1.26))


def membrane_point(petal, t, u):
    """t runs from eave to crown; u runs from left valley to right valley."""
    angle = (petal + .5) * math.tau / PETALS
    # A flared foot and almost vertical neck, not the old convex umbrella.
    radius = ROOF_RADIUS * (.285 + .715 * (1 - t) ** 2.8 + .012 * t ** 12)
    valley_radius = radius - (.062 * (1 - t) + .034 * t)
    ridge_z = ROOF_BASE + ROOF_HEIGHT * t + .095 * (1 - t) ** 8 + .10 * t ** 10
    valley_z = ROOF_BASE + ROOF_HEIGHT * t
    side_angle = angle + (1 if u >= 0 else -1) * math.pi / PETALS
    ridge = (radius * math.cos(angle), radius * math.sin(angle), ridge_z)
    valley = (valley_radius * math.cos(side_angle), valley_radius * math.sin(side_angle), valley_z)
    weight = abs(u)
    return tuple(a * (1 - weight) + c * weight for a, c in zip(ridge, valley))


def membrane_normal(petal, t, u, half):
    """Independent half-panel normals preserve both ridges and valleys."""
    epsilon = .0001
    lo, hi = (-1, 0) if half == 0 else (0, 1)
    a = membrane_point(petal, t, max(lo, u - epsilon))
    c = membrane_point(petal, t, min(hi, u + epsilon))
    d = membrane_point(petal, max(0, t - epsilon), u)
    e = membrane_point(petal, min(1, t + epsilon), u)
    du = tuple(v - w for v, w in zip(c, a))
    dt = tuple(v - w for v, w in zip(e, d))
    normal = (du[1] * dt[2] - du[2] * dt[1],
              du[2] * dt[0] - du[0] * dt[2],
              du[0] * dt[1] - du[1] * dt[0])
    length = math.sqrt(sum(v * v for v in normal))
    return tuple(v / length for v in normal)


def build_expo(b, x, y, z):
    def point(p):
        return (x + p[0], y + p[1], z + p[2])

    def wing_roof_normal(t):
        slope = .085 * math.pi / .42 * math.cos(t * math.pi)
        length = math.hypot(slope, 1)
        return (0, -slope / length, 1 / length)

    def ring(radius, level, width, height, material, segments=96):
        for i in range(segments):
            a, c = i * math.tau / segments, (i + 1) * math.tau / segments
            low = [(r * math.cos(t), r * math.sin(t), level)
                   for r, t in [(radius, a), (radius, c), (radius - width, c), (radius - width, a)]]
            high = [(px, py, pz + height) for px, py, pz in low]
            b.face([point(p) for p in high], material)
            b.face([point(low[0]), point(low[1]), point(high[1]), point(high[0])], material)
            b.face([point(low[2]), point(low[3]), point(high[3]), point(high[2])], material)

    # Low circular podium, two tiers of glazing, and a wide horizontal cornice.
    b.cone(x, y, z, 1.07, 1.07, .16, 'expo_stone', 96)
    b.cone(x, y, z + .16, .975, .975, .45, 'expo_glass', 96)
    for level in [.17, .37, .60]:
        ring(.99, level, .035, .018, 'expo_frame')
    ring(1.055, .61, .12, .125, 'expo_stone')
    for level in [.622, .655, .688, .723]:
        ring(1.060, level, .018, .007, 'expo_frame')
    for i in range(72):
        angle = i * math.tau / 72
        r = .983
        a = (r * math.cos(angle), r * math.sin(angle), .17)
        c = (a[0], a[1], .61)
        b.beam(point(a), point(c), .007 if i % 3 else .014, 'expo_frame' if i % 3 else 'roof')

    # Solid, thin membrane: adjacent petals meet without large daylight gaps.
    # Both skins are present because the top and scalloped eaves are visible.
    for petal in range(PETALS):
        for half in range(2):
            for i in range(RADIAL_STEPS):
                t, tt = i / RADIAL_STEPS, (i + 1) / RADIAL_STEPS
                for j in range(HALF_PANEL_STEPS):
                    u, uu = half - 1 + j / HALF_PANEL_STEPS, half - 1 + (j + 1) / HALF_PANEL_STEPS
                    params = [(t, u), (t, uu), (tt, uu), (tt, u)]
                    outer = [membrane_point(petal, a, c) for a, c in params]
                    normals = [membrane_normal(petal, a, c, half) for a, c in params]
                    # Radial inset joins both skins consistently at each crease.
                    inner = [(px * (1 - ROOF_THICKNESS), py * (1 - ROOF_THICKNESS), pz - ROOF_THICKNESS)
                             for px, py, pz in outer]
                    b.face([point(p) for p in outer], 'expo_membrane', normals=normals)
                    b.face([point(p) for p in reversed(inner)], 'expo_membrane',
                           normals=[tuple(-v for v in n) for n in reversed(normals)])
                    if i == 0:
                        b.face([point(inner[0]), point(inner[1]), point(outer[1]), point(outer[0])], 'expo_membrane')
                    if i == RADIAL_STEPS - 1:
                        b.face([point(outer[3]), point(outer[2]), point(inner[2]), point(inner[3])], 'expo_membrane')
        # Structural folds are narrow seams; broad white membrane carries the form.
        for i in range(RADIAL_STEPS):
            a = membrane_point(petal, i / RADIAL_STEPS, 0)
            c = membrane_point(petal, (i + 1) / RADIAL_STEPS, 0)
            b.beam(point(a), point(c), .0035, 'roof')
        a = (math.cos((petal + .5) * math.tau / PETALS) * .89,
             math.sin((petal + .5) * math.tau / PETALS) * .89, .735)
        b.beam(point(a), point(membrane_point(petal, 0, 0)), .009, 'expo_frame')
    # Match the folded cross-section: a circular disk would pierce the valleys.
    # The closure is recessed below the twelve points, as in the dome section.
    cap_level = ROOF_BASE + ROOF_HEIGHT * .82
    cap = []
    for petal in range(PETALS):
        for j in range(6):
            u = -1 + j / 3
            lo, hi = 0, 1
            for _ in range(22):
                t = (lo + hi) / 2
                if membrane_point(petal, t, u)[2] < cap_level: lo = t
                else: hi = t
            px, py, _ = membrane_point(petal, (lo + hi) / 2, u)
            cap.append(point((px * (1 - ROOF_THICKNESS), py * (1 - ROOF_THICKNESS), cap_level - ROOF_THICKNESS)))
    b.face(cap, 'expo_membrane')

    # The long low exhibition wings sit behind the rotunda, with repeating roof bays.
    # Their massing is simplified to keep the landmark readable at atlas scale.
    b.box(x, y + 1.22, z, 3.30, 3.00, .12, 'expo_stone')
    b.box(x, y + 1.60, z + .12, .54, 2.13, .48, 'expo_glass', 'roof')
    for side in [-1, 1]:
        for i in range(5):
            cy = y + .64 + i * .42
            cx = x + side * .94
            b.box(cx, cy, z + .12, 1.36, .395, .44, 'expo_glass', 'expo_stone')
            # Shallow, folded daylight roofs, not flat blocks or tall unrelated towers.
            for j in range(WING_ROOF_STEPS):
                v, vv = j / WING_ROOF_STEPS, (j + 1) / WING_ROOF_STEPS
                za = z + .57 + .085 * math.sin(v * math.pi)
                zc = z + .57 + .085 * math.sin(vv * math.pi)
                b.face([(cx - .72, cy - .21 + v * .42, za),
                        (cx + .72, cy - .21 + v * .42, za),
                        (cx + .72, cy - .21 + vv * .42, zc),
                        (cx - .72, cy - .21 + vv * .42, zc)], 'roof',
                       normals=[wing_roof_normal(t) for t in (v, v, vv, vv)])
                # Glazed end panels follow the roof profile. Without them the
                # arched roofs expose dark, empty slots when seen from the side.
                for end in [-1, 1]:
                    points = [(cx + end * .68, cy - .21 + v * .42, z + .56),
                              (cx + end * .68, cy - .21 + vv * .42, z + .56),
                              (cx + end * .68, cy - .21 + vv * .42, zc),
                              (cx + end * .68, cy - .21 + v * .42, za)]
                    b.face(points if end > 0 else list(reversed(points)), 'expo_glass')
            b.box(cx, cy - .197, z + .13, 1.36, .012, .025, 'expo_frame')
            # The reference elevations have two glazed storeys separated by a
            # continuous horizontal floor band, not a single tall blank facade.
            b.box(cx, cy, z + .32, 1.38, .403, .032, 'expo_frame')
            for j in range(7):
                b.box(cx - .60 + j * .20, cy - .200, z + .13, .009, .012, .40, 'expo_frame')
            for j in range(4):
                b.box(x + side * 1.622, cy - .15 + j * .10, z + .13,
                      .009, .007, .43, 'expo_frame')
        for j in range(9):
            b.box(x + side * 1.64, y + .48 + j * .26, z + .12, .028, .028, .48, 'roof')

    # An entrance terrace, central stair and two side staircases tie the hall to ground.
    b.box(x, y - .85, z, 2.80, .62, .145, 'expo_stone')
    for i in range(12):
        b.box(x, y - 1.12 - i * .040, z, 1.65, .043, .144 - i * .012, 'expo_stone', 'roof')
    for side in [-1, 1]:
        for i in range(12):
            b.box(x + side * 1.31, y - .98 + i * .068, z, .40, .072, .024 + i * .033, 'expo_stone', 'roof')
        for i in range(13):
            yy = y - .98 + i * .068
            hh = .11 + i * .033
            b.beam((x + side * 1.53, yy, z + hh - .08),
                   (x + side * 1.53, yy, z + hh), .004, 'expo_frame')
        b.beam((x + side * 1.53, y - .98, z + .11),
               (x + side * 1.53, y - .164, z + .506), .004, 'expo_frame')

    # Orient the primary elevation toward the western approach. The atlas position
    # remains its existing catalog point; the shape uses local architectural axes.
    # (A single transform also rotates the custom shading normals.)
    angle = SITE_ANGLE
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    b.v[:] = [(x + (px - x) * cos_a - (py - y) * sin_a,
               y + (px - x) * sin_a + (py - y) * cos_a, pz) for px, py, pz in b.v]
    b.normals[:] = [None if values is None else [
        (nx * cos_a - ny * sin_a, nx * sin_a + ny * cos_a, nz) for nx, ny, nz in values
    ] for values in b.normals]
