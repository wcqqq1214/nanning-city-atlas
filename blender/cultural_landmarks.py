"""Detailed exterior interpretations of Longxiang Pagoda and two Guangxi museums.

Keep the established atlas envelopes and illustrative display enlargement.
The source snapshot locates each place; photographs guide architectural details.
See docs/CULTURAL_LANDMARKS.md for scope, sources and reproducible validation.
"""
import math

SPECS = {
    'qingxiu': {'radius': .4995, 'height': 3.05, 'osmId': 243217636},
    'gx-museum': {'width': 2.35, 'depth': 1.8, 'height': .81, 'osmId': 476559327},
    'ethnic-museum': {'width': 3.5, 'depth': 2.4, 'height': 1.22, 'osmId': 1006681820},
}
MATERIALS = {
    'culture_stone': ('Museum pale limestone', 'd6ccae', .80, .01),
    'culture_light': ('Museum ivory relief', 'e2ddc7', .78, .02),
    'culture_dark': ('Museum recessed joints', '455957', .83, .01),
    'culture_glass': ('Museum blue grey glazing', '66888e', .27, .22),
    'culture_roof': ('Museum silver roof panels', 'b9c3bf', .43, .27),
    'culture_steel': ('Museum exposed silver steel', 'b3c5c7', .35, .40),
    'culture_gold': ('Museum bronze lettering', 'c4a060', .45, .38),
    'culture_paving': ('Cultural landmark paving', 'c8cabb', .95, .00),
    'culture_leaf': ('Museum courtyard planting', '648267', .95, .00),
    'pagoda_wall': ('Longxiang warm brick plaster', 'd7c6ab', .91, .00),
    'pagoda_tile': ('Longxiang green glazed tiles', '386f60', .36, .10),
    'pagoda_edge': ('Longxiang jade eave edges', '69a28a', .44, .08),
    'pagoda_shadow': ('Longxiang recessed openings', '334442', .93, .00),
    'pagoda_wood': ('Longxiang red brown joinery', '825648', .83, .00),
}
KEYS = list(MATERIALS)


def envelope(identity):
    spec=SPECS[identity]
    if 'radius' in spec:
        return [(spec['radius']*math.cos(i*math.tau/8),spec['radius']*math.sin(i*math.tau/8)) for i in range(8)]
    w,d=spec['width']/2,spec['depth']/2
    return [(-w,-d),(w,-d),(w,d),(-w,d)]


def clip_convex(points,ring):
    """Clip a terrain triangle to the counter-clockwise reserved site."""
    for a,b in zip(ring,ring[1:]+ring[:1]):
        def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        output=[]
        for p,q in zip(points,points[1:]+points[:1]):
            dp,dq=side(p),side(q)
            if dp>=0:output.append(p)
            if (dp>=0)!=(dq>=0):
                t=dp/(dp-dq);output.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
        points=output
        if not points:break
    return points


def support_level(identity,x,y,ground_bounds,terrain_grid):
    ring=[(x+u,y+v) for u,v in envelope(identity)]
    west=min(p[0] for p in ring);east=max(p[0] for p in ring)
    south=min(p[1] for p in ring);north=max(p[1] for p in ring)
    points=list(ring)
    # A linear terrain triangle reaches its clipped maximum at a vertex.
    # Sampling a regular grid alone misses narrow crests near museum corners.
    bounds,cols,rows=terrain_grid
    minx,miny,maxx,maxy=bounds
    dx=(maxx-minx)/(cols-1);dy=(maxy-miny)/(rows-1)
    for step in [1,2]:
        imin=math.floor((west-minx)/dx/step)*step
        jmin=math.floor((maxy-north)/dy/step)*step
        for i in range(max(0,imin),min(cols-1,math.ceil((east-minx)/dx)),step):
            for j in range(max(0,jmin),min(rows-1,math.ceil((maxy-south)/dy)),step):
                corners=[(minx+ii*dx,maxy-jj*dy) for ii,jj in
                         [(i,j),(min(i+step,cols-1),j),(min(i+step,cols-1),min(j+step,rows-1)),(i,min(j+step,rows-1))]]
                for indices in [(0,1,2),(0,2,3)]:
                    points.extend(clip_convex([corners[k] for k in indices],ring))
    # Also account for the continuous height function used by other site pieces.
    for i in range(13):
        for j in range(13):
            p=(west+(east-west)*i/12,south+(north-south)*j/12)
            if clip_convex([p],ring):points.append(p)
    return max(ground_bounds(u,v)[1] for u,v in points)+.018


