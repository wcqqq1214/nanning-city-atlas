"""The city and offline validators share the same pre-railway ground model."""
import math

from terrain_height import scene_height
from nanhu_landmark import shore_height
from expo_landmark import site_distance
from sports_landmark import SITE_PADS, pad_distance
from station_landmarks import STATIONS, ground_blend


class SceneGround:
    def __init__(self, geography, terrain, catalog):
        self.bounds = geography['bounds']
        self.terrain = terrain
        self.columns, self.rows = terrain['cols'], terrain['rows']
        self.heights = terrain.get('sceneHeights', terrain['heights'])
        places = {p['id']: p for p in catalog}

        def origin(identity):
            p = places[identity]
            return ((p['lon']-geography['center'][0])*1113.2*math.cos(math.radians(geography['center'][1])),
                    (p['lat']-geography['center'][1])*1113.2)

        self.nanhu = origin('nanhu')
        self.expo = origin('expo')
        self.expo_level = self.terrain_height(*self.expo)
        self.sports = origin('sports-center')
        self.sports_levels = [self.terrain_height(self.sports[0]+pad[0], self.sports[1]+pad[1]) for pad in SITE_PADS]
        self.stations = {}
        for identity, station in STATIONS.items():
            if [places[identity]['lon'], places[identity]['lat']] != station['center']:
                raise ValueError('Station ground and scene use different origins')
            x, y = origin(identity)
            self.stations[identity] = (x, y, self.terrain_height(x, y))

    def terrain_height(self, x, y):
        west, south, east, north = self.bounds
        i = max(0, min(self.columns-1.001, (x-west)/(east-west)*(self.columns-1)))
        j = max(0, min(self.rows-1.001, (north-y)/(north-south)*(self.rows-1)))
        ix, jy = int(i), int(j)
        a, b = i-ix, j-jy
        heights = self.heights
        h = (heights[jy*self.columns+ix]*(1-a)+heights[jy*self.columns+ix+1]*a)*(1-b) + (heights[(jy+1)*self.columns+ix]*(1-a)+heights[(jy+1)*self.columns+ix+1]*a)*b
        return scene_height(h, self.terrain)

    def __call__(self, x, y):
        h = self.terrain_height(x, y)
        h = shore_height(x-self.nanhu[0], y-self.nanhu[1], h)
        distance = site_distance(x-self.expo[0], y-self.expo[1])
        if distance < 1.3:
            t = max(0, min(1, (distance-.45)/.85))
            blend = t*t*(3-2*t)
            h = self.expo_level*(1-blend)+h*blend
        for pad, level in zip(SITE_PADS, self.sports_levels):
            distance = pad_distance(x-self.sports[0], y-self.sports[1], pad)
            if distance < .65:
                t = max(0, distance/.65)
                blend = t*t*(3-2*t)
                h = level*(1-blend)+h*blend
        for identity, (sx, sy, level) in self.stations.items():
            if abs(x-sx) < 10 and abs(y-sy) < 10:
                blend = ground_blend(identity, x-sx, y-sy)
                h = level*(1-blend)+h*blend
        return h
