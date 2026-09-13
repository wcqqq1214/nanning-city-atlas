"""Source-footprint sluice display geometry, independent of ordinary buildings.

Only the mapped plan and layer are source facts. Bay count, sections, freeboard
and submerged foundation are explicit display estimates, not hydraulic design.
Height callbacks must query the final terrain and water used by the city.
"""
import hashlib
import json
import math
import numpy as np


def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()


class WaterControlStructure:
    def __init__(self,spec,geography):
        self.spec=spec
        building=next((b for b in geography['buildings'] if b['id']==spec['buildingId']),None)
        if (building is None or building.get('use')!='dam' or building.get('sourceRef')!=spec['sourceRef']
                or digest(building['rings'])!=spec['expectedFootprintSha256']):
            raise ValueError('Water-control footprint or identity differs from its source')
        if spec['sourceFeature']['tags'].get('layer')!='1' or spec['isEngineeringDesign'] is not False:
            raise ValueError('Expected an explicitly estimated layer=1 structure')
        if geography['center']!=spec['center'] or spec['metersPerUnit']!=100:
            raise ValueError('Water-control coordinate mismatch')
        if digest(geography['water'][spec['waterIndex']])!=spec['expectedWaterSha256']:
            raise ValueError('Reconcile water-control shoreline source')
        rings=building['rings'];r=rings[0][:-1]
        if len(rings)!=1 or len(r)!=4 or any(not math.isfinite(v) for p in r for v in p):
            raise ValueError('This sluice consumer requires one convex quadrilateral')
        cross=lambda a,b,c:(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
        signs=[cross(r[i],r[(i+1)%4],r[(i+2)%4]) for i in range(4)]
        if not (all(v>0 for v in signs) or all(v<0 for v in signs)):
            raise ValueError('This sluice consumer requires one convex quadrilateral')
        length=lambda a,b:math.hypot(a[0]-b[0],a[1]-b[1])
        i=min(range(2),key=lambda i:length(r[i],r[i+1])+length(r[i+2],r[(i+3)%4]))
        self.a,self.b,self.c,self.d=[r[(i+j)%4] for j in range(4)]
        self.span=(length(self.a,self.d)+length(self.b,self.c))/2
        self.width=(length(self.a,self.b)+length(self.c,self.d))/2
        p=spec['displayParametersMeters'];self.parameters=p
        if any(not math.isfinite(v) or v<=0 for v in p.values()):raise ValueError('Positive finite display dimensions required')
        if type(spec['estimatedBayCount']) is not int or spec['estimatedBayCount']<1:
            raise ValueError('A positive integer bay count is required')
        if p['deckWidth']/100>=self.width or p['abutmentLength']/100>=self.span/3:
            raise ValueError('Display sections do not fit the mapped footprint')
        if p['pierWidth']/100>=self.span/spec['estimatedBayCount']/2:
            raise ValueError('Display piers leave no usable gate opening')

    def xy(self,u,v):
        return tuple((1-u)*((1-v)*self.a[k]+v*self.b[k])+u*((1-v)*self.d[k]+v*self.c[k]) for k in [0,1])

    def footprint(self,u0,u1,v0,v1):return [self.xy(u,v) for u,v in [(u0,v0),(u1,v0),(u1,v1),(u0,v1)]]

    def geometry_on_surfaces(self,surfaces,water_height,final_height=None):
        """Use the same native land meshes for candidate and city integration."""
        if len(surfaces)!=2:raise ValueError('Both terrain profiles are required')
        edge_data={};snapped=[];support_queries=[]
        def ground_bounds(x,y):
            values=[s.sample(x,y) for s in surfaces]
            queries=[(x,y),(x,y)]
            for i,value in enumerate(values):
                if value is not None:continue
                if i not in edge_data:
                    faces=np.asarray(surfaces[i].triangles);a=faces.reshape((-1,3));b=np.roll(faces,-1,axis=1).reshape((-1,3))
                    delta=b[:,:2]-a[:,:2];edge_data[i]=(a,b,delta,np.sum(delta*delta,axis=1))
                a,b,delta,length2=edge_data[i];t=np.clip(np.sum((np.array([x,y])-a[:,:2])*delta,axis=1)/length2,0,1)
                distance=np.linalg.norm(a[:,:2]+t[:,None]*delta-[x,y],axis=1);j=int(np.argmin(distance))
                if distance[j]>.00005:raise ValueError('Sluice approach lies outside its terrain surface')
                values[i]=float(a[j,2]+t[j]*(b[j,2]-a[j,2]));snapped.append(float(distance[j])*100)
                queries[i]=tuple(a[j,:2]+t[j]*delta[j])
            if final_height is not None:
                # The native meshes establish that the query is on land. The
                # active city sampler includes subsequent grading/reduction.
                values=[final_height(*q,bool(i)) for i,q in enumerate(queries)]
                if any(v is None or not math.isfinite(v) for v in values):
                    raise ValueError('Missing finite final land support for water-control structure')
            support_queries.append({'sourceXY':[x,y],'sampleXY':[list(q) for q in queries],'heights':values})
            return min(values),max(values)
        result=self.geometry(ground_bounds,water_height)
        result['shorelineSupportSnapCount']=len(snapped)
        result['maximumShorelineSupportSnapMeters']=max(snapped,default=0)
        result['supportQueries']=support_queries
        result['usesFinalCitySampler']=final_height is not None
        return result

    def geometry(self,ground_bounds,water_height):
        p={k:v/100 for k,v in self.parameters.items()};parts=[]
        water=float(water_height(*self.xy(.5,.5)))
        if not math.isfinite(water):raise ValueError('Structure requires an actual finite city water height')
        def support(ring):
            values=[ground_bounds(*q) for q in [*ring,tuple(sum(q[k] for q in ring)/len(ring) for k in [0,1])]]
            if any(len(v)!=2 or not all(math.isfinite(z) for z in v) or v[0]>v[1] for v in values):
                raise ValueError('Structure requires both final terrain profiles')
            return min(v[0] for v in values),max(v[1] for v in values)
        half=p['deckWidth']/self.width/2;v0,v1=.5-half,.5+half
        run=p['approachLength']/self.span
        bank_rings=[self.footprint(-run,0,v0,v1),self.footprint(1,1+run,v0,v1)]
        bank_support=[support(r) for r in bank_rings]
        deck=max(water+p['deckAboveWater'],max(v[1] for v in bank_support)+p['landingClearance'])
        underside=deck-p['deckThickness'];gate_bottom=water+p['gateOpeningAboveWater']
        if underside<=gate_bottom:raise ValueError('Gate opening exceeds the clear height below the deck')
        def prism(name,ring,bottom,top,key):
            if top<=bottom:raise ValueError('Nonpositive water-control section: '+name)
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1]))
            if area<0:ring=list(reversed(ring))
            low=[(*q,bottom) for q in ring];high=[(*q,top) for q in ring]
            faces=[list(reversed(low)),high]+[[low[i],low[(i+1)%4],high[(i+1)%4],high[i]] for i in range(4)]
            parts.append({'name':name,'material':key,'footprint':ring,'bottom':bottom,'top':top,'faces':faces})
        foundation=min(water-p['foundationBelowWater'],min(v[0] for v in bank_support)-p['foundationEmbed'])
        prism('submerged-sill',self.footprint(0,1,0,1),foundation,water-p['sillBelowWater'],'viaduct_concrete')
        abut=p['abutmentLength']/self.span
        for i,(u0,u1) in enumerate([(0,abut),(1-abut,1)]):
            prism('abutment-'+str(i),self.footprint(u0,u1,0,1),foundation,underside,'viaduct_concrete')
        centers=[i/self.spec['estimatedBayCount'] for i in range(1,self.spec['estimatedBayCount'])]
        pier_half=p['pierWidth']/self.span/2
        for i,u in enumerate(centers):prism('pier-'+str(i),self.footprint(u-pier_half,u+pier_half,v0,v1),foundation,underside,'viaduct_concrete')
        limits=[(abut,centers[0]-pier_half)] if centers else [(abut,1-abut)]
        if centers:limits += [(a+pier_half,b-pier_half) for a,b in zip(centers,centers[1:])]+[(centers[-1]+pier_half,1-abut)]
        gate_half=p['gateThickness']/self.width/2
        for i,(u0,u1) in enumerate(limits):prism('gate-'+str(i),self.footprint(u0,u1,.5-gate_half,.5+gate_half),gate_bottom,underside,'viaduct_metal')
        prism('service-deck',self.footprint(0,1,v0,v1),underside,deck,'viaduct_concrete')
        # Terminal landings follow both actual terrain profiles. Solid steps
        # extend beneath their support; no new water/terrain surface is added.
        approaches=[]
        for side,terminal in enumerate([-run,1+run]):
            end_ring=self.footprint(terminal-.001,terminal+.001,v0,v1);low,high=support(end_ring)
            end=high+p['landingClearance'];rise=deck-end
            count=max(1,math.ceil(rise/p['maximumStepRise']))
            if p['approachLength']/count<p['minimumTread']:raise ValueError('Approach requires a longer sourced land corridor')
            stations=[(-run+i*run/count) if side==0 else (1+i*run/count) for i in range(count+1)]
            for i,(u0,u1) in enumerate(zip(stations,stations[1:])):
                fraction=(i+1)/count if side==0 else 1-i/count
                ring=self.footprint(u0,u1,v0,v1);lo,hi=support(ring);top=end+rise*fraction
                if top<hi:raise ValueError('Approach step is buried in the final terrain')
                prism('approach-%s-%s'%(side,i),ring,lo-p['foundationEmbed'],top,'viaduct_concrete')
            approaches.append({'side':side,'steps':count,'riseMeters':rise*100,'treadMeters':p['approachLength']*100/count,'terminalSupportRange':list((low,high))})
        rail_half=p['railWidth']/self.width/2
        for side,v in enumerate([v0+rail_half,v1-rail_half]):
            prism('handrail-'+str(side),self.footprint(0,1,v-rail_half,v+rail_half),deck+p['railHeight']-p['railWidth'],deck+p['railHeight'],'viaduct_metal')
            count=max(2,math.ceil(self.span/p['postSpacing']))
            post_half=p['railWidth']/self.span/2
            for i in range(count+1):
                u=post_half+(1-2*post_half)*i/count
                prism('post-%s-%s'%(side,i),self.footprint(u-post_half,u+post_half,v-rail_half,v+rail_half),deck,deck+p['railHeight'],'viaduct_metal')
        return {'parts':parts,'waterHeight':water,'deckHeight':deck,'gateBottom':gate_bottom,'deckUnderside':underside,
                'gateOpenings':[{'uRange':[a,b],'centerXY':list(self.xy((a+b)/2,.5)),
                                 'probeXY':[list(self.xy(a+(b-a)*f,.5)) for f in [.25,.5,.75]]} for a,b in limits],
                'openings':len(limits),'spanMeters':self.span*100,'widthMeters':self.width*100,'approaches':approaches,
                'status':'estimated sluice display structure; no engineering or operational claim'}

    def build(self,batch,ground_bounds,water_height):
        result=self.geometry(ground_bounds,water_height)
        for part in result['parts']:
            for face in part['faces']:batch.face(face,part['material'])
        return result