class Mesh:
    def __init__(self,batch,x,y,z,angle=0):
        self.b,self.x,self.y,self.z,self.angle=batch,x,y,z,angle

    def p(self,u,v,h):
        c,s=math.cos(self.angle),math.sin(self.angle)
        return self.x+u*c-v*s,self.y+u*s+v*c,self.z+h

    def child(self,u,v,angle=0,h=0):
        return Mesh(self.b,*self.p(u,v,h),self.angle+angle)

    def face(self,points,key):
        self.b.face([self.p(*p) for p in points],key)

    def box(self,u,v,h,w,d,rise,key='culture_stone',angle=0):
        self.b.box(*self.p(u,v,h),w,d,rise,key,angle=self.angle+angle)

    def beam(self,a,b,r=.002,key='culture_steel'):
        self.b.beam(self.p(*a),self.p(*b),r,key)

    def profile(self,cx,cy,rings,key,n=64,cap=False):
        for (r,z),(rr,zz) in zip(rings,rings[1:]):
            for i in range(n):
                a,b=i*math.tau/n,(i+1)*math.tau/n
                ps=[(cx+r*math.cos(a),cy+r*math.sin(a),z),(cx+r*math.cos(b),cy+r*math.sin(b),z)]
                if rr==0:
                    self.face([*ps,(cx,cy,zz)],key)
                else:
                    self.face([*ps,(cx+rr*math.cos(b),cy+rr*math.sin(b),zz),(cx+rr*math.cos(a),cy+rr*math.sin(a),zz)],key)
        if cap:
            r,z=rings[-1]
            if r>0:
                # Radial triangles avoid skinny ear-clipped caps collapsing in Draco.
                for i in range(n):
                    a,b=i*math.tau/n,(i+1)*math.tau/n
                    self.face([(cx,cy,z),(cx+r*math.cos(a),cy+r*math.sin(a),z),
                               (cx+r*math.cos(b),cy+r*math.sin(b),z)],key)

    def ring(self,cx,cy,r,width,h,rise,key,n=64):
        self.profile(cx,cy,[(r,h),(r,h+rise),(r-width,h+rise),(r-width,h)],key,n)

    def sign(self,text,cx,cy,z,size,key='culture_gold'):
        # Original line glyphs avoid redistributing font files or photo textures.
        glyphs={
            '广': [[(.45,1),(.58,.9)],[(.12,.8),(.96,.8)],[(.2,.8),(.16,.33),(0,.02)]],
            '西': [[(0,.95),(1,.95)],[(.32,.95),(.32,.67),(.21,.3)],[(.66,.95),(.66,.37),(.82,.37)],[(.1,.67),(.9,.67),(.9,.05),(.1,.05),(.1,.67)],[(.1,.2),(.9,.2)]],
            '民': [[(.15,.02),(.15,.94),(.87,.94),(.87,.65),(.15,.65)],[(.15,.4),(.98,.4)],[(.15,.02),(.48,.16)],[(.52,.65),(.57,.29),(.79,.04),(.98,.06),(.97,.21)]],
            '族': [[(.15,1),(.24,.87)],[(0,.78),(.43,.78)],[(.15,.78),(.15,.23),(.02,.03)],[(.16,.55),(.36,.55),(.32,.05),(.2,.05)],[(.58,1),(.45,.69)],[(.55,.85),(1,.85)],[(.62,.71),(.48,.47)],[(.6,.59),(.95,.59)],[(.48,.35),(1,.35)],[(.74,.59),(.71,.27),(.5,.03)],[(.72,.33),(.98,.03)]],
            '博': [[(.16,1),(.16,0)],[(0,.68),(.34,.68)],[(.39,.83),(1,.83)],[(.7,1),(.7,.35)],[(.45,.7),(.94,.7),(.94,.4),(.45,.4),(.45,.7)],[(.45,.55),(.94,.55)],[(.37,.26),(1,.26)],[(.82,.35),(.82,.03),(.67,.03)],[(.48,.19),(.56,.08)],[(.85,.98),(.95,.91)]],
            '物': [[(.11,.85),(.04,.54)],[(.09,.68),(.42,.68)],[(.23,1),(.23,0)],[(0,.31),(.42,.47)],[(.59,1),(.42,.65)],[(.55,.8),(.98,.8),(.91,.07),(.77,.04)],[(.67,.77),(.59,.37),(.41,.18)],[(.82,.77),(.73,.29),(.5,.02)]],
            '馆': [[(.18,1),(.02,.67)],[(.16,.75),(.33,.75),(.26,.6)],[(.15,.54),(.15,.08),(.34,.27)],[(.65,1),(.75,.9)],[(.44,.68),(.44,.86),(.98,.86),(.98,.7)],[(.51,.68),(.9,.68),(.9,.44),(.51,.44),(.51,.68)],[(.51,.44),(.51,.05),(.95,.05),(.95,.31),(.51,.31)]],
            '龙': [[(0,.7),(1,.7)],[(.43,1),(.4,.52),(.25,.16),(.05,.02)],[(.56,.62),(.56,.1),(.82,.02),(.98,.08),(.98,.25)],[(.89,.57),(.48,.15)],[(.66,.96),(.79,.84)]],
            '象': [[(.4,1),(.18,.78),(.78,.78),(.88,.53),(.22,.53),(.18,.78)],[(.5,.78),(.5,.53),(.73,.28),(.69,.02),(.48,.02)],[(.51,.5),(.09,.32)],[(.64,.37),(.12,.12)],[(.71,.3),(.92,.08)],[(.74,.4),(.96,.54)]],
            '塔': [[(.14,.96),(.14,.17)],[(0,.62),(.32,.62)],[(0,.11),(.33,.25)],[(.36,.84),(1,.84)],[(.52,1),(.52,.69)],[(.83,1),(.83,.69)],[(.68,.7),(.37,.41)],[(.68,.7),(1,.41)],[(.48,.42),(.9,.42)],[(.48,.29),(.9,.29),(.9,.05),(.48,.05),(.48,.29)]],
        }
        width=len(text)*size*1.18
        for i,char in enumerate(text):
            for line in glyphs[char]:
                for a,b in zip(line,line[1:]):
                    self.beam((cx-width/2+i*size*1.18+a[0]*size,cy,z+a[1]*size),
                              (cx-width/2+i*size*1.18+b[0]*size,cy,z+b[1]*size),size*.023,key)


