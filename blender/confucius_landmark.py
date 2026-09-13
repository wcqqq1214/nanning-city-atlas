"""Source-constrained Confucius Temple courts on individual terrain supports.

The sequence, seven-bay main hall and five-metre front columns are documented.
Footprints and secondary heights remain explicit illustrative estimates. No
single large slab or local DEM flattening hides the hillside.
"""
import math
from landmark_sites import SPECS,rect_ring,support_level

MATERIALS={
    'temple_wall':('Temple muted vermilion','ab6859',.92,0),
    'temple_tile':('Temple ochre glazed roof','c4a366',.58,.04),
    'temple_shadow':('Temple recessed timber','594c43',.91,0),
    'temple_stone':('Temple pale stone courts','ceccb7',.96,0),
    'temple_water':('Temple ceremonial pond','75a5a1',.32,.05),
}


def build_confucius(b,x,y,z,ground_bounds,terrain_grid):
    spec=SPECS['confucius'];levels={}
    def slab(rect,level,key='temple_stone'):
        ring=[(x+u/100,y+v/100) for u,v in rect_ring(rect)]
        # Subdivide perimeter foundations so the bottom stays below both meshes.
        perimeter=[]
        for a,c in zip(ring,ring[1:]+ring[:1]):
            count=max(1,math.ceil(math.dist(a,c)/.025))
            perimeter.extend((a[0]+(c[0]-a[0])*i/count,a[1]+(c[1]-a[1])*i/count) for i in range(count))
        b.face([(*p,level) for p in ring],key)
        for a,c in zip(perimeter,perimeter[1:]+perimeter[:1]):
            b.face([(*a,ground_bounds(*a)[0]-.015),(*c,ground_bounds(*c)[0]-.015),(*c,level),(*a,level)],key)

    previous=-math.inf
    for court in spec['courts']:
        rect=court['rectMeters'];ring=[(x+u/100,y+v/100) for u,v in rect_ring(rect)]
        level=max(previous+.025,support_level(ring,ground_bounds,terrain_grid))
        levels[court['id']]=level;previous=level
        if court['id']=='entrance':
            # Four pieces leave the pond physically open in the paving.
            for piece in [[-32,-90,32,-76],[-32,-64,32,-50],[-32,-76,-12,-64],[12,-76,32,-64]]:slab(piece,level)
            pond=[(x+u/100,y+v/100,level-.008) for u,v in rect_ring([-12,-76,12,-64])]
            b.face(pond,'temple_water')
            b.box(x,y-.70,level-.008,.042,.14,.014,'temple_stone')
        else:slab(rect,level)
    for a,c in zip(spec['courts'],spec['courts'][1:]):
        low,high=levels[a['id']],levels[c['id']]
        start,end=a['rectMeters'][3]/100,c['rectMeters'][1]/100
        count=max(2,math.ceil((high-low)/.002))
        depth=(end-start)/count
        for i in range(count):
            cy=y+start+(i+.5)*depth
            top=low+(high-low)*(i+1)/count
            bottom=min(ground_bounds(x,cy)[0]-.015,low-.01)
            b.box(x,cy,bottom,.18,depth+1e-6,top-bottom,'temple_stone')
    def roof(cx,cy,base,w,d,rise):
        e=[(cx-w/2,cy-d/2,base),(cx+w/2,cy-d/2,base),
           (cx+w/2,cy+d/2,base),(cx-w/2,cy+d/2,base)]
        r=[(cx-w*.28,cy,base+rise),(cx+w*.28,cy,base+rise)]
        for face in [(e[0],e[1],r[1],r[0]),(e[1],e[2],r[1]),
                     (e[2],e[3],r[0],r[1]),(e[3],e[0],r[0])]:b.face(face,'temple_tile')
    def hall(item):
        u,v=item['centerMeters'];w,d=[v/100 for v in item['extentMeters']]
        cx,cy=x+u/100,y+v/100;floor=levels[item['court']]+.006
        h=item['columnHeightMeters']/100;rise=item['roofRiseMeters']/100
        # Recessed enclosed hall leaves the front colonnade legible.
        b.box(cx,cy+.02,floor,w*.91,max(.025,d-.04),h,'temple_wall')
        for i in range(item['bays']+1):
            px=cx-w*.46+w*.92*i/item['bays']
            b.cone(px,cy-d/2,floor,.004,.004,h,'temple_wall',8)
        b.box(cx,cy-d/2,floor+h-.003,w,.012,.005,'temple_shadow')
        roof(cx,cy,floor+h,w*1.12,d*1.16,rise)
        if item['id']=='dacheng-hall':
            roof(cx,cy,floor+h+rise*.37,w*.92,d*.88,rise*.90)
    for item in spec['halls']:hall(item)
    for side in [-1,1]:
        for court,cy,depth in [('main-court',-12,28),('main-hall',38,24)]:
            hall({'id':'side-hall','centerMeters':[side*25,cy],'extentMeters':[6,depth],
                  'columnHeightMeters':3.2,'roofRiseMeters':2.0,'court':court,'bays':3})
    floor=levels['entrance']
    # Front ceremonial portals; their openings stay physically clear.
    for yy,span,height in [(-.86,.24,.065),(-.80,.18,.050)]:
        for u in [-span/2,0,span/2]:b.box(x+u,y+yy,floor,.008,.008,height,'temple_stone')
        b.box(x,y+yy,floor+height-.012,span+.025,.011,.014,'temple_stone')
        roof(x,y+yy,floor+height,span+.045,.03,.014)
    return {'anchorLevel':levels['main-court'],'courtLevels':levels,
            'estimatedLayout':True,'sourceAreaSquareMeters':spec['siteAreaReferenceSquareMeters']}
