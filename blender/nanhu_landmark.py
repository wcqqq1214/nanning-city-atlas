"""Nanhu Park: a nine-arch bridge, palm causeways and mapped garden paths.

Plan: OSM relation 12477526 and footbridge way 243076845, recorded in
data/nanhu-plan.json. The main bridge follows the mapped ~62 m span; its
305 m reported overall length includes embankments, not extra arch openings.
Exterior: Nanning Evening Post, Song Yankang / Zhao Jinling, 2025-08-13.
Planting and small parapet motifs are illustrative, not a landscape survey.
"""
import json
import math
from pathlib import Path
from vegetation import build_tree

PLAN = json.loads((Path(__file__).resolve().parents[1]/'data/nanhu-plan.json').read_text())
MATERIAL_KEYS = ['nanhu_stone', 'nanhu_cap', 'nanhu_paving', 'nanhu_edge',
                 'nanhu_grass', 'nanhu_wood', 'nanhu_trunk', 'nanhu_palm',
                 'nanhu_leaf', 'nanhu_leaf_light', 'nanhu_leaf_dark', 'nanhu_metal']
WATER = .26
BRIDGE_END = .303
BRIDGE_CREST = .398
BRIDGE_WIDTH = .050
BRIDGE_POINTS = PLAN['causeways']['243076845']
BRIDGE_LENGTH = math.dist(*BRIDGE_POINTS)
PARK_BOUNDS = (min(p[0] for p in PLAN['park']), min(p[1] for p in PLAN['park']),
               max(p[0] for p in PLAN['park']), max(p[1] for p in PLAN['park']))


def inside_park(u, v):
    if not (PARK_BOUNDS[0] < u < PARK_BOUNDS[2] and PARK_BOUNDS[1] < v < PARK_BOUNDS[3]):
        return False
    inside = False
    for (ax, ay), (bx, by) in zip(PLAN['park'], PLAN['park'][1:]):
        if (ay > v) != (by > v) and u < (bx-ax)*(v-ay)/(by-ay)+ax:
            inside = not inside
    return inside


def bridge_deck(distance):
    t = max(0, min(1, distance/BRIDGE_LENGTH))
    return BRIDGE_END+(BRIDGE_CREST-BRIDGE_END)*math.sin(math.pi*t)**.82


def arch_intervals():
    # Nine openings, with a distinctly wider central span. All pier widths are
    # included before scaling to the actual map endpoints.
    openings = [.035, .043, .052, .062, .135, .062, .052, .043, .035]
    pier, end = .011, .01
    scale = BRIDGE_LENGTH/(sum(openings)+8*pier+2*end)
    cursor, result = end*scale, []
    for width in openings:
        result.append((cursor, cursor+width*scale))
        cursor += (width+pier)*scale
    return result


def shore_height(u, v, original):
    patch = PLAN['terrainPatch']
    west, south, east, north = patch['bounds']
    if not (west <= u <= east and south <= v <= north):
        return original
    i = min(patch['columns']-1.00001, (u-west)/(east-west)*(patch['columns']-1))
    j = min(patch['rows']-1.00001, (v-south)/(north-south)*(patch['rows']-1))
    ix, jy = int(i), int(j)
    a, c = i-ix, j-jy
    grid = patch['shoreDistance']
    distance = ((1-a)*grid[jy][ix]+a*grid[jy][ix+1])*(1-c)+((1-a)*grid[jy+1][ix]+a*grid[jy+1][ix+1])*c
    if distance >= .85:
        return original
    t = max(0, (distance-.03)/.82)
    blend = t*t*(3-2*t)
    # Grade the immediate water's edge above the display water stage. The
    # original ~95 m DEM cannot resolve a narrow, nearly level park promenade.
    return max(WATER+.025, .30*(1-blend)+original*blend)


def replaces_terrain_cell(i, j):
    patch = PLAN['terrainPatch']
    return (patch['columnRange'][0] <= i < patch['columnRange'][1] and
            patch['rowRange'][0] <= j < patch['rowRange'][1])


