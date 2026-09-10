"""Terrain-aware Qingxiang urban viaduct and its connected ramps.

Shared structural geometry survives the mobile profile. Small fittings are
batched separately; no external textures, Blender modifiers or runtime LOD.
"""
import bisect
from collections import defaultdict
from functools import lru_cache
import heapq
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / 'data/viaduct-plan.json').read_text())
MATERIAL_KEYS = ['viaduct_concrete', 'viaduct_soffit', 'viaduct_asphalt', 'viaduct_line', 'viaduct_metal']
REMOVED_TREES = set(PLAN['removedTrees'])


def smooth(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


class Path:
    def __init__(self, points):
        self.points = points
        self.lengths = [0]
        for a, b in zip(points, points[1:]):
            self.lengths.append(self.lengths[-1] + math.dist(a, b))
        self.length = self.lengths[-1]

    def section(self, s):
        s = max(0, min(self.length, s))
        i = max(0, min(len(self.points) - 2, bisect.bisect_right(self.lengths, s) - 1))
        return i, (s - self.lengths[i]) / (self.lengths[i + 1] - self.lengths[i])

    def at(self, s, offset=0, z=0):
        i, t = self.section(s)
        a, b = self.points[i:i + 2]
        # Averaged station tangents give adjacent sections identical edge
        # vertices, avoiding cracks at every bend in the original OSM polyline.
        def normal(j):
            p, q = self.points[max(0, j - 1)], self.points[min(len(self.points) - 1, j + 1)]
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dy)
            return -dy / length, dx / length
        na, nb = normal(i), normal(i + 1)
        nx, ny = na[0] * (1 - t) + nb[0] * t, na[1] * (1 - t) + nb[1] * t
        length = math.hypot(nx, ny)
        return (a[0] * (1 - t) + b[0] * t + nx / length * offset,
                a[1] * (1 - t) + b[1] * t + ny / length * offset, z)

    @lru_cache(maxsize=40000)
    def nearest(self, x, y):
        best = (float('inf'), 0)
        for i, (a, b) in enumerate(zip(self.points, self.points[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
            distance = math.hypot(x - a[0] - dx * t, y - a[1] - dy * t)
            if distance < best[0]:
                best = distance, self.lengths[i] + (self.lengths[i + 1] - self.lengths[i]) * t
        return best


class Viaduct:
    def __init__(self, height, surface):
        self.height, self.surface = height, surface
        self.main = Path(PLAN['main']['points'])
        self.ramps = {r['id']: (r, Path(r['points'])) for r in PLAN['ramps']}
        self.paths = {'main': self.main, **{key: path for key, (_, path) in self.ramps.items()}}
        source = json.loads((ROOT / 'data/viaduct-source.json').read_text())
        ways = {e['id']: e for e in source['elements']}
        # A node graph gives every split/merge one elevation. Source bridge
        # flags set clearance; ground sections remain embankments, not viaducts.
        graph, required, keys = defaultdict(list), {}, {}
        for identity, path in self.paths.items():
            route = self.ramps.get(identity, ({},))[0]
            samples = []
            for j, s in enumerate(path.lengths):
                endpoint = 0 if j == 0 else 1 if j == len(path.lengths) - 1 else None
                key = ('node', route['nodes'][endpoint]) if identity != 'main' and endpoint is not None else (identity, j)
                samples.append(key)
                w = self.width(identity, s)
                floor = max(surface(*path.at(s, offset)[:2], mobile)
                            for offset in [-w, 0, w] for mobile in [False, True])
                floor = max(floor, height(*path.at(s)[:2]))
                clearance = .22 * max(1, route.get('layer', 1)) if self.is_bridge(identity, s) else .065
                if route.get('tunnel'):
                    clearance = .005
                required[key] = max(required.get(key, -1000), floor + clearance)
                if endpoint is not None and str(endpoint) in route.get('boundaryJoints', {}):
                    if any(ways[i]['tags'].get('bridge', 'no') != 'no' for i in route['boundaryJoints'][str(endpoint)]):
                        required[key] = max(required[key], 1.1)
            keys[identity] = samples
            for j, (a, b) in enumerate(zip(samples, samples[1:])):
                cost = .12 * (path.lengths[j + 1] - path.lengths[j])
                graph[a].append((b, cost)); graph[b].append((a, cost))
        self.merge_ranges = {}
        for identity, (route, path) in self.ramps.items():
            ranges = []
            for endpoint, binding in route['mainJoints'].items():
                end = int(endpoint)
                join_s = binding['distance']
                node = keys[identity][0 if end == 0 else -1]
                index, _ = self.main.section(join_s)
                for j in [index, index + 1]:
                    main_key = keys['main'][j]
                    cost = .12 * abs(self.main.lengths[j] - join_s)
                    graph[node].append((main_key, cost)); graph[main_key].append((node, cost))
                stations = path.lengths if end == 0 else path.lengths[::-1]
                for s in stations:
                    distance, main_s = self.main.nearest(*path.at(s)[:2])
                    if distance > self.width('main', main_s) + self.width(identity, s) + .004:
                        break
                ranges.append((0 if end == 0 else s, s if end == 0 else path.length, binding['side']))
            self.merge_ranges[identity] = ranges
            for j, s in enumerate(path.lengths):
                if not any(a <= s <= b for a, b, _ in ranges):
                    continue
                main_s = self.main.nearest(*path.at(s)[:2])[1]
                index, t = self.main.section(main_s)
                main_key = keys['main'][index if t < .5 else index + 1]
                node = keys[identity][j]
                graph[node].append((main_key, 0)); graph[main_key].append((node, 0))
        # The maximum-source shortest-path envelope raises valleys only as much
        # as needed to bound grade across *all* connected ramp pieces.
        queue = [(-value, key) for key, value in required.items()]
        heapq.heapify(queue)
        while queue:
            negative, key = heapq.heappop(queue)
            value = -negative
            if value < required[key] - 1e-10:
                continue
            for neighbour, cost in graph[key]:
                candidate = value - cost
                if candidate > required[neighbour] + 1e-10:
                    required[neighbour] = candidate
                    heapq.heappush(queue, (-candidate, neighbour))
        self.profiles = {identity: [required[k] for k in samples] for identity, samples in keys.items()}
        self.levels = self.profiles['main']
        self.deck = max(self.levels)
        self.landing_lifts = []
        # At a boundary the retained street and the new route use the same
        # smooth lift; otherwise a coarse terrain cell can bury their junction.
        for identity, (route, path) in self.ramps.items():
            for endpoint in route['boundaryJoints']:
                j = 0 if endpoint == '0' else -1
                x, y = path.points[j]
                lift = max(0, self.profiles[identity][j] - height(x, y) - .065)
                self.landing_lifts.append((x, y, lift))
        for j in [0, -1]:
            x, y = self.main.points[j]
            self.landing_lifts.append((x, y, max(0, self.levels[j] - height(x, y) - .065)))
        for boundary in PLAN['main'].get('boundaries', []):
            x, y = boundary['point']
            s = self.main.nearest(x, y)[1]
            self.landing_lifts.append((x, y, max(0, self.level('main', s) - height(x, y) - .065)))
        self.sections = {'main': self.render_sections('main')}
        for identity in self.ramps:
            self.sections[identity] = self.render_sections(identity)
        self.piers = []
        for group in PLAN['piers']:
            identity = group['path']
            path = self.paths[identity]
            for s in group['distances']:
                x, y, _ = path.at(s)
                if not self.is_bridge(identity, s):
                    continue
                if identity != 'main' and self.main.nearest(x, y)[0] < .19:
                    continue
                bottom = max(surface(x, y, False) + .072, surface(x, y, True) + .072,
                             self.road_level(x, y) + .007)
                top = self.render_level(identity, s) - .035
                obstructs_lower_deck = False
                for other, other_path in self.paths.items():
                    if other == identity:
                        continue
                    distance, along = other_path.nearest(x, y)
                    if distance < self.width(other, along) + .05 and self.render_level(other, along) < top + .07:
                        obstructs_lower_deck = True
                        break
                if obstructs_lower_deck:
                    continue
                if top - bottom > .075:
                    self.piers.append({'path': identity, 's': s, 'x': x, 'y': y, 'bottom': bottom, 'top': top})

    def is_bridge(self, identity, s):
        if identity == 'main':
            i, t = self.main.section(s)
            return PLAN['main']['bridge'][i if t < .5 else i + 1]
        return self.ramps[identity][0]['bridge']

    def merge_at(self, identity, s):
        return any(a <= s <= b for a, b, _ in self.merge_ranges.get(identity, []))

    def road_level(self, x, y):
        radius = PLAN['assumptions']['landingBlendMeters'] / 100
        weighted, weights, fade = 0., 0., 0.
        for px, py, value in self.landing_lifts:
            distance = math.hypot(x - px, y - py)
            if distance >= radius:
                continue
            if distance < .00001:
                return self.height(x, y) + .065 + value
            falloff = smooth(1 - distance / radius)
            weight = falloff / (distance * distance)
            weighted += value * weight
            weights += weight
            fade = max(fade, falloff)
        lift = weighted / weights * fade if weights else 0
        return self.height(x, y) + .065 + lift

    def render_level(self, identity, s):
        stations = self.sections[identity]
        i = max(0, min(len(stations) - 2, bisect.bisect_right(stations, s) - 1))
        a, b = stations[i:i + 2]
        t = max(0, min(1, (s - a) / (b - a)))
        return self.level(identity, a) * (1 - t) + self.level(identity, b) * t

    def render_sections(self, identity):
        """Retain turns, grades and merge openings without tessellating straight spans."""
        path = self.paths[identity]
        stations = path.lengths
        edges = [[path.at(s, side * self.width(identity, s), self.level(identity, s))
                  for side in [-1, 1]] for s in stations]
        required = {0, len(stations) - 1}
        if identity == 'main':
            openings = [tuple(self.barrier_open((a + b) / 2, side) for side in [-1, 1])
                        for a, b in zip(stations, stations[1:])]
            required.update(i for i in range(1, len(openings)) if openings[i] != openings[i - 1])
        else:
            for a, b, _ in self.merge_ranges[identity]:
                for s in [a, b]:
                    index = bisect.bisect_left(stations, s)
                    required.update(range(max(0, index - 1), min(len(stations), index + 2)))
        tolerance = PLAN['assumptions']['geometryToleranceMeters'] / 100
        max_span = PLAN['assumptions']['geometryMaxSpanMeters'] / 100

        def reduce(a, b):
            if b - a <= 1:
                return
            def error(i):
                t = (stations[i] - stations[a]) / (stations[b] - stations[a])
                return max(math.dist(edges[i][side], tuple(x * (1 - t) + y * t
                               for x, y in zip(edges[a][side], edges[b][side]))) for side in [0, 1])
            split = max(range(a + 1, b), key=error)
            if error(split) <= tolerance:
                if stations[b] - stations[a] <= max_span:
                    return
                split = (a + b) // 2
            required.add(split)
            reduce(a, split)
            reduce(split, b)

        initial = sorted(required)
        for a, b in zip(initial, initial[1:]):
            reduce(a, b)
        return [stations[i] for i in sorted(required)]

    def width(self, identity, s):
        if identity == 'main':
            i, t = self.main.section(s)
            a, b = PLAN['main']['halfWidths'][i:i + 2]
            return a * (1 - t) + b * t
        return .073 / 2

    def level(self, identity, s):
        path = self.paths[identity]
        i, t = path.section(s)
        value = self.profiles[identity][i] * (1 - t) + self.profiles[identity][i + 1] * t
        return value

    def barrier_open(self, s, side):
        x, y, _ = self.main.at(s, side * (self.width('main', s) - .004))
        for identity, (_, path) in self.ramps.items():
            distance, along = path.nearest(x, y)
            if distance < .047 and any(a - .25 <= along <= b + .25 and ramp_side == side
                                       for a, b, ramp_side in self.merge_ranges[identity]):
                return True
        return False


def strip(batch, path, a, b, lo, hi, z1, z2, key):
    batch.face([path.at(a, lo, z1), path.at(b, lo, z2),
                path.at(b, hi, z2), path.at(a, hi, z1)], key)


def build_structure(batch, network):
    for identity, path in network.paths.items():
        stations = network.sections[identity]
        for a, b in zip(stations, stations[1:]):
            rings = []
            for s in [a, b]:
                w, z = network.width(identity, s), network.level(identity, s)
                rings.append([path.at(s, u, z + h) for u, h in
                              [(-w, -.004), (-w, -.015), (-w * .68, -.035),
                               (w * .68, -.035), (w, -.015), (w, -.004)]])
            for i in range(6):
                j = (i + 1) % 6
                batch.face([rings[0][i], rings[0][j], rings[1][j], rings[1][i]],
                           'viaduct_soffit' if i in [1, 2, 3] else 'viaduct_concrete')
            wa, wb = network.width(identity, a) - .012, network.width(identity, b) - .012
            za, zb = network.level(identity, a), network.level(identity, b)
            batch.face([path.at(a, -wa, za), path.at(b, -wb, zb),
                        path.at(b, wb, zb), path.at(a, wa, za)], 'viaduct_asphalt')
            for side in [-1, 1]:
                if identity == 'main' and network.barrier_open((a + b) / 2, side):
                    continue
                # Ramp barriers begin at the edge of the shared merge surface.
                if identity != 'main' and network.merge_at(identity, (a + b) / 2):
                    continue
                rails = []
                for s in [a, b]:
                    w, z = network.width(identity, s), network.level(identity, s)
                    rails.append([path.at(s, side * (w - offset), z + h)
                                  for offset, h in [(0, 0), (.009, 0), (.007, .014), (.002, .014)]])
                for i in range(4):
                    j = (i + 1) % 4
                    face = [rails[0][i], rails[1][i], rails[1][j], rails[0][j]]
                    batch.face(face if side > 0 else face[::-1], 'viaduct_concrete')
            if identity == 'main':
                strip(batch, path, a, b, -.006, .006, za + .013, zb + .013, 'viaduct_concrete')
                for side in [-1, 1]:
                    batch.face([path.at(a, side * .006, za), path.at(b, side * .006, zb),
                                path.at(b, side * .006, zb + .013), path.at(a, side * .006, za + .013)], 'viaduct_concrete')
        for s, reverse in [(0, True), (path.length, False)]:
            w, z = network.width(identity, s), network.level(identity, s)
            points = [path.at(s, u, z + h) for u, h in
                      [(-w, -.004), (-w, -.015), (-w * .68, -.035), (w * .68, -.035), (w, -.015), (w, -.004)]]
            batch.face(points[::-1] if reverse else points, 'viaduct_concrete')

    for pier in network.piers:
        identity, s, bottom, top = pier['path'], pier['s'], pier['bottom'], pier['top']
        path = network.paths[identity]
        x, y, _ = path.at(s)
        a, b = path.at(s - .02), path.at(s + .02)
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        # A raised island identifies the pier's reserved space below the deck.
        ground = min(network.surface(x, y, False), network.surface(x, y, True)) - .005
        batch.box(x, y, ground, .078, .050, bottom - ground, 'viaduct_concrete', angle=angle)
        w = network.width(identity, s)
        rings = []
        for h, half in [(bottom, .012), (top - .055, .012), (top - .016, min(w * .68, .072)), (top, min(w * .74, .083))]:
            rings.append([path.at(s + ds, offset, h) for ds, offset in [(-.016, -half), (.016, -half), (.016, half), (-.016, half)]])
        for lower, upper in zip(rings, rings[1:]):
            for i in range(4):
                j = (i + 1) % 4
                batch.face([lower[i], lower[j], upper[j], upper[i]], 'viaduct_concrete')
        batch.face(rings[-1], 'viaduct_concrete')


def build_details(batch, network, lightweight=False):
    for identity, path in network.paths.items():
        spacing = .30 if lightweight else .20
        start = 0
        for i in range(math.ceil((path.length - start) / spacing)):
            a, b = start + i * spacing + .02, min(path.length - .03, start + i * spacing + (.10 if lightweight else .095))
            if b <= a:
                continue
            if identity != 'main' and network.merge_at(identity, (a + b) / 2):
                continue
            offsets = [-.085, -.045, .045, .085] if identity == 'main' else [0]
            for offset in offsets:
                strip(batch, path, a, b, offset - .0012, offset + .0012,
                      network.render_level(identity, a) + .0013, network.render_level(identity, b) + .0013, 'viaduct_line')
        if lightweight:
            continue
        # Edge lines and sparse lamps are a single mesh, never one object per fitting.
        stations = network.sections[identity]
        for a, b in zip(stations, stations[1:]):
            for side in [-1, 1]:
                if identity == 'main' and network.barrier_open((a + b) / 2, side):
                    continue
                if identity != 'main' and network.merge_at(identity, (a + b) / 2):
                    continue
                w = min(network.width(identity, a), network.width(identity, b)) - .015
                strip(batch, path, a, b, side * w - .0011, side * w + .0011,
                      network.level(identity, a) + .0013, network.level(identity, b) + .0013, 'viaduct_line')
        if identity != 'main':
            continue
        for i in range(1, math.floor(path.length / 1.2)):
            s = i * 1.2
            z = network.render_level(identity, s) + .014
            batch.beam(path.at(s, 0, z), path.at(s, 0, z + .10), .002, 'viaduct_metal')
            for side in [-1, 1]:
                batch.beam(path.at(s, 0, z + .10), path.at(s, side * .038, z + .115), .0018, 'viaduct_metal')
                batch.beam(path.at(s, side * .038, z + .115), path.at(s, side * .058, z + .115), .003, 'viaduct_metal')
