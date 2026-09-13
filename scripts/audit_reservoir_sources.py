"""Inventory every mapped dam and its nearby source waters; never infer engineering heights.

Raw DSM water pixels can support a display-level candidate, but neither a water
depth nor interpolated samples on a narrow dam establish its crest elevation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import map_coordinates
from shapely import contains_xy
from shapely.geometry import Polygon, box, mapping
from prepare_geodata import geom_for


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statistics(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    result = {'count': len(values)}
    if len(values):
        result.update(dict(zip(['min', 'p10', 'p25', 'median', 'p75', 'p90', 'max'],
                               map(float, np.percentile(values, [0, 10, 25, 50, 75, 90, 100])))))
    return result


def display_level_candidate(water, dam_records):
    """Screen source evidence only; applying a candidate still requires shore/terrain work."""
    reasons = []
    connected = [r['id'] for r in dam_records for w in r['nearbyWaters']
                 if w['sourceRef'] == water['sourceRef'] and w['sharedBoundaryMeters'] >= 1]
    if not connected:
        reasons.append('no mapped shared dam/water boundary of at least 1 m')
    matches = water['displayMatches']
    if len(matches) != 1 or min(matches[0]['sourceCoverageFraction'], matches[0]['displayCoverageFraction']) < .9:
        reasons.append('display water does not have a unique mutually covering source match of at least 90%')
    samples = water['rawPixelStatisticsMetersByInset']
    if samples['30']['count'] < 20:
        reasons.append('fewer than 20 raw pixel centers inside the 30 m inset')
    elif samples['30']['p90']-samples['30']['p10'] > .5:
        reasons.append('30 m interior p90-p10 spread exceeds 0.5 m')
    medians = [s['median'] for s in samples.values() if s['count']]
    if len(medians) != 3 or max(medians)-min(medians) > .5:
        reasons.append('0/10/30 m inset medians are missing or differ by more than 0.5 m')
    return {'status': 'needs-source-review' if reasons else 'display-level-candidate',
            'levelMeters': None if reasons else samples['30']['median'],
            'sharedBoundaryDamIds': connected, 'reasons': reasons,
            'method': 'raw DSM median inside 30 m inset, screened for spatial stability and source matching',
            'isEngineeringLevel': False, 'appliedToRuntime': False}


class SourceRaster:
    def __init__(self, raster, center):
        if raster.crs != rasterio.crs.CRS.from_epsg(4326):
            raise ValueError('Expected source raster in EPSG:4326')
        self.raster = raster
        self.cx, self.cy = center
        self.kx = 1113.2 * math.cos(math.radians(self.cy))

    def pixels(self, shape):
        if shape.is_empty:
            return np.array([])
        w, s, e, n = shape.bounds
        window = from_bounds(self.cx+w/self.kx, self.cy+s/1113.2,
                             self.cx+e/self.kx, self.cy+n/1113.2,
                             self.raster.transform)
        # Expand outward before selecting actual pixel centers, including tiny polygons.
        c, r = math.floor(window.col_off), math.floor(window.row_off)
        window = rasterio.windows.Window(c, r, math.ceil(window.col_off+window.width)-c,
                                         math.ceil(window.row_off+window.height)-r)
        window = window.intersection(rasterio.windows.Window(0, 0, self.raster.width, self.raster.height))
        data = self.raster.read(1, window=window, masked=True)
        transform = self.raster.window_transform(window)
        gx, gy = np.meshgrid(np.arange(data.shape[1]), np.arange(data.shape[0]))
        x = (transform.c+(gx+.5)*transform.a-self.cx)*self.kx
        y = (transform.f+(gy+.5)*transform.e-self.cy)*1113.2
        valid = contains_xy(shape, x, y) & ~np.ma.getmaskarray(data)
        return np.asarray(data)[valid]

    def profile(self, shape):
        corners = np.asarray(shape.minimum_rotated_rectangle.exterior.coords[:-1])
        edges = np.roll(corners, -1, axis=0)-corners
        edge = edges[np.argmax(np.linalg.norm(edges, axis=1))]
        axis = edge/np.linalg.norm(edge)
        center = corners.mean(axis=0)
        distances = np.linspace(-np.linalg.norm(edge)/2, np.linalg.norm(edge)/2,
                                max(2, math.ceil(np.linalg.norm(edge)*100/5)+1))
        points = center+distances[:, None]*axis
        lon = self.cx+points[:, 0]/self.kx
        lat = self.cy+points[:, 1]/1113.2
        t = self.raster.transform
        cols, rows = (lon-t.c)/t.a-.5, (lat-t.f)/t.e-.5
        c, r = math.floor(cols.min())-1, math.floor(rows.min())-1
        window = rasterio.windows.Window(c, r, math.ceil(cols.max())-c+2,
                                         math.ceil(rows.max())-r+2)
        window = window.intersection(rasterio.windows.Window(0, 0, self.raster.width, self.raster.height))
        c, r = window.col_off, window.row_off
        data = self.raster.read(1, window=window, masked=True).astype(float).filled(np.nan)
        values = map_coordinates(data, [rows-r, cols-c], order=1, mode='constant', cval=np.nan)
        if not np.isfinite(values).all():
            raise ValueError('Dam profile has missing source raster samples')
        return {'method': 'bilinear raw DSM on long axis of footprint bounding rectangle; not surveyed crest',
                'sampleSpacingMaximumMeters': 5,
                'pointsSceneXY': points.tolist(), 'sourceMeters': values.tolist(),
                'statisticsMeters': statistics(values)}


def audit(geography, terrain, snapshot, raster_path):
    cx, cy = geography['center']
    kx = 1113.2*math.cos(math.radians(cy))
    project = lambda lon, lat: ((lon-cx)*kx, (lat-cy)*1113.2)
    clip = box(*geography['bounds'])
    elements = snapshot['elements']
    lookup = {f"osm/{e['type']}/{e['id']}": e for e in elements}
    is_water = lambda e: e.get('tags', {}).get('natural') == 'water' or e.get('tags', {}).get('waterway') == 'riverbank'
    members = {m['ref'] for e in elements if e['type'] == 'relation' and is_water(e)
               for m in e.get('members', []) if m['type'] == 'way'}
    waters = []
    for e in elements:
        if not is_water(e) or (e['type'] == 'way' and e['id'] in members):
            continue
        shape = geom_for(e, project=project, clip=clip)
        if shape is not None and not shape.is_empty and shape.area > 0:
            waters.append((f"osm/{e['type']}/{e['id']}", e, shape))
    display = [Polygon(r[0], r[1:]) for r in geography['water']]
    records, selected_waters = [], {}
    with rasterio.open(raster_path) as raster:
        sampler = SourceRaster(raster, geography['center'])
        for index, building in enumerate(geography['buildings']):
            element = lookup.get(building.get('sourceRef'))
            tags = element.get('tags', {}) if element else {}
            # Include source-tagged dams even if an earlier classifier lost their use.
            if not (building.get('use') == 'dam' or tags.get('building') == 'dam' or tags.get('waterway') == 'dam'):
                continue
            if element is None:
                raise ValueError('Missing source for dam '+building['id'])
            source = geom_for(element, project=project, clip=clip)
            if source is None or source.is_empty or source.area <= 0:
                raise ValueError('Dam has no valid polygon source '+building['id'])
            footprint = Polygon(building['rings'][0], building['rings'][1:])
            nearby = []
            # 100 m is a search radius, not proof of upstream/downstream connection.
            for ref, water_element, water_shape in sorted(waters, key=lambda pair: (source.distance(pair[2]), pair[0])):
                distance = source.distance(water_shape)*100
                if distance > 100:
                    break
                nearby.append({'sourceRef': ref, 'distanceMeters': distance,
                               'sharedBoundaryMeters': source.boundary.intersection(water_shape.boundary).length*100,
                               'sourceOverlapSquareMeters': source.intersection(water_shape).area*10000})
                if ref in selected_waters:
                    continue
                pixel_stats = {str(inset): statistics(sampler.pixels(water_shape.buffer(-inset/100)))
                               for inset in [0, 10, 30]}
                matches = []
                for wi, polygon in enumerate(display):
                    overlap = water_shape.intersection(polygon).area
                    if overlap > 1e-8:
                        matches.append({'index': wi, 'intersectionSquareMeters': overlap*10000,
                                        'sourceCoverageFraction': overlap/water_shape.area,
                                        'displayCoverageFraction': overlap/polygon.area})
                selected_waters[ref] = {'sourceRef': ref, 'sourceFeature': water_element,
                                        'sourceGeometry': mapping(water_shape),
                                        'areaSquareMeters': water_shape.area*10000,
                                        'rawPixelStatisticsMetersByInset': pixel_stats,
                                        'displayMatches': matches,
                                        'levelStatus': 'unapproved raw DSM evidence; no engineering level or runtime change'}
            records.append({'index': index, 'id': building['id'], 'sourceRef': building['sourceRef'],
                            'sourceFeature': element, 'sourceGeometry': mapping(source),
                            'candidateGeometry': mapping(footprint),
                            'usesPreparedBuildingPath': bool(building.get('qualityGeometry') or building.get('massing')),
                            'legacyHeightMeters': building['height'], 'heightSource': building.get('heightSource'),
                            'centroidLonLat': [cx+source.centroid.x/kx, cy+source.centroid.y/1113.2],
                            'nearbyWaters': nearby, 'rawDsmLongAxis': sampler.profile(source),
                            'rawFootprintPixelsMeters': statistics(sampler.pixels(source)),
                            'engineeringCrestMeters': None, 'engineeringDamHeightMeters': None})
    for water in selected_waters.values():
        water['displayLevelCandidate'] = display_level_candidate(water, records)
    source_dams = []
    for ref, e in lookup.items():
        tags = e.get('tags', {})
        if tags.get('building') == 'dam' or tags.get('waterway') == 'dam':
            source_dams.append({'sourceRef': ref, 'tags': tags,
                                'buildingRecordIds': [r['id'] for r in records if r['sourceRef'] == ref]})
    return {'schemaVersion': 1, 'status': 'source inventory; geometry and levels have not been applied',
            'units': {'geometry': 'local east/north, 100 m per scene unit', 'sourceHeights': 'meters EGM2008 DSM'},
            'sourceGeometryPrecisionMeters': .1, 'nearbyWaterSearchRadiusMeters': 100,
            'scope': {'mappedDamRecords': len(records),
                      'preparedDamRecords': sum(r['usesPreparedBuildingPath'] for r in records),
                      'legacyDamRecords': sum(not r['usesPreparedBuildingPath'] for r in records),
                      'nearbySourceWaterFeatures': len(selected_waters),
                      'screenedDisplayLevelCandidates': sum(w['displayLevelCandidate']['status'] == 'display-level-candidate'
                                                           for w in selected_waters.values()),
                      'sourceDamFeatures': len(source_dams)},
            'terrainDatum': {k: terrain[k] for k in ['verticalDatumMeters', 'verticalOffset', 'verticalExaggeration',
                                                    'sourceUrl', 'sourceSha256', 'sourceResolutionArcSeconds']},
            'records': records, 'waters': [selected_waters[k] for k in sorted(selected_waters)],
            'sourceDamFeatures': source_dams,
            'limitations': ['Search proximity alone does not identify upstream water or hydraulic connectivity.',
                            'DSM is a surface model; 5 m interpolation does not resolve a narrow dam crest.',
                            'Raw water pixels may contain bank, vegetation or acquisition artifacts.',
                            'No fallback building height may be promoted to an engineering dam height.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['geography', 'terrain', 'osm', 'raster', 'output']:
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    terrain = json.loads(args.terrain.read_text())
    if digest(args.raster) != terrain['sourceSha256']:
        raise ValueError('Source raster hash does not match terrain provenance')
    result = audit(json.loads(args.geography.read_text()), terrain, json.loads(args.osm.read_text()), args.raster)
    result['inputs'] = {key: {'path': str(getattr(args, key).resolve()), 'sha256': digest(getattr(args, key))}
                        for key in ['geography', 'terrain', 'osm', 'raster']}
    result['toolSha256'] = digest(Path(__file__))
    result['geometryReaderSha256'] = digest(Path(__file__).with_name('prepare_geodata.py'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result['scope']))


if __name__ == '__main__':
    main()
