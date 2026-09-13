"""Shared prepared-building envelope for rendering and road clearance inputs.

Full-footprint support prevents centre-point floating and penetration, but does
not certify entrance or site design. Special structures require their own model.
"""
import math

from block_massing import build_compound
from mapped_buildings import build_mapped


def prepared(building):return bool(building.get('massing') or building.get('qualityGeometry'))


def validate_road_envelope(index,building,placement,captured,tolerance_meters=.005):
    """Final access terrain must retain the upstream road-clearance volume."""
    record=captured.get(index)
    if record is None or record.get('id')!=building['id'] or placement['id']!=building['id']:
        raise ValueError('Missing or mismatched road envelope for '+building['id'])
    if any(not math.isfinite(record[key]) or not math.isfinite(placement[key]) or abs(record[key]-placement[key])*100>tolerance_meters
           for key in ['bottom','top']):
        raise ValueError('Building support changed after road capture; rebuild upstream support and roads: '+building['id'])


def envelope(building,support):
    if not prepared(building):raise ValueError('Use the legacy consumer for an unchanged building')
    if support is None:raise ValueError('Prepared buildings require a source-bound support plan')
    if building.get('use')=='dam':raise ValueError('Dam requires a hydraulic-structure consumer: '+building['id'])
    low,high=support.bounds(building)
    if not all(math.isfinite(v) for v in [low,high]) or low>high:raise ValueError('Invalid support range')
    floor=high+.002;bottom=low-.005
    if building.get('massing'):
        height=max(part['topMeters'] for part in building['massing'])/100
        kind='compound'
    else:
        height=building['height']/100*building.get('displayHeightScale',1.55)
        kind='mapped'
    if not math.isfinite(height) or height<=0:raise ValueError('Invalid building height')
    return {'id':building['id'],'kind':kind,'floor':floor,'bottom':bottom,'top':floor+height,
            'supportRange':[low,high],'reliefMeters':(high-low)*100,
            'siteReviewRequired':(high-low)*100>5}


def render(batch,building,placement,material,limit=None):
    if placement['id']!=building['id']:raise ValueError('Placement belongs to another building')
    top=placement['top'] if limit is None else min(placement['top'],limit)
    if not math.isfinite(top):raise ValueError('Invalid road height limit')
    if top<=placement['floor']:return None
    if placement['kind']=='compound':
        result=build_compound(batch,building,placement['supportRange'],material,limit)
        if result is None or abs(result['floor']-placement['floor'])>1e-10 or abs(result['top']-top)>1e-10:
            raise ValueError('Compound consumer differs from its road envelope')
    else:
        result=build_mapped(batch,building,placement['bottom'],top,material)
    return {**placement,'top':top,'geometry':result}