def build_park_terrain(batch, x, y, ground):
    for mesh in PLAN['terrainPatch']['meshes']:
        vertices = [(x+u, y+v, ground(x+u, y+v)) for u, v in mesh['points']]
        center = [sum(p[k] for p in mesh['points'])/len(mesh['points']) for k in [0, 1]]
        material = 'hillLight' if inside_park(*center) else 'ground'
        for tri in mesh['triangles']:
            batch.face([vertices[i] for i in tri], material)


def build_nanhu(b, x, y, ground, trees):
    def p(u, v, h):
        return (x+u, y+v, h)

    def face(points, key):
        b.face([p(*q) for q in points], key)

    def beam(a, c, radius, key):
        b.beam(p(*a), p(*c), radius, key)

    def cone(u, v, h, r, rr, rise, key, segments=8):
        b.cone(x+u, y+v, h, r, rr, rise, key, segments)

    def floor(u, v):
        return max(WATER+.028, ground(x+u, y+v))

    # Reuse the city crown at the park's smaller scale and original positions.
    for index, (u, v, r) in enumerate(PLAN['trees']):
        h = floor(u, v)
        color = ['nanhu_leaf','nanhu_leaf_light','nanhu_leaf_dark'][index%3]
        build_tree(trees,x+u,y+v,h,r,color,crown_height=.21,crown_rise=r*.95,
                   trunk_radius=.010,trunk_height=.16,trunk_color='nanhu_trunk')

    def palm(u, v, h, seed):
        rise = .28+(seed%5)*.016
        lean = .012*math.sin(seed*1.7)
        trees.cone(x+u,y+v,h,.009,.006,rise,'nanhu_trunk',4)
        # Fronds are folded ribbons with a central ridge and a drooping tip.
        for leaf in range(9):
            a = (leaf/9+seed*.071)*math.tau
            reach = .115+(leaf%3)*.012
            def q(t, side):
                radius = reach*t
                halfwidth = .018*math.sin(math.pi*t)**.7 if 0 < t < 1 else 0
                z = h+rise+.08*math.sin(math.pi*t*.9)-.065*t*t
                return (u+lean+radius*math.cos(a)-side*halfwidth*math.sin(a),
                        v+radius*math.sin(a)+side*halfwidth*math.cos(a), z-(.009*math.sin(math.pi*t) if side else 0))
            for j in range(3):
                t, tt = j/3, (j+1)/3
                for side in [-1, 1]:
                    pts = [q(t, 0), q(t, side), q(tt, side), q(tt, 0)]
                    if j == 0: pts = [pts[0], pts[2], pts[3]]
                    elif j == 2: pts = pts[:3]
                    trees.face([p(*q) for q in pts],'nanhu_palm' if (leaf+seed)%3 else 'nanhu_leaf_light')
        trees.cone(x+u+lean,y+v,h+rise-.018,.018,.010,.026,'nanhu_palm',4)

    # Map-derived paths stay strictly landward of the existing water polygons.
    # A small offset keeps their paving clear of the coarse display DEM.
    for kind, material in [('paths', 'nanhu_paving'), ('square', 'nanhu_edge')]:
        for mesh in PLAN[kind]:
            vertices = [(u, v, floor(u, v)+(.037 if kind == 'paths' else .043)) for u, v in mesh['points']]
            for tri in mesh['triangles']:
                face([vertices[i] for i in tri], material)

    a, c = BRIDGE_POINTS
    tx, ty = (c[0]-a[0])/BRIDGE_LENGTH, (c[1]-a[1])/BRIDGE_LENGTH
    nx, ny = -ty, tx
    def bp(distance, across, h):
        return (a[0]+tx*distance+nx*across, a[1]+ty*distance+ny*across, h)

    intervals = arch_intervals()
    bottom = WATER-.035
    # Solid piers separate open arch voids; each vault has a real soffit.
    solids = [(0, intervals[0][0])]+[(aa[1], cc[0]) for aa, cc in zip(intervals, intervals[1:])]+[(intervals[-1][1], BRIDGE_LENGTH)]
    for start, end in solids:
        for side in [-1, 1]:
            face([bp(start, side*BRIDGE_WIDTH/2, bottom), bp(end, side*BRIDGE_WIDTH/2, bottom),
                  bp(end, side*BRIDGE_WIDTH/2, bridge_deck(end)), bp(start, side*BRIDGE_WIDTH/2, bridge_deck(start))], 'nanhu_stone')
        for d in [start, end]:
            face([bp(d, -BRIDGE_WIDTH/2, bottom), bp(d, BRIDGE_WIDTH/2, bottom),
                  bp(d, BRIDGE_WIDTH/2, bridge_deck(d)), bp(d, -BRIDGE_WIDTH/2, bridge_deck(d))], 'nanhu_stone')
    for index, (start, end) in enumerate(intervals):
        center, radius = (start+end)/2, (end-start)/2
        crown = bridge_deck(center)-.020
        spring = WATER-.005
        def arch(d):
            return spring+(crown-spring)*math.sqrt(max(0, 1-((d-center)/radius)**2))
        count = 24 if index == 4 else 16
        for j in range(count):
            d, dd = start+(end-start)*j/count, start+(end-start)*(j+1)/count
            h, hh = arch(d), arch(dd)
            for side in [-1, 1]:
                face([bp(d, side*BRIDGE_WIDTH/2, h), bp(dd, side*BRIDGE_WIDTH/2, hh),
                      bp(dd, side*BRIDGE_WIDTH/2, bridge_deck(dd)), bp(d, side*BRIDGE_WIDTH/2, bridge_deck(d))], 'nanhu_stone')
                # Pale voussoir strip defines each arch without painting a hole.
                across = side*(BRIDGE_WIDTH/2+.0007)
                face([bp(d, across, h), bp(dd, across, hh), bp(dd, across, hh+.004), bp(d, across, h+.004)], 'nanhu_cap')
            face([bp(d, -BRIDGE_WIDTH/2, h), bp(dd, -BRIDGE_WIDTH/2, hh),
                  bp(dd, BRIDGE_WIDTH/2, hh), bp(d, BRIDGE_WIDTH/2, h)], 'nanhu_edge')

    # Closely spaced deck strips and transverse joints follow the gentle rise.
    for j in range(64):
        d, dd = BRIDGE_LENGTH*j/64, BRIDGE_LENGTH*(j+1)/64
        face([bp(d, -.026, bridge_deck(d)+.003), bp(dd, -.026, bridge_deck(dd)+.003),
              bp(dd, .026, bridge_deck(dd)+.003), bp(d, .026, bridge_deck(d)+.003)], 'nanhu_paving')
        if j % 2 == 0:
            beam(bp(d, -.023, bridge_deck(d)+.004), bp(d, .023, bridge_deck(d)+.004), .00065, 'nanhu_edge')
    rail_count = 30
    for side in [-1, 1]:
        across = side*.0255
        for j in range(rail_count+1):
            d = BRIDGE_LENGTH*j/rail_count
            level = bridge_deck(d)
            beam(bp(d, across, level), bp(d, across, level+.023), .0021, 'nanhu_cap')
            u, v, h = bp(d, across, level+.023)
            cone(u, v, h, .0037, .0027, .0045, 'nanhu_cap', 8)
        for j in range(rail_count):
            d, dd = BRIDGE_LENGTH*j/rail_count, BRIDGE_LENGTH*(j+1)/rail_count
            for h, radius in [(.005, .0018), (.020, .0023)]:
                beam(bp(d, across, bridge_deck(d)+h), bp(dd, across, bridge_deck(dd)+h), radius, 'nanhu_cap')
            # Open diamond / lotus-inspired panels, kept coarse enough to survive
            # mesh compression while retaining the real balustrade's rhythm.
            m = (d+dd)/2
            for e, z in [(d+.003, .012), (dd-.003, .012)]:
                beam(bp(e, across, bridge_deck(e)+z), bp(m, across, bridge_deck(m)+.006), .0012, 'nanhu_cap')
                beam(bp(e, across, bridge_deck(e)+z), bp(m, across, bridge_deck(m)+.019), .0012, 'nanhu_cap')

    def line_samples(points, spacing):
        lengths = [math.dist(a, c) for a, c in zip(points, points[1:])]
        total = sum(lengths)
        count = max(1, math.ceil(total/spacing))
        result = []
        for i in range(count+1):
            distance, cursor = total*i/count, 0
            for j, length in enumerate(lengths):
                if distance <= cursor+length+.000001:
                    t = min(1, (distance-cursor)/length)
                    a, c = points[j:j+2]
                    tx, ty = (c[0]-a[0])/length, (c[1]-a[1])/length
                    result.append((a[0]+t*(c[0]-a[0]), a[1]+t*(c[1]-a[1]), -ty, tx, distance/total))
                    break
                cursor += length
        return result

    for key in ['243076844', '243076846']:
        points = PLAN['causeways'][key]
        # Both OSM ways run from the bank to the arch bridge.
        bank = floor(*points[0])+.022
        def level(t):
            return bank*(1-t)+BRIDGE_END*t
        samples = line_samples(points, .045)
        for aa, cc in zip(samples, samples[1:]):
            u, v, nx, ny, t = aa
            uu, vv, nnx, nny, tt = cc
            def cp(sample, across, h):
                x, y, nx, ny, t = sample
                return (x+nx*across, y+ny*across, h)
            face([cp(aa, -.033, level(t)), cp(cc, -.033, level(tt)),
                  cp(cc, .033, level(tt)), cp(aa, .033, level(t))], 'nanhu_paving')
            for side in [-1, 1]:
                face([cp(aa, side*.034, level(t)-.001), cp(cc, side*.034, level(tt)-.001),
                      cp(cc, side*.095, level(tt)-.011), cp(aa, side*.095, level(t)-.011)], 'nanhu_grass')
                face([cp(aa, side*.095, level(t)-.011), cp(cc, side*.095, level(tt)-.011),
                      cp(cc, side*.132, WATER-.009), cp(aa, side*.132, WATER-.009)], 'nanhu_grass')
                beam(cp(aa, side*.033, level(t)+.001), cp(cc, side*.033, level(tt)+.001), .003, 'nanhu_edge')
        for i, (u, v, nx, ny, t) in enumerate(line_samples(points, .155)[1:-1]):
            for side in [-1, 1]:
                palm(u+side*nx*.075, v+side*ny*.075, level(t)-.008, i+(side+1)*7)
            if i % 3 == 1:
                u, v = u+nx*.040, v+ny*.040
                beam((u, v, level(t)), (u, v, level(t)+.040), .0018, 'nanhu_metal')
                cone(u, v, level(t)+.037, .006, .0045, .007, 'nanhu_cap', 8)

    # Four actual mapped waterside footbridges / boardwalks, including the
    # northeast zigzag walk. Decks and rails follow their original polylines.
    for walk in PLAN['boardwalks']:
        pts = walk['points']
        level = max(WATER+.045, min(floor(*pts[0]), floor(*pts[-1]))+.016)
        samples = line_samples(pts, .040)
        for aa, cc in zip(samples, samples[1:]):
            u, v, nx, ny, _ = aa
            uu, vv, nnx, nny, _ = cc
            face([(u-nx*.015, v-ny*.015, level), (uu-nnx*.015, vv-nny*.015, level),
                  (uu+nnx*.015, vv+nny*.015, level), (u+nx*.015, v+ny*.015, level)], 'nanhu_wood')
            for side in [-1, 1]:
                beam((u+side*nx*.014, v+side*ny*.014, level+.018),
                     (uu+side*nnx*.014, vv+side*nny*.014, level+.018), .0015, 'nanhu_edge')
        for u, v, nx, ny, _ in line_samples(pts, .080):
            for side in [-1, 1]:
                beam((u+side*nx*.014, v+side*ny*.014, WATER-.012),
                     (u+side*nx*.014, v+side*ny*.014, level+.020), .0018, 'nanhu_edge')
    return BRIDGE_CREST
