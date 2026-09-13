"""Check the serialized shoreline candidate, including unchanged surroundings."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
from shapely.strtree import STRtree
from prepare_geodata import geom_for
from prepare_building_shorelines import permitted_water_overlap,replacement_water


def check(before,after,source,*,record_key='shorelineRestoration'):
    selected={e['geographyWaterIndex'] for e in source['water']};identities={e['id'] for e in source['buildings']}
    assert len(before['water'])==len(after['water'])
    assert len(before['buildings'])==len(after['buildings'])
    assert record_key not in before,'Cannot overwrite a previous restoration record'
    assert set(after)==set(before)|{record_key}
    for key in before:
        if key not in ['water','waterTriangles','buildings','parks','urban','inferredUrban','trees','stats']:assert before[key]==after[key],key
    for i,(a,b) in enumerate(zip(before['water'],after['water'])):
        if i not in selected:assert a==b,i
    cx,cy=after['center'];kx=1113.2*math.cos(math.radians(cy))
    project=lambda lon,lat:((lon-cx)*kx,(lat-cy)*1113.2)
    for entry in source['water']:
        r=after['water'][entry['geographyWaterIndex']]
        old=before['water'][entry['geographyWaterIndex']]
        expected,_=replacement_water(entry,Polygon(old[0],old[1:]),project,box(*after['bounds']))
        assert Polygon(r[0],r[1:]).symmetric_difference(expected).area*10000<1e-6,'Shoreline differs from source'
    for a,b in zip(before['buildings'],after['buildings']):
        assert a['id']==b['id']
        if a['id'] not in identities:assert a==b,a['id']
        else:
            for key in set(a)|set(b):
                if key not in ['rings','roofTriangles','meshRoofTriangles','qualityGeometry','footprintSource']:
                    assert a.get(key)==b.get(key),(a['id'],key)
            entry=next(e for e in source['buildings'] if e['id']==b['id'])
            expected=geom_for(entry['feature'],project=project,clip=box(*after['bounds']))
            assert Polygon(b['rings'][0],b['rings'][1:]).symmetric_difference(expected).area*10000<1e-6,'Footprint differs from source'
    water=unary_union([Polygon(p[0],p[1:]) for p in after['water']])
    old_water=unary_union([Polygon(p[0],p[1:]) for p in before['water']]);gained=water.difference(old_water)
    removed={entry['index'] for entry in source.get('treeRemovals',[])}
    assert len(removed)==len(source.get('treeRemovals',[])),'Repeated tree removal'
    for entry in source.get('treeRemovals',[]):
        assert before['trees'][entry['index']]==entry['expectedTree'],'Stale tree removal'
        point=Point(entry['expectedTree'][:2]);index=entry['geographyWaterIndex']
        assert index in selected and gained.covers(point),'Tree removal outside gained water'
        rings=after['water'][index]
        assert Polygon(rings[0],rings[1:]).covers(point),'Wrong source lake for tree removal'
    assert after['trees']==[t for i,t in enumerate(before['trees']) if i not in removed],'Unrelated trees changed'
    if removed:
        assert before['stats']['trees']==len(before['trees'])
        assert after['stats']=={**before['stats'],'trees':len(after['trees'])},'Unrelated statistics changed'
    else:assert before.get('stats')==after.get('stats'),'Statistics changed without tree removals'
    faces=[Polygon(t) for t in after['waterTriangles']];mesh=unary_union(faces)
    area_delta=mesh.symmetric_difference(water).area*10000
    overlap=(math.fsum(p.area for p in faces)-mesh.area)*10000
    assert all(p.area>0 for p in faces),'Degenerate water triangle'
    assert area_delta<1e-5,area_delta
    assert abs(overlap)<1e-4,overlap
    for index in selected:
        assert len(before['water'][index])==len(after['water'][index]),'Water island lost'
    unchanged=[]
    for g in [before,after]:
        region=unary_union([Polygon(g['water'][i][0],g['water'][i][1:]) for i in selected])
        unchanged.append([t for t in g['waterTriangles'] if not region.contains(Point(sum(p[0] for p in t)/3,sum(p[1] for p in t)/3))])
    assert unchanged[0]==unchanged[1],'Unrelated water triangles changed'
    landcover={}
    for key in ['parks','urban','inferredUrban']:
        a=unary_union([Polygon(p[0],p[1:]) for p in before[key]])
        b=unary_union([Polygon(p[0],p[1:]) for p in after[key]])
        error=b.symmetric_difference(a.difference(gained)).area*10000
        assert error<1e-4,(key,error);landcover[key]=error
    affected=[]
    for building in after['buildings']:
        if building['id'] not in source['affectedBuildingIds']:continue
        p=Polygon(building['rings'][0],building['rings'][1:]);area=p.intersection(water).area*10000
        assert abs(area-permitted_water_overlap(source,building['id']))<1e-6,(building['id'],area)
        if building['id'] in identities:
            triangles=[Polygon(t) for t in building['meshRoofTriangles']];roof=unary_union(triangles)
            assert all(t.area>0 for t in triangles)
            assert abs(math.fsum(t.area for t in triangles)-roof.area)*10000<1e-5
            assert p.difference(roof.buffer(.00005)).area<1e-10
            assert roof.difference(p.buffer(.00005)).area<1e-10
        affected.append({'id':building['id'],'waterOverlapSquareMeters':area})
    assert len(affected)==len(source['affectedBuildingIds'])
    footprints=[Polygon(b['rings'][0],b['rings'][1:]) for b in after['buildings']]
    for index in STRtree(footprints).query(gained,predicate='intersects'):
        identity=after['buildings'][index]['id']
        expected=permitted_water_overlap(source,identity)
        if expected:
            # The whole preserved overlap above was checked against the source
            # footprint; only that explicitly layered structure is exempt.
            continue
        assert footprints[index].intersection(gained).area*10000<1e-6,identity
    assert not any(gained.covers(Point(x,y)) for x,y,_ in after['trees']),'A tree stem is newly in water'
    return {'status':'serialized geography checks passed; actual terrain and city acceptance pending',
            'waterPolygons':len(after['water']),'changedWaterIndices':sorted(selected),'changedBuildingIds':sorted(identities),
            'waterTrianglesBefore':len(before['waterTriangles']),'waterTrianglesAfter':len(after['waterTriangles']),
            'waterCoverageDifferenceSquareMeters':area_delta,'waterOverlapSquareMeters':overlap,
            'unchangedWaterTriangles':len(unchanged[0]),
            'removedTreeIndices':sorted(removed),'treesBefore':len(before['trees']),'treesAfter':len(after['trees']),
            'landcoverOutsideChangeDifferenceSquareMeters':landcover,'affectedBuildings':affected}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['before','after','source','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--record-key',choices=['shorelineRestoration','reservoirShorelineRestoration','reservoirRolloutRestoration','reservoirNeighborRestoration'],default='shorelineRestoration')
    args=parser.parse_args();result=check(*[json.loads(getattr(args,name).read_text()) for name in ['before','after','source']],record_key=args.record_key)
    result['inputs']={name:{'path':str(getattr(args,name).resolve()),'sha256':hashlib.sha256(getattr(args,name).read_bytes()).hexdigest()}
                      for name in ['before','after','source']}
    result['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