def foundation(m,identity,ground_bounds):
    ring=envelope(identity)
    m.face([(*p,0) for p in ring],'culture_paving')
    for a,b in zip(ring,ring[1:]+ring[:1]):
        steps=max(1,math.ceil(math.dist(a,b)/.06))
        for i in range(steps):
            ps=[(a[0]+(b[0]-a[0])*t/steps,a[1]+(b[1]-a[1])*t/steps) for t in [i,i+1]]
            low=[ground_bounds(*m.p(*p,0)[:2])[0]-m.z-.015 for p in ps]
            m.face([(*ps[0],low[0]),(*ps[1],low[1]),(*ps[1],0),(*ps[0],0)],'culture_paving')


def arched_wall(m,width,height,opening,sill,spring):
    """A recessed arch opening with reveal faces and a real curved head."""
    half=opening/2;thickness=.018
    for side in [-1,1]:
        a,b=(-width/2,-half) if side<0 else (half,width/2)
        m.face([(a,0,0),(b,0,0),(b,0,height),(a,0,height)],'pagoda_wall')
    if sill>0:m.face([(-half,0,0),(half,0,0),(half,0,sill),(-half,0,sill)],'pagoda_wall')
    arc=[(half*math.cos(i*math.pi/10),spring+half*math.sin(i*math.pi/10)) for i in range(11)]
    for a,b in zip(arc,arc[1:]):
        m.face([(b[0],0,b[1]),(a[0],0,a[1]),(a[0],0,height),(b[0],0,height)],'pagoda_wall')
        m.face([(a[0],0,a[1]),(b[0],0,b[1]),(b[0],thickness,b[1]),(a[0],thickness,a[1])],'pagoda_wood')
        m.beam((a[0],-.002,a[1]),(b[0],-.002,b[1]),.0035,'culture_light')
    for u in [-half,half]:
        m.face([(u,0,sill),(u,thickness,sill),(u,thickness,spring),(u,0,spring)],'pagoda_wood')
        m.beam((u,-.002,sill),(u,-.002,spring),.0035,'culture_light')
    m.face([(-half,thickness,sill),(half,thickness,sill),*[(u,thickness,h) for u,h in arc]],'pagoda_shadow')


