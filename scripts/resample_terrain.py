"""Resample attributed GLO-30 elevation and prepare a conditioned display DEM.

Raw samples are retained separately from the cartographic display surface.
This does not claim to derive surveyed bare-earth elevations from the DSM.
"""
import datetime
import hashlib
import json
import math
from pathlib import Path
import urllib.request

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import map_coordinates, gaussian_filter, percentile_filter, distance_transform_edt
from shapely import contains_xy, prepare as prepare_shape
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
TILE='Copernicus_DSM_COG_10_N22_00_E108_00_DEM'
URL=f'https://copernicus-dem-30m.s3.amazonaws.com/{TILE}/{TILE}.tif'


def prepare(raw_only=False):
    region=json.loads((ROOT/'data/region.json').read_text())
    bounds=region['bbox']
    geo={'center':[(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2]} if raw_only else json.loads((ROOT/'public/data/geography.json').read_text())
    cache=ROOT/'work/geodata'/f'{TILE}.tif';cache.parent.mkdir(parents=True,exist_ok=True)
    if not cache.exists():
        with urllib.request.urlopen(URL,timeout=180) as response:cache.write_bytes(response.read())
    west,south,east,north=region['bbox'];cx,cy=geo['center']
    assert 108<=west<east<109 and 22<south<north<=23, 'Add source tiles before expanding this region'
    spacing=region['terrainSpacingMeters']
    cols=math.ceil((east-west)*111320*math.cos(math.radians(cy))/spacing)+1
    rows=math.ceil((north-south)*111320/spacing)+1
    lons,lats=np.meshgrid(np.linspace(west,east,cols),np.linspace(north,south,rows))
    with rasterio.open(cache) as source:
        window=from_bounds(west-.004,south-.004,east+.004,north+.004,source.transform).round_offsets().round_lengths()
        source_heights=source.read(1,window=window).astype(np.float64)
        transform=source.window_transform(window)
        pixel_x=(lons-transform.c)/transform.a-.5;pixel_y=(lats-transform.f)/transform.e-.5
        # Anti-alias the native 1 arc-second DSM before sampling the coarser mesh.
        native_smoothed=gaussian_filter(source_heights,.65,mode='nearest')
        raw=map_coordinates(source_heights,[pixel_y,pixel_x],order=1,mode='nearest')
        sampled=map_coordinates(native_smoothed,[pixel_y,pixel_x],order=1,mode='nearest')
    assert np.isfinite(raw).all() and raw.min()>0 and raw.max()<1000
    if raw_only:
        payload={'bbox':region['bbox'],'center':geo['center'],'cols':cols,'rows':rows,
                 'heights':np.round(raw,2).ravel().tolist(),'minElevation':round(float(raw.min()),2),
                 'maxElevation':round(float(raw.max()),2),'source': 'Copernicus DEM GLO-30',
                 'sourceUrl':URL,'sourceResolutionArcSeconds':1,'units':'meters'}
        (ROOT/'public/data/terrain.json').write_text(json.dumps(payload,separators=(',',':')))
        print(f'Fetched GLO-30 source: {cols} x {rows}; run data:prepare for display conditioning',flush=True)
        return
    xx=(lons-cx)*1113.2*math.cos(math.radians(cy));yy=(lats-cy)*1113.2
    water=unary_union([Polygon(p[0],p[1:]) for p in geo['water']])
    parks=unary_union([Polygon(p[0],p[1:]) for p in geo['parks']])
    urban=unary_union([Polygon(p[0],p[1:]) for p in geo['urban']+geo['inferredUrban']])
    forest=json.loads((ROOT/'data/forest-plan.json').read_text())
    woods=unary_union([Polygon(p[0],p[1:]) for r in forest['regions'] for p in r['woodland']])
    for shape in [water,parks,urban,woods]:prepare_shape(shape)
    print('Prepared water, urban and forest masks',flush=True)
    wet=contains_xy(water,xx,yy);protected=contains_xy(woods,xx,yy)
    built=contains_xy(urban,xx,yy)&~protected&~wet
    # Lower-envelope filtering only within mapped built-up areas suppresses DSM
    # roof/tree spikes. Forest mountain ridges retain their broad relief.
    terrain=gaussian_filter(sampled,.65,mode='nearest')
    low=gaussian_filter(percentile_filter(sampled,35,size=5,mode='nearest'),1.1,mode='nearest')
    weight=np.minimum(1,distance_transform_edt(built)/2.0)
    terrain=terrain*(1-weight)+low*weight
    water_datum=float(np.round(np.median(raw[wet]),1))
    land_floor=water_datum+5
    terrain=np.maximum(land_floor,terrain)
    # Grade the two mall parcels before meshing; the flat apron covers both
    # detailed and coarse cell corners, not just the building centre point.
    mall_plan=json.loads((ROOT/'data/malls-plan.json').read_text())
    grades={}
    for identity,site in mall_plan['sites'].items():
        mx=(site['center'][0]-cx)*1113.2*math.cos(math.radians(cy));my=(site['center'][1]-cy)*1113.2
        shape=Polygon([(mx+u,my+v) for u,v in site['site']])
        core=contains_xy(shape.buffer(1.75),xx,yy)
        apron=contains_xy(shape.buffer(3.0),xx,yy)
        level=float(np.percentile(terrain[apron&~wet],25))
        distance=distance_transform_edt(~core)*spacing/100
        blend=np.clip(1-distance/1.25,0,1);blend=blend*blend*(3-2*blend)
        blend[wet]=0
        terrain=terrain*(1-blend)+level*blend
        grades[identity]={'levelMeters':round(level,3),'flatApronMeters':175,'blendApronMeters':125}
    terrain[wet]=water_datum-2
    raw=np.round(raw,2);terrain=np.round(terrain,3)
    metadata={'bbox':region['bbox'],'center':geo['center'],'cols':cols,'rows':rows,
              'heights':raw.ravel().tolist(),'sceneHeights':terrain.ravel().tolist(),
              'landcover':np.where(wet,2,np.where(contains_xy(parks,xx,yy)|protected,1,0)).ravel().tolist(),
              'minElevation':float(raw.min()),'maxElevation':float(raw.max()),'units':'meters',
              'datum':'Copernicus GLO-30 DSM, EGM2008 heights; display conditioning is separate',
              'source':'Copernicus DEM GLO-30, 2021 release, hosted on AWS by Sinergise',
              'sourceUrl':URL,'sourceSha256':hashlib.sha256(cache.read_bytes()).hexdigest(),
              'sourceResolutionArcSeconds':1,'sampleSpacingMeters':spacing,'accessed':datetime.date.today().isoformat(),
              'verticalDatumMeters':water_datum,'verticalOffset':.26,'verticalExaggeration':1.35,
              'conditioning':{'version':1,'resampling':'bilinear after native Gaussian antialiasing',
                              'urbanPercentile':35,'urbanWindowMeters':spacing*5,'forestRidgesProtected':True,
                              'landFloorMeters':land_floor,'waterDisplayMeters':water_datum-2,'gradedSites':grades}}
    (ROOT/'public/data/terrain.json').write_text(json.dumps(metadata,separators=(',',':')))
    manifest={k:v for k,v in metadata.items() if k not in ['heights','sceneHeights','landcover']}
    manifest['woodlandFootprintSha256']=hashlib.sha256(json.dumps([r['woodland'] for r in forest['regions']],separators=(',',':')).encode()).hexdigest()
    manifest['attributionFile']='public/data/terrain-attribution.txt'
    manifest['inputHashes']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                            ['data/region.json','public/data/geography.json','data/malls-plan.json']}
    (ROOT/'data/terrain-source.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'Copernicus: {cols} x {rows}, {spacing} m mesh, raw {raw.min():.2f}–{raw.max():.2f} m; datum {water_datum}; grades {grades}',flush=True)


if __name__=='__main__':prepare()
