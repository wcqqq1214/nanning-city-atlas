"""Prepare paired bridge centrelines without changing the underlying OSM snapshot."""
import hashlib
import json
import math
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    source = json.loads((ROOT/'data/bridges-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    water = unary_union([Polygon(p[0], p[1:]) for p in geo['water']])
    output = []
    for spec in source['bridges']:
        chains = spec.get('chains', [[i] for i, r in enumerate(geo['roads'])
                                   if r['name'] == spec['name'] and r['bridge']])
        assert len(chains) == 2, f"Expected two carriageways: {spec['name']}"
        # Explicit chains also identify unnamed bridges; check their expected OSM
        # name against the hash-pinned geography instead of matching every blank.
        for chain in chains:
            for index in chain:
                road = geo['roads'][index]
                assert road['bridge'] and road['name'] == spec.get('osmName', spec['name']), spec['name']
        lines = []
        for chain in chains:
            points = list(geo['roads'][chain[0]]['points'])
            for index in chain[1:]:
                extra = list(geo['roads'][index]['points'])
                # Connect exact shared endpoints; never invent a link across a gap.
                if points[0] in (extra[0], extra[-1]): points.reverse()
                if points[-1] == extra[-1]: extra.reverse()
                assert points[-1] == extra[0], spec['name']
                points.extend(extra[1:])
            if points[0] > points[-1]: points.reverse()
            lines.append(LineString(points))
        assert max(lines[0].hausdorff_distance(lines[1]), 0) < .35
        n = max(2, math.ceil(max(l.length for l in lines)/.08))
        points = []
        for i in range(n+1):
            a, b = [l.interpolate(i/n, normalized=True) for l in lines]
            points.append([round((a.x+b.x)/2, 6), round((a.y+b.y)/2, 6)])
        line = LineString(points)
        wet = line.intersection(water)
        parts = [wet] if wet.geom_type == 'LineString' else list(wet.geoms)
        main_water = max((p for p in parts if p.geom_type == 'LineString'), key=lambda p:p.length)
        stations = sorted(line.project(Point(p)) for p in main_water.coords)
        center = (stations[0]+stations[-1])/2
        span = sum(spec['spansMeters'])/100
        start = max(.06, min(line.length-span-.06, center-span/2))
        assert 0 < start < start+span < line.length
        output.append({**spec, 'points': points, 'roadIndices':sum(chains, []),
                       'length':line.length, 'mainStart':start, 'mainEnd':start+span,
                       'waterRange':[stations[0],stations[-1]]})
    plan = {'sceneCenter':geo['center'],'osmTimestamp':geo['osmTimestamp'],
            'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                           for p in ['data/bridges-source.json','public/data/geography.json']},
            'bridges':output}
    (ROOT/'data/bridges-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',',':'))+'\n')
    # Generate only this module's catalogue entries; preserve every existing place.
    catalog = json.loads((ROOT/'data/landmarks.json').read_text())
    ids = {b['id'] for b in output}
    catalog = [p for p in catalog if p['id'] not in ids]
    entries=[]
    for b in output:
        p=LineString(b['points']).interpolate((b['mainStart']+b['mainEnd'])/2)
        a,c=b['points'][0],b['points'][-1]
        entries.append({'id':b['id'],'name':b['name'],
            'lon':round(geo['center'][0]+p.x/(1113.2*math.cos(math.radians(geo['center'][1]))),7),
            'lat':round(geo['center'][1]+p.y/1113.2,7), 'category':'邕江桥梁',
            'description':b['description']+' 模型尺寸与细节为沙盘近似。',
            'anchorHeight':max(.5,b['displayRise']+.15),'cameraDistance':max(10,b['length']*1.25),
            'closeDistance':max(4.5,(b['mainEnd']-b['mainStart'])*1.45),
            'cameraBearing':round(math.degrees(math.atan2(c[0]-a[0],c[1]-a[1]))+60,1)%360,
            'modelled':True,'layer':'roads','sourceUrl':source['sources'][b['source']]['url']})
    i=next(i for i,p in enumerate(catalog) if p['id']=='bridge')
    catalog[i+1:i+1]=entries
    (ROOT/'data/landmarks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    print(f'Prepared {len(output)} bridges; replaced {sum(len(b["roadIndices"]) for b in output)} road strips.')


if __name__ == '__main__': prepare()