def oct_eave(m,r,z):
    # Curved flared roof strips, with slightly lifted corner tiles.
    profile=[(.90,z+.058),(1.01,z+.025),(1.19,z+.009),(1.30,z+.014)]
    for side in range(8):
        a,b=side*math.tau/8,(side+1)*math.tau/8
        for j in range(6):
            t0,t1=j/6,(j+1)/6
            def p(scale,h,t):
                return (r*scale*((1-t)*math.cos(a)+t*math.cos(b)),
                        r*scale*((1-t)*math.sin(a)+t*math.sin(b)),h+.008*(abs(t-.5)*2)**4)
            for (s,h),(ss,hh) in zip(profile,profile[1:]):
                m.face([p(s,h,t0),p(ss,hh,t0),p(ss,hh,t1),p(s,h,t1)],'pagoda_tile')
            for (s,h),(ss,hh) in zip(profile,profile[1:]):
                m.beam(p(s,h,t0),p(ss,hh,t0),.0018,'pagoda_edge')
        m.beam((r*1.3*math.cos(a),r*1.3*math.sin(a),z+.022),
               (r*1.3*math.cos(b),r*1.3*math.sin(b),z+.022),.005,'pagoda_edge')


def build_pagoda(m):
    m.profile(0,0,[(.45,0),(.45,.055),(.39,.055),(.39,.075)],'pagoda_wall',8,cap=True)
    for floor in range(9):
        r=.365-floor*.024;z=.075+floor*.275
        # Walls are separate facets; arched reveals remain visible in close views.
        for side in range(8):
            a,b=side*math.tau/8,(side+1)*math.tau/8
            aa=(r*math.cos(a),r*math.sin(a));bb=(r*math.cos(b),r*math.sin(b))
            facade=m.child((aa[0]+bb[0])/2,(aa[1]+bb[1])/2,math.atan2(bb[1]-aa[1],bb[0]-aa[0]),z)
            w=math.dist(aa,bb)
            arched_wall(facade,w,.233,w*.29,.025 if floor else 0,.145)
            for u in [-w*.43,w*.43]:facade.box(u,-.003,.006,.008,.010,.212,'culture_light')
            # Delicate green balcony posts and two continuous horizontal rails.
            rr=r*1.15
            for i in range(5):
                t=(i+.25)/5
                u=rr*((1-t)*math.cos(a)+t*math.cos(b));v=rr*((1-t)*math.sin(a)+t*math.sin(b))
                m.beam((u,v,z+.045),(u,v,z+.102),.003,'pagoda_edge')
            for h in [.055,.104]:
                m.beam((rr*math.cos(a),rr*math.sin(a),z+h),(rr*math.cos(b),rr*math.sin(b),z+h),.004,'pagoda_edge')
            if floor>0:
                # Small bells hang from the eight upturned corners.
                q=(r*1.29*math.cos(a),r*1.29*math.sin(a))
                m.beam((*q,z+.019),(*q,z+.002),.0015,'culture_gold')
                m.profile(*q,[(.004,z-.004),(.006,z),(.003,z+.005)],'culture_gold',6,cap=True)
        m.profile(0,0,[(r*1.19,z+.015),(r*1.19,z+.041)],'pagoda_tile',8)
        oct_eave(m,r,z+.209)
    # A curved eight-ridged crown, not a straight cone.
    crown=[(.236,2.518),(.242,2.542),(.178,2.61),(.118,2.72),(.055,2.88),(.019,2.985)]
    m.profile(0,0,crown,'pagoda_tile',64,cap=True)
    for i in range(8):
        a=i*math.tau/8
        for (r,z),(rr,zz) in zip(crown,crown[1:]):
            m.beam((r*math.cos(a),r*math.sin(a),z),(rr*math.cos(a),rr*math.sin(a),zz),.004,'pagoda_edge')
    m.profile(0,0,[(.027,2.986),(.027,3.009),(.012,3.022),(0,3.045)],'culture_gold',12)
    plaque=m.child(0,-.338,0,.16)
    plaque.box(0,-.010,0,.145,.012,.054,'pagoda_wood')
    plaque.sign('龙象塔',0,-.018,.007,.035,'culture_light')


