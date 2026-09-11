"""Site-specific fittings for Zhuxi; OSM IDs retain the interchange topology."""
import math

MAIN_WAYS = {392546693, 392547316, 392547317, 396095205, 959178327, 959178328, 959178329}
RAMP_WAYS = {392546673, 392546674, 392546675, 392546680, 392546682, 392547315,
             392547807, 396095184, 959178330, 959178331, 1036187437}
CONNECTOR_WAYS = {959178351}
WAYS = MAIN_WAYS | RAMP_WAYS | CONNECTOR_WAYS
MATERIAL_KEYS = ['viaduct_metal', 'viaduct_line', 'leaf', 'leaf2', 'leaf3', 'trunk']


def lane_count(osm_id):
    return 3 if osm_id in MAIN_WAYS else 2 if osm_id in RAMP_WAYS else 1 if osm_id in CONNECTOR_WAYS else None


def marking_faces(route, path, levels, lightweight=False):
    """Forward lane arrows follow the retained one-way OSM point order."""
    if route['osmId'] not in WAYS:
        return []
    lanes = lane_count(route['osmId'])
    output = []
    spacing = 1.25 if lightweight else .8
    for k in range(1, math.ceil(path.length / spacing)):
        station = k * spacing
        if station > path.length - .25:
            continue
        if any(abs(path.lengths[j] - station) < .25 for _, stations in route['mergeStations'] for j in stations):
            continue
        for lane in range(lanes):
            offset = -route['width'] + (lane + .5) * 2 * route['width'] / lanes
            # Two shaft triangles and a filled arrowhead, 5.5 m long.
            for triangle in [[(-.025,-.004),(.010,-.004),(.010,.004)],
                             [(-.025,-.004),(.010,.004),(-.025,.004)],
                             [(.004,-.011),(.030,0),(.004,.011)]]:
                face=[]
                for along, side in triangle:
                    s=station+along; j,t=path.section(s)
                    face.append(path.at(s,offset+side,levels[j]*(1-t)+levels[j+1]*t+.002))
                output.append(face)
    return output


def build_details(batch, network):
    """Shared road-layer fittings; compact crowns use a smaller mobile mesh."""
    import hashlib
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    plan=json.loads((root/'data/zhuxi-details.json').read_text())
    for filename,digest in plan['inputHashes'].items():
        assert hashlib.sha256((root/filename).read_bytes()).hexdigest()==digest, f'Rebuild Zhuxi details after changing {filename}'
    profile='smooth' if network.lightweight else 'detail'
    for lamp in plan['lamps'][profile]:
        x,y,z,dx,dy=lamp
        batch.cone(x,y,z,.0018,.0012,.105,'viaduct_metal',5)
        batch.beam((x,y,z+.105),(x+dx*.026,y+dy*.026,z+.115),.0012,'viaduct_metal')
        batch.box(x+dx*.026,y+dy*.026,z+.113,.015,.006,.003,'viaduct_line',angle=math.atan2(dy,dx))
    return {'lamps':len(plan['lamps'][profile]),'trees':len(plan['trees']),'greenIslands':len(plan['islands'])}


def build_greenery(batch, ground, lightweight=False):
    import json
    from pathlib import Path
    from vegetation import build_tree
    plan=json.loads((Path(__file__).resolve().parents[1]/'data/zhuxi-details.json').read_text())
    for i,(x,y,radius) in enumerate(plan['trees']):
        z=ground(x,y)+.003
        build_tree(batch,x,y,z,radius,['leaf','leaf2','leaf3'][i%3],lightweight,
                   crown_height=.055,crown_rise=.042,trunk_radius=.003,trunk_height=.032)
