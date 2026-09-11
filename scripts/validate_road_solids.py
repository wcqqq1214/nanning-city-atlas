"""Regression checks on exported triangles, including sides and inferred buildings.

Crossing centerline heights alone cannot detect folded shoulders or buried decks.
Tests use actual decoded Draco faces; shared edges and sub-5 cm noise are ignored.
Approach solids intentionally enter terrain below their visible road surface;
surface/terrain clearance is checked by the ground/elevated validators instead.
"""
import json
from road_collision_checks import ROOT,decode,intersections

PAIRS=[('deck','deck'),('deck','ground'),('deck','soffit'),
       ('structure','deck'),('structure','ground'),('deck','groundWalls'),
       ('structure','buildings'),('soffit','buildings')]

def validate_road_solids():
    destination=ROOT/'work/road-repair';destination.mkdir(parents=True,exist_ok=True)
    failures=[]
    for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
        groups,digest=decode(filename)
        report={'model':filename,'sha256':digest,'planeToleranceMeters':.05,'edgeToleranceMeters':.05,'minIntersectionMeters':.10,'checks':{}}
        for a,b in PAIRS:
            result=intersections(groups[a],groups[b],profile+' '+a+'/'+b,a==b)
            report['checks'][a+'/'+b]=result
            if result['pairs']:failures.append((profile,a,b,result['pairs']))
        (destination/f'collision-{profile}.json').write_text(json.dumps(report,separators=(',',':')))
    assert not failures,f'Exported road intersections: {failures}'
    print('PASS: both exported models have no road-solid intersections above the stated tolerance.',flush=True)

if __name__=='__main__':validate_road_solids()