def glazing(m,cx,cy,z,w,h,columns=12,rows=3):
    m.box(cx,cy,z,w,.013,h,'culture_glass')
    for i in range(columns+1):
        m.box(cx-w/2+i*w/columns,cy-.010,z,.003,.008,h,'culture_steel')
    for j in range(1,rows):m.box(cx,cy-.011,z+j*h/rows,w,.009,.003,'culture_steel')


def brocade(m,cx,cy,z,size,rows=2,columns=4,key='culture_light'):
    for i in range(columns):
        for j in range(rows):
            u=cx+(i-(columns-1)/2)*size*1.8;h=z+j*size*1.8
            points=[(u,cy,h+size),(u+size*.67,cy,h),(u,cy,h-size),(u-size*.67,cy,h),(u,cy,h+size)]
            for a,b in zip(points,points[1:]):m.beam(a,b,.0024,key)
            m.box(u,cy,h-.008,.008,.005,.016,key)


def build_gx_museum(m):
    # Long slab with deep eaves, the original north block and a glazed south wing.
    m.box(0,.12,.065,2.14,1.19,.60,'culture_stone')
    m.box(0,.12,.665,2.29,1.32,.035,'culture_light')
    m.box(0,.12,.700,2.23,1.26,.010,'culture_roof')
    # Slightly recessed roof plant and three strip skylights.
    for u in [-.72,0,.72]:
        m.box(u,.28,.711,.36,.33,.055,'culture_roof')
        for i in range(7):m.box(u-.15+i*.05,.28,.768,.015,.27,.006,'culture_dark')
    for u in [-.58,0,.58]:
        m.box(u,-.23,.711,.29,.18,.011,'culture_steel')
        for i in range(5):m.box(u-.116+i*.058,-.23,.723,.049,.155,.004,'culture_glass')
    # Both public faces retain the long rhythm; the north face fronts Minzu Avenue.
    for north in [False,True]:
        front=m.child(0,.716 if north else -.479,math.pi if north else 0)
        glazing(front,0,-.004,.108,2.06,.528,columns=30,rows=5)
        for i in range(23):
            u=-1.01+i*2.02/22
            if abs(u)<.225:continue
            front.box(u,-.027,.115,.027,.043,.526,'culture_light')
            # Warm strips within the tall fins read as recessed brocade bands.
            if i%2==0:brocade(front,u,-.051,.35,.009,rows=6,columns=1)
        front.box(0,-.046,.170,.458,.07,.030,'culture_stone')
        front.box(0,-.018,.22,.405,.018,.36,'culture_glass')
        brocade(front,0,-.034,.36,.024,rows=4,columns=6)
        front.sign('广西博物馆',0,-.075,.207,.050)
        for u in [-.16,-.08,0,.08,.16]:
            front.box(u,-.024,.072,.068,.025,.094,'culture_glass')
            front.box(u,-.044,.074,.003,.008,.087,'culture_gold')
        for i in range(5):front.box(0,-.06-i*.024,.012,.58,.024,.060-i*.010,'culture_paving')
    # Continuous shallow side elevations with visible panel joints.
    for side in [-1,1]:
        wing=m.child(side*1.074,.12,side*math.pi/2)
        glazing(wing,0,-.005,.12,1.15,.51,columns=17,rows=5)
        for i in range(16):wing.box(-.55+i*1.10/15,-.029,.12,.027,.035,.53,'culture_light')
    for u in [-.80,.80]:
        m.box(u,-.755,.005,.37,.17,.035,'culture_light')
        m.box(u,-.755,.040,.34,.14,.025,'culture_leaf')
    # Front forecourt paving joints remain inside the established podium.
    for i in range(13):m.box(-1.08+i*.18,-.815,.002,.002,.15,.002,'culture_roof')


