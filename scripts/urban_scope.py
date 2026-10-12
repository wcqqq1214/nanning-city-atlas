"""Approved display scope in the city's existing 100 m east/north coordinates.

This is a product boundary, not an administrative or surveyed urban boundary.
Source geography stays intact so upstream terrain/road dependency hashes remain
valid. Only the intersection with existing source coverage is exportable.
"""
import json
import math
from pathlib import Path

from shapely import make_valid
from shapely.geometry import Polygon, box
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]


def polygons(shape):
    if shape.is_empty:
        return
    if shape.geom_type == 'Polygon':
        yield shape
    elif hasattr(shape, 'geoms'):
        for part in shape.geoms:
            yield from polygons(part)


class UrbanScope:
    def __init__(self, source, geography):
        self.source = source
        self.geo = geography
        self.units = geography['metersPerUnit']
        if self.units != 100:
            raise ValueError('The city projection requires 100 m per unit')
        self.cx, self.cy = geography['center']
        self.kx = math.cos(math.radians(self.cy)) * 1113.2
        self.ky = 1113.2
        ring = []
        for segment in source['segments']:
            if ring and ring[-1] != segment['points'][0]:
                raise ValueError('Disconnected boundary segment: ' + segment['id'])
            ring.extend(segment['points'][1:] if ring else segment['points'])
        if not ring or ring[0] != ring[-1]:
            raise ValueError('Core ring must be explicitly closed')
        self.proposed = transform(self.project, Polygon(ring))
        if not self.proposed.is_valid:
            raise ValueError('Invalid urban boundary')
        self.coverage = box(*geography['bounds'])
        self.buildings = [make_valid(Polygon(b['rings'][0], b['rings'][1:]))
                          for b in geography['buildings']]
        self.retained_buildings = [i for i, b in enumerate(self.buildings)
                                   if self.proposed.intersects(b)]
        self.crossing_buildings = [i for i in self.retained_buildings
                                   if not self.proposed.covers(self.buildings[i])]
        # A small apron keeps walls, roof overhangs and their ground together.
        # Include all retained footprints: even an inside building can have an
        # overhang outside the line. Do not progressively absorb rural blocks.
        apron = source.get('buildingApronMeters', 20) / self.units
        near = [self.buildings[i].buffer(apron, quad_segs=2)
                for i in self.retained_buildings
                if self.proposed.boundary.distance(self.buildings[i]) < apron
                or i in self.crossing_buildings]
        self.core = unary_union([self.proposed, *near]).intersection(self.coverage)
        self.transition = self.core.buffer(source['contextWidthMeters']/self.units,
                                           quad_segs=8).intersection(self.coverage)
        # The city line controls detail, never the silhouette of the model.
        # Fill its rectangular envelope with inexpensive geographic context.
        self.context = self.transition.envelope
        # Keep complete major water bodies and their banks at source detail.
        # A city-detail line must never turn into a dam across the Yong River.
        water = unary_union([make_valid(Polygon(r[0], r[1:])) for r in geography['water']])
        self.water_corridors = unary_union([p for p in polygons(water)
            if p.area/100 >= source['continuousWaterMinAreaKm2'] and p.intersects(self.core)]).intersection(self.context)
        joined = self.transition.union(self.water_corridors.buffer(
            source['riverbankContextMeters']/self.units, quad_segs=4)).intersection(self.context)
        # Retain the small enclosed patches too, avoiding isolated LOD holes.
        self.transition = Polygon(joined.exterior)
        self.landscape = self.core.buffer(source['landscapeFadeMeters']/self.units,
                                          quad_segs=8).intersection(self.context)
        for shape in [self.core, self.transition, self.context]:
            if shape.is_empty or not shape.is_valid or shape.geom_type != 'Polygon':
                raise ValueError('Export scope must be one valid connected polygon')

    def mask_for(self, name):
        if name.startswith('Vegetation') and '_canopy' in name:
            return self.landscape
        if name.startswith(('Buildings', 'Vegetation')):
            return self.core
        if name in ('Water', 'Plinth'):
            return self.context
        return self.transition

    def project(self, x, y, z=None):
        return (x-self.cx)*self.kx, (y-self.cy)*self.ky

    def inverse(self, x, y, z=None):
        return x/self.kx+self.cx, y/self.ky+self.cy

    @classmethod
    def read(cls, root=ROOT):
        source = json.loads((root/'data/urban-core-boundary-source.json').read_text())
        geography = json.loads((root/'public/data/geography.json').read_text())
        return cls(source, geography)

    def require_approved(self):
        if self.source.get('status') != 'approved' or not self.source.get('readyForModelExport'):
            raise ValueError('Urban scope has not been approved for export')
