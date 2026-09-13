"""Trace unsupported footprints to source shorelines before inventing site geometry."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon,box,mapping
from shapely.ops import unary_union
from prepare_geodata import geom_for


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['geography','support','osm','envelope-audit','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    geography=json.loads(args.geography.read_text());support=json.loads(args.support.read_text())
    if support['inputs']['geography']['sha256']!=digest(args.geography):raise ValueError('Support geography is stale')
    snapshot=json.loads(args.osm.read_text());audit=json.loads(args.envelope_audit.read_text())
    if audit['inputs']['geography']['sha256']!=digest(args.geography):raise ValueError('Envelope inventory is stale')
    requested={r['id'] for r in audit['unresolved']};support={r['id']:r for r in support['records']}
    cx,cy=geography['center'];kx=1113.2*math.cos(math.radians(cy))
    project=lambda lon,lat:((lon-cx)*kx,(lat-cy)*1113.2)
    clip=box(*geography['bounds']);elements=snapshot['elements']
    lookup={f"osm/{e['type']}/{e['id']}":e for e in elements}
    def is_water(element):
        tags=element.get('tags',{})
        return tags.get('natural')=='water' or tags.get('waterway')=='riverbank'
    members={m['ref'] for e in elements if e['type']=='relation' and is_water(e)
             for m in e.get('members',[]) if m['type']=='way'}
    waters=[]
    for element in elements:
        if not is_water(element) or (element['type']=='way' and element['id'] in members):continue
        shape=geom_for(element,project=project,clip=clip)
        if shape is not None and not shape.is_empty:waters.append((element,shape))
    raw_water=unary_union([p for _,p in waters])
    display_water=unary_union([Polygon(r[0],r[1:]) for r in geography['water']])
    records=[]
    for building in geography['buildings']:
        if building['id'] not in requested:continue
        current=Polygon(building['rings'][0],building['rings'][1:])
        footprint_hash=hashlib.sha256(json.dumps(building['rings'],separators=(',',':')).encode()).hexdigest()
        measured=support[building['id']]
        if measured['footprintHash']!=footprint_hash:raise ValueError('Measured footprint is stale')
        element=lookup[building['sourceRef']];source=geom_for(element,project=project,clip=clip)
        nearby=sorted(waters,key=lambda pair:current.distance(pair[1]))[:2]
        overlaps={'candidateBuildingDisplayWater':current.intersection(display_water).area*10000,
                  'candidateBuildingSourceWater':current.intersection(raw_water).area*10000,
                  'sourceBuildingSourceWater':source.intersection(raw_water).area*10000}
        records.append({'id':building['id'],'name':building.get('name',''),'sourceRef':building['sourceRef'],
                        'sourceTags':element.get('tags',{}),'centroidLonLat':[cx+current.centroid.x/kx,cy+current.centroid.y/1113.2],
                        'overlapSquareMeters':overlaps,'sourceWaterDistanceMeters':current.distance(raw_water)*100,
                        'uncoveredTerrainSquareMeters':{p:measured['profiles'][p]['uncoveredAreaSquareMeters'] for p in ['detail','smooth']},
                        'sourceGeometry':mapping(source),'candidateGeometry':mapping(current),
                        'nearbyWater':[{'sourceRef':f"osm/{e['type']}/{e['id']}",'tags':e.get('tags',{}),
                                        'sourceGeometry':mapping(p),'distanceMeters':current.distance(p)*100} for e,p in nearby],
                        'nextAction':'dedicated reservoir/dam geometry; no residential height fallback' if building.get('use')=='dam'
                        else 'restore source shoreline and shared footprint geometry, then rebuild terrain/support; do not assume overwater construction'})
    if {r['id'] for r in records}!=requested:raise ValueError('Missing requested building')
    inputs={name:{'path':str(getattr(args,name).resolve()),'sha256':digest(getattr(args,name))}
            for name in ['geography','support','osm','envelope_audit']}
    result={'status':'source-geometry diagnosis; no candidate geography or terrain has been changed',
            'method':'Existing OSM projection/validity/10 cm storage precision before the 7.5 m water simplification; areas are model-space estimates',
            'records':records,'inputs':inputs,'toolSha256':digest(Path(__file__)),
            'geometryReaderSha256':digest(Path(__file__).with_name('prepare_geodata.py'))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k not in ['sourceGeometry','candidateGeometry','nearbyWater']} for r in records],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
