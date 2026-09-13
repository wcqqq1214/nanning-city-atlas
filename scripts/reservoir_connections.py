"""Connected water constraints and bounded preservation of separate lake banks."""
import copy
import math
import numpy as np
from shapely import distance,points
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union


def connect_water_fields(lakes,groups):
    entries={e['geographyWaterIndex']:copy.deepcopy(e) for e,p in lakes}
    shapes={e['geographyWaterIndex']:p for e,p in lakes};used=set()
    for group in groups:
        ids=group['waterIndices']
        if len(ids)<2 or len(ids)!=len(set(ids)) or set(ids)-set(entries) or used.intersection(ids):
            raise ValueError('Connected water group must contain distinct selected waters only once')
        joined=unary_union([shapes[i] for i in ids])
        if joined.geom_type!='Polygon' or abs(sum(shapes[i].area for i in ids)-joined.area)>1e-10:
            raise ValueError('Connected source waters must share edges without area overlap')
        widths={entries[i].get('transitionWidthMeters') for i in ids}
        if len(widths)!=1 or None in widths or any(not entries[i].get('levelRegions') for i in ids):
            raise ValueError('Connected waters require source regions and one transition width')
        regions=[r for i in ids for r in entries[i]['levelRegions']]
        for i in ids:
            entries[i]['levelInfluenceRegions']=regions
            entries[i]['connectedWaterIndices']=[j for j in ids if j!=i]
            entries[i]['waterLevelGroup']=group['id']
        used.update(ids)
    return [(entries[e['geographyWaterIndex']],p) for e,p in lakes]


def protected_banks(geography,lakes,native,qpatch,config):
    width=config.get('preserveUnselectedWaterBanksMeters')
    if width is None:return []
    if not math.isfinite(width) or width<=0:raise ValueError('Positive bank preservation width required')
    selected={e['geographyWaterIndex'] for e,p in lakes};focus=unary_union([p for e,p in lakes]);result=[]
    for index,rings in enumerate(geography['water']):
        if index in selected:continue
        polygon=Polygon(rings[0],rings[1:]);separation=polygon.distance(focus)*100
        if separation>=config['nativeRestoreMeters'] or not native.encode(polygon).intersects(qpatch):continue
        if separation<.005:raise ValueError('Directly connected water must be resolved, not protected as a separate bank')
        transition=min(width,separation/2);hold=min(2,separation/4,transition/2)
        polygon=native.decode(native.encode(polygon))
        result.append(({'geographyWaterIndex':index,'transitionMeters':transition,'holdMeters':hold,
                        'distanceToSelectedWaterMeters':separation,
                        'rings':[[list(p) for p in ring.coords] for ring in [polygon.exterior,*polygon.interiors]]},polygon))
    return result


def protection_weights(xy,banks):
    result=np.ones(len(xy));vertices=points(np.asarray(xy).reshape((-1,2)))
    for entry,polygon in banks:
        d=distance(vertices,polygon)*100
        t=np.clip((d-entry['holdMeters'])/(entry['transitionMeters']-entry['holdMeters']),0,1)
        result=np.minimum(result,t*t*(3-2*t))
    return result


def protected_bank_lines(banks,native,land,bounds,columns,rows):
    """Retain both profiles' original triangle breaks in preserved bank bands."""
    w,s,e,n=bounds;dx=(e-w)/(columns-1);dy=(n-s)/(rows-1);lines=[]
    for entry,polygon in banks:
        band=native.encode(polygon.buffer(entry['transitionMeters']/100)).intersection(land)
        if band.is_empty:continue
        lines.extend([band.boundary,native.encode(polygon.buffer(entry['holdMeters']/100)).intersection(land).boundary])
        a,b,c,d=native.decode(band).bounds
        for step in [1,2]:
            for j in range(max(0,math.floor((n-d)/dy/step)*step),min(rows-1,math.ceil((n-b)/dy/step)*step),step):
                for i in range(max(0,math.floor((a-w)/dx/step)*step),min(columns-1,math.ceil((c-w)/dx/step)*step),step):
                    lines.append(native.encode(LineString([(w+i*dx,n-j*dy),(w+(i+step)*dx,n-(j+step)*dy)])).intersection(band))
    return lines
