"""Shared building/site visibility for city generation and offline P5 audits."""
import math

from sports_landmark import inside_site
from tingzi_landmark import inside_site as inside_tingzi
from changyou_landmark import inside_site as inside_changyou
from station_landmarks import STATIONS, inside_site as inside_station
from mall_landmarks import SITES as MALL_SITES, inside_site as inside_mall, intersects_site as intersects_mall
from landmark_sites import SPECS as CALIBRATION, inside_site as inside_calibrated_site


class CityVisibility:
    def __init__(self, geography, catalog):
        cx, cy = geography['center']
        # Keep the builder's multiplication order: a reassociation changes
        # strict boundary predicates for points exactly on a reservation edge.
        def pos(lon, lat): return (lon-cx)*1113.2*math.cos(math.radians(cy)), (lat-cy)*1113.2
        places = {p['id']: p for p in catalog}
        self.clear_areas = [(*pos(p['lon'], p['lat']), *p['clearExtent']) for p in catalog
                            if 'clearExtent' in p and p['id'] not in CALIBRATION]
        self.legacy_clear_areas = self.clear_areas+[
            (*pos(places[i]['lon'], places[i]['lat']), *s['legacyClearExtentScene'])
            for i, s in CALIBRATION.items() if s.get('legacyClearExtentScene')]
        self.calibration_origins = {i: pos(places[i]['lon'], places[i]['lat']) for i in CALIBRATION}
        self.mall_origins = {i: pos(*s['center']) for i, s in MALL_SITES.items()}
        self.station_origins = {i: pos(*s['center']) for i, s in STATIONS.items()}
        self.sports = pos(places['sports-center']['lon'], places['sports-center']['lat'])
        self.tingzi = pos(places['tingzi']['lon'], places['tingzi']['lat'])
        self.changyou = pos(places['changyou']['lon'], places['changyou']['lat'])

    def inside_landmark(self, x, y, legacy=False):
        return (inside_site(x-self.sports[0], y-self.sports[1]) or
                any(abs(x-sx)<3 and abs(y-sy)<3 and inside_mall(identity, x-sx, y-sy)
                    for identity, (sx, sy) in self.mall_origins.items()) or
                inside_tingzi(x-self.tingzi[0], y-self.tingzi[1]) or
                inside_changyou(x-self.changyou[0], y-self.changyou[1]) or
                any(abs(x-sx)<7 and abs(y-sy)<7 and inside_station(identity, x-sx, y-sy)
                    for identity, (sx, sy) in self.station_origins.items()) or
                any(abs(x-cx)<width/2 and abs(y-cy)<depth/2 for cx, cy, width, depth in
                    (self.legacy_clear_areas if legacy else self.clear_areas)) or
                (not legacy and any(abs(x-cx)<3 and abs(y-cy)<3 and inside_calibrated_site(identity, x-cx, y-cy)
                                    for identity, (cx, cy) in self.calibration_origins.items())))

    def building_visible(self, building, railway_hidden=False, legacy=False):
        if railway_hidden: return False
        if any(n in building.get('name', '') for n in ['龙象塔', '华润大厦A', '地王国际商会中心']): return False
        ring = building['rings'][0][:-1]
        if len(ring) < 3: return False
        x = sum(p[0] for p in ring)/len(ring); y = sum(p[1] for p in ring)/len(ring)
        return not self.inside_landmark(x, y, legacy=legacy) and not any(
            abs(x-sx)<5 and abs(y-sy)<5 and intersects_mall(identity, ring, sx, sy)
            for identity, (sx, sy) in self.mall_origins.items())
