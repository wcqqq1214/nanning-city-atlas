"""Restore selected source shorelines and shared building edges in a candidate.

Water indices and unrelated triangles stay stable. This prepares geography only;
dependent terrain, lake provenance, roads and vegetation must be rebuilt.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from prepare_geodata import geom_for,coords,triangulate_water
from prepare_building_quality import mesh_roof_triangles
from prepare_urban_blocks import roof_triangles
from prepare_waterfront import polygons

ROOT=Path(__file__).resolve().parents[1]


def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
def face_key(face):return tuple(sorted(tuple(point) for point in face))


def permitted_water_overlap(source,identity):
    """Only an explicitly recorded, source-layered dam may retain source water beneath it."""
    entry=next((e for e in source['buildings'] if e['id']==identity),None)
    if entry is None or entry.get('waterRelationship') is None:return 0.0
    tags=entry['feature'].get('tags',{})
    if (entry['waterRelationship']!='mapped-overwater-structure' or tags.get('waterway')!='dam'
            or tags.get('building')!='dam' or int(tags.get('layer','0'))<=0):
        raise ValueError('Only a source-layered dam can retain mapped water overlap')
    area=entry.get('expectedWaterOverlapSquareMeters')
    if not isinstance(area,(int,float)) or not math.isfinite(area) or area<=0:
        raise ValueError('Record the exact source water overlap for the layered dam')
    return area


def replacement_water(entry,before,project,clip):
    if entry.get('operation')=='restore-source-union':
        components=[]
        for item in entry['components']:
            feature=item['feature']
            if item['sourceRef']!=f"osm/{feature['type']}/{feature['id']}":raise ValueError('Union component source identity differs')
            parts=list(polygons(geom_for(feature,project=project,clip=clip)))
            part=parts[item['sourcePart']]
            if digest(coords(part))!=item['expectedSourcePartSha256']:
                raise ValueError('Union source component changed')
            components.append(part)
        if len(components)<2:raise ValueError('A source union needs at least two reviewed components')
        new=unary_union(components)
        if abs(sum(p.area for p in components)-new.area)*10000>1e-6:
            raise ValueError('Source union components overlap')
        return new,3
    feature=entry['feature']
    if entry['sourceRef']!=f"osm/{feature['type']}/{feature['id']}":raise ValueError('Water source identity differs')
    source_shape=geom_for(feature,project=project,clip=clip)
    if entry.get('operation','restore-source')=='restore-source':return source_shape,3
    if entry['operation']!='clip-source-dam-footprint':raise ValueError('Unsupported shoreline operation')
    tags=feature.get('tags',{})
    if tags.get('building')!='dam' or tags.get('waterway')!='dam' or int(tags.get('layer','0'))>0:
        raise ValueError('Only a mapped land dam can clip its adjoining water')
    rr=coords(source_shape);dam=Polygon(rr[0],rr[1:])
    neighbor=geom_for(entry['sharedWaterFeature'],project=project,clip=clip)
    rr=coords(neighbor);neighbor=Polygon(rr[0],rr[1:])
    if dam.intersection(neighbor).area*10000>1e-6 or dam.boundary.intersection(neighbor.boundary).length*100<1:
        raise ValueError('Source does not establish a shared dry dam/water boundary')
    after=before.difference(dam);removed=(before.area-after.area)*10000
    if abs(removed-entry['expectedRemovedSquareMeters'])>1e-4:
        raise ValueError('Local dam shoreline correction area differs from the reviewed source')
    # Overlay intersections need extra storage digits; they add no source precision.
    return after,9


def restore(geography,source,*,record_key='shorelineRestoration'):
    if record_key not in ['shorelineRestoration','reservoirShorelineRestoration','reservoirRolloutRestoration','reservoirNeighborRestoration']:
        raise ValueError('Unsupported restoration record key')
    if record_key in geography:raise ValueError('Prepare from the frozen pre-restoration geography')
    if geography['metersPerUnit']!=100 or source['metersPerUnit']!=100 or geography['center']!=source['center']:
        raise ValueError('Source and city coordinates differ')
    if source['precisionMeters']!=.1:raise ValueError('Unsupported source coordinate precision')
    result=copy.deepcopy(geography);cx,cy=geography['center'];kx=1113.2*math.cos(math.radians(cy))
    project=lambda lon,lat:((lon-cx)*kx,(lat-cy)*1113.2)
    clip=box(*geography['bounds']);replacements={};reports=[]
    for entry in source['water']:
        index=entry['geographyWaterIndex']
        if index in replacements:raise ValueError('Repeated water index')
        old=geography['water'][index]
        if digest(old)!=entry['expectedPolygonSha256']:raise ValueError('Source water index or footprint is stale')
        before=Polygon(old[0],old[1:]);new,precision=replacement_water(entry,before,project,clip)
        if new is None or new.geom_type!='Polygon' or not new.is_valid or new.area<=0:raise ValueError('Expected one valid source water polygon')
        if before.intersection(new).area/min(before.area,new.area)<source['minimumPolygonOverlapFraction']:
            raise ValueError('Source water does not match selected city polygon')
        if len(new.interiors)!=len(before.interiors):raise ValueError('Water island count changed; explicit review required')
        new_rings=[[[round(x,precision),round(y,precision)] for x,y in ring.coords] for ring in [new.exterior,*new.interiors]]
        new=Polygon(new_rings[0],new_rings[1:])
        result['water'][index]=new_rings
        old_triangles=triangulate_water(before,precision=9);new_triangles=triangulate_water(new,precision=precision)
        replacements[index]={'old':old_triangles,'new':new_triangles}
        reports.append({'index':index,'sourceRef':entry['sourceRef'],'beforeSha256':digest(old),'afterSha256':digest(new_rings),
                        'beforeAreaSquareMeters':before.area*10000,'afterAreaSquareMeters':new.area*10000,
                        'symmetricDifferenceSquareMeters':before.symmetric_difference(new).area*10000,
                        'islands':len(new.interiors),'beforeTriangles':len(old_triangles),'afterTriangles':len(new_triangles)})
    # Replace only known source triangles; do not retriangulate unrelated lakes.
    owners={};remaining={i:Counter(face_key(t) for t in r['old']) for i,r in replacements.items()}
    for index,counts in remaining.items():
        for key in counts:
            if key in owners:raise ValueError('Ambiguous water triangle owner')
            owners[key]=index
    triangles=[];emitted=set();outside=[]
    for triangle in geography['waterTriangles']:
        key=face_key(triangle);index=owners.get(key)
        if index is None:triangles.append(triangle);outside.append(triangle);continue
        if remaining[index][key]<=0:raise ValueError('Repeated water face beyond source triangulation')
        remaining[index][key]-=1
        if index not in emitted:triangles.extend(replacements[index]['new']);emitted.add(index)
    if any(sum(counts.values()) for counts in remaining.values()):raise ValueError('City water triangles do not match their polygons')
    result['waterTriangles']=triangles
    restored=[]
    for entry in source['buildings']:
        matches=[b for b in result['buildings'] if b['id']==entry['id']]
        if len(matches)!=1:raise ValueError('Missing or duplicate source building')
        building=matches[0]
        if building.get('sourceRef')!=entry['sourceRef'] or digest(building['rings'])!=entry['expectedFootprintSha256']:
            raise ValueError('Building footprint/source is stale')
        feature=entry['feature']
        if entry['sourceRef']!=f"osm/{feature['type']}/{feature['id']}":raise ValueError('Building source identity differs')
        shape=geom_for(feature,project=project,clip=clip)
        if shape is None or shape.geom_type!='Polygon' or not shape.is_valid:raise ValueError('Expected valid source building')
        building['rings']=coords(shape);shape=Polygon(building['rings'][0],building['rings'][1:])
        building['roofTriangles']=roof_triangles(shape);building['meshRoofTriangles']=mesh_roof_triangles(building['rings'])
        building['qualityGeometry']=True
        building['footprintSource']={'method':'preserved-source-near-water','toleranceMeters':0,
                                    'coordinatePrecisionMeters':.1,'reference':entry['sourceRef'],'sourcePart':0,
                                    'sourceAreaSquareMeters':shape.area*10000,'interiorRings':len(shape.interiors)}
        restored.append(building['id'])
    old_water=unary_union([Polygon(p[0],p[1:]) for p in geography['water']])
    new_water=unary_union([Polygon(p[0],p[1:]) for p in result['water']])
    if abs(sum(Polygon(p[0],p[1:]).area for p in result['water'])-new_water.area)>1e-8:
        raise ValueError('Restored lake overlaps another water polygon')
    affected=[]
    for identity in source['affectedBuildingIds']:
        building=next(b for b in result['buildings'] if b['id']==identity);shape=Polygon(building['rings'][0],building['rings'][1:])
        overlap=shape.intersection(new_water).area*10000
        expected=permitted_water_overlap(source,identity)
        if abs(overlap-expected)>1e-6:raise ValueError('Source restoration water overlap differs for '+identity)
        affected.append({'id':identity,'afterWaterOverlapSquareMeters':overlap,'afterWaterDistanceMeters':shape.distance(new_water)*100,
                         'waterRelationship':'mapped-overwater-structure' if expected else 'land'})
    gained=new_water.difference(old_water)
    ancillary={name:sum(Polygon(p[0],p[1:]).intersection(gained).area for p in result[name])*10000
               for name in ['parks','urban','inferredUrban']}
    landcover_changes=[]
    for name in ['parks','urban','inferredUrban']:
        corrected=[]
        for index,outlines in enumerate(result[name]):
            shape=Polygon(outlines[0],outlines[1:])
            if shape.intersection(gained).area<=1e-12:corrected.append(outlines);continue
            cut=shape.difference(gained)
            # Old self-touching rings can leave zero-area lines after overlay.
            # Land cover stores surfaces only; the coverage check below still
            # requires every square metre of the resulting surface to survive.
            pieces=[p for p in polygons(cut) if not p.is_empty]
            if any(not p.is_valid for p in pieces):raise ValueError('Invalid land-cover overlay surface')
            # Keep line-intersection coordinates, rather than snapping them off
            # the shared shoreline again. This adds no new source measurements.
            emitted=[[[[round(x,9),round(y,9)] for x,y in ring.coords]
                       for ring in [p.exterior,*p.interiors]] for p in pieces]
            covered=unary_union([Polygon(p[0],p[1:]) for p in emitted])
            if covered.intersection(gained).area*10000>1e-5:raise ValueError('Land-cover rounding crosses restored water')
            if covered.symmetric_difference(cut).area*10000>1e-4:raise ValueError('Land-cover overlay exceeds storage tolerance')
            start=len(corrected);corrected.extend(emitted)
            landcover_changes.append({'field':name,'sourceIndex':index,'outputIndices':list(range(start,len(corrected))),
                                      'removedSquareMeters':(shape.area-covered.area)*10000})
        result[name]=corrected
    removed_trees=[];tree_indices=set()
    for entry in source.get('treeRemovals',[]):
        index=entry['index']
        if index in tree_indices or geography['trees'][index]!=entry['expectedTree']:
            raise ValueError('Tree removal identity is duplicate or stale')
        point=Point(entry['expectedTree'][:2]);water_index=entry['geographyWaterIndex']
        if (water_index not in replacements or not gained.covers(point)
                or not Polygon(result['water'][water_index][0],result['water'][water_index][1:]).covers(point)):
            raise ValueError('Only a reviewed tree newly inside restored water can be removed')
        tree_indices.add(index);removed_trees.append(copy.deepcopy(entry))
    if tree_indices:
        if result['stats']['trees']!=len(result['trees']):raise ValueError('Stale tree count')
        result['trees']=[tree for i,tree in enumerate(result['trees']) if i not in tree_indices]
        result['stats']['trees']=len(result['trees'])
    wet_trees=[i for i,(x,y,_) in enumerate(result['trees']) if gained.covers(Point(x,y))]
    footprints=[Polygon(b['rings'][0],b['rings'][1:]) for b in result['buildings']]
    new_overlaps=[]
    for index in STRtree(footprints).query(gained,predicate='intersects'):
        area=footprints[index].intersection(gained).area*10000
        if area>1e-6:new_overlaps.append({'id':result['buildings'][index]['id'],'areaSquareMeters':area})
    record={'id':source['id'],'status':'source geometry restored; downstream terrain, land cover, roads and vegetation pending',
            'sourceHash':digest(source),'water':reports,'restoredBuildingIds':restored,'affectedBuildings':affected,
            'unchangedWaterTriangles':len(outside),'unchangedWaterTrianglesSha256':digest(outside),
            'newWaterLandcoverOverlapBeforeCorrectionSquareMeters':ancillary,'landcoverChanges':landcover_changes,
            'removedTrees':removed_trees,'newWaterTreeIndices':wet_trees,'newWaterBuildingOverlaps':new_overlaps}
    result[record_key]=record
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=ROOT/'data/building-shoreline-source.json')
    parser.add_argument('--record-key',choices=['shorelineRestoration','reservoirShorelineRestoration','reservoirRolloutRestoration','reservoirNeighborRestoration'],default='shorelineRestoration')
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():raise ValueError('Write a candidate separately from its frozen input')
    result=restore(json.loads(args.input.read_text()),json.loads(args.source.read_text()),record_key=args.record_key)
    result[args.record_key]['inputSha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    result[args.record_key]['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(result[args.record_key],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