def medallion(m,cx,cy,h,r):
    # Vertical bronze-drum disc, with sun rays and concentric openwork bands.
    for radius in [r,r*.90,r*.70,r*.41]:
        for i in range(48):
            a,b=i*math.tau/48,(i+1)*math.tau/48
            m.beam((cx+radius*math.cos(a),cy,h+radius*math.sin(a)),(cx+radius*math.cos(b),cy,h+radius*math.sin(b)),.004,'culture_steel')
    for i in range(12):
        a=i*math.tau/12
        m.face([(cx+math.cos(a)*r*.1,cy,h+math.sin(a)*r*.1),
                (cx+math.cos(a+.12)*r*.38,cy,h+math.sin(a+.12)*r*.38),
                (cx+math.cos(a-.12)*r*.38,cy,h+math.sin(a-.12)*r*.38)],'culture_steel')
        m.beam((cx+r*.73*math.cos(a),cy,h+r*.73*math.sin(a)),(cx+r*.87*math.cos(a),cy,h+r*.87*math.sin(a)),.005,'culture_steel')


def build_ethnic_museum(m):
    cy=-.36
    # Side wings enclose an open planted court behind the central glass drum.
    for side in [-1,1]:
        wing=m.child(side*1.10,.04,-side*.17)
        wing.box(0,0,.07,.91,1.27,.55,'culture_stone')
        wing.box(0,0,.62,.98,1.32,.025,'culture_light')
        wing.box(0,0,.647,.92,1.25,.010,'culture_roof')
        for front in [-1,1]:
            elevation=wing.child(0,front*.641,math.pi if front>0 else 0)
            glazing(elevation,0,-.008,.445,.85,.086,columns=12,rows=1)
            for u in [-.36,-.24,-.12,0,.12,.24,.36]:elevation.box(u,-.013,.13,.048,.017,.215,'culture_glass')
            elevation.box(0,-.009,.37,.87,.012,.025,'culture_light')
        medallion(wing,0,-.662,.34,.22)
    m.box(0,.81,.07,2.73,.37,.55,'culture_stone')
    # Five shallow concave silver shell roofs sweep along the rear arc.
    for i in range(5):
        roof=m.child((i-2)*.58,.70+.11*(1-abs(i-2)/2),(i-2)*-.075)
        w,d=.55,.58
        roof.box(0,0,.53,w,d,.10,'culture_dark')
        for j in range(12):
            a=-d/2+j*d/12;b=a+d/12
            za=.68+.10*(a/(d/2))**2;zb=.68+.10*(b/(d/2))**2
            roof.face([(-w/2,a,za),(w/2,a,za),(w/2,b,zb),(-w/2,b,zb)],'culture_roof')
            if j%3==0:roof.beam((-w/2,a,za+.002),(w/2,a,za+.002),.002,'culture_steel')
            for u in [-w/2,w/2]:roof.beam((u,a,za),(u,b,zb),.006,'culture_light')
        for u in [-w*.35,w*.35]:roof.box(u,-d*.43,.53,.023,.025,.21,'culture_light')
    # Lower glass cylinder flares into the drum rim, with visible meridian ribs.
    profile=[(.58,.08),(.59,.16),(.565,.31),(.54,.55),(.565,.77),(.605,.91)]
    m.profile(0,cy,profile,'culture_glass',72)
    for r,z in profile[1:]:m.ring(0,cy,r+.003,.006,z,.004,'culture_steel',72)
    for i in range(48):
        a=i*math.tau/48
        for (r,z),(rr,zz) in zip(profile,profile[1:]):
            m.beam((r*math.cos(a),cy+r*math.sin(a),z),(rr*math.cos(a),cy+rr*math.sin(a),zz),.0022,'culture_steel')
    for z in [.22,.40,.48,.64,.71,.84]:
        for (r,h),(rr,hh) in zip(profile,profile[1:]):
            if h<z<hh:m.ring(0,cy,r+(rr-r)*(z-h)/(hh-h)+.004,.006,z,.003,'culture_steel',72)
    # Eight broad curved ribs accentuate the waisted silhouette.
    for i in range(8):
        a=i*math.tau/8
        for (r,z),(rr,zz) in zip(profile,profile[1:]):
            m.beam(((r+.018)*math.cos(a),cy+(r+.018)*math.sin(a),z),((rr+.018)*math.cos(a),cy+(rr+.018)*math.sin(a),zz),.013,'culture_light')
    m.profile(0,cy,[(.691,1.085),(.670,1.155)],'culture_steel',72)
    m.profile(0,cy,[(.601,.91),(.607,.933),(.675,1.084)],'culture_glass',72)
    # Alternating V trusses wrap the lip rather than using a solid cone.
    for i in range(36):
        a=i*math.tau/36;b=(i+1)*math.tau/36;c=(a+b)/2
        m.beam((.608*math.cos(c),cy+.608*math.sin(c),.933),(.690*math.cos(a),cy+.690*math.sin(a),1.078),.006,'culture_light')
        m.beam((.608*math.cos(c),cy+.608*math.sin(c),.933),(.690*math.cos(b),cy+.690*math.sin(b),1.078),.006,'culture_light')
        m.box(.672*math.cos(a),cy+.672*math.sin(a),1.09,.009,.020,.060,'culture_dark',angle=a)
    m.profile(0,cy,[(.67,1.155),(.67,1.174)],'culture_roof',72,cap=True)
    m.ring(0,cy,.48,.13,1.176,.003,'culture_glass',72)
    m.profile(0,cy,[(.155,1.177),(0,1.21)],'culture_roof',36)
    # A curved transparent eyebrow canopy on the public front half.
    for i in range(28):
        a=math.pi+i*math.pi/28;b=math.pi+(i+1)*math.pi/28
        m.face([(.55*math.cos(a),cy+.55*math.sin(a),.225),(.74*math.cos(a),cy+.74*math.sin(a),.193),
                (.74*math.cos(b),cy+.74*math.sin(b),.193),(.55*math.cos(b),cy+.55*math.sin(b),.225)],'culture_glass')
        if i%2==0:m.beam((.54*math.cos(a),cy+.54*math.sin(a),.265),(.74*math.cos(a),cy+.74*math.sin(a),.193),.004,'culture_steel')
    glazing(m,0,cy-.555,.024,.68,.145,columns=8,rows=1)
    m.sign('广西民族博物馆',0,cy-.71,.120,.064)
    for i in range(5):m.box(0,-1.018-i*.030,.005,.81,.030,.060-i*.010,'culture_paving')
    for u in [-.46,.46]:m.box(u,cy-.55,.016,.035,.035,.196,'culture_light')
    # An open court, low planters and a circular ground motif.
    m.box(0,.45,.005,.96,.42,.018,'culture_paving')
    for u,v in [(-.28,.48),(.24,.49),(-.93,-.90),(.93,-.90)]:
        m.box(u,v,.020,.19,.13,.035,'culture_light');m.box(u,v,.055,.165,.108,.028,'culture_leaf')
    for u in [-.64,.64]:
        m.box(u,-1.04,.005,.025,.025,.24,'culture_steel')
        m.ring(u,-1.04,.029,.009,.217,.008,'culture_gold',12)


def build_cultural(batch,identity,x,y,z,ground_bounds):
    m=Mesh(batch,x,y,z)
    foundation(m,identity,ground_bounds)
    {'qingxiu':build_pagoda,'gx-museum':build_gx_museum,'ethnic-museum':build_ethnic_museum}[identity](m)
