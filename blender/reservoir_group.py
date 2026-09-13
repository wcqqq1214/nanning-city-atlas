"""A disjoint set of reservoir patches sharing one city coordinate system.

Keep each patch's actual mesh and water sampler. The collection owns grid
cells, not bounding rectangles: excluded cells can belong to another patch.
"""
import re


class ReservoirGroup:
    def __init__(self, plans):
        self.plans=tuple(plans)
        if not self.plans:raise ValueError('A reservoir registry must contain plans')
        self.cells={};names=set();water_ids=set();dam_ids=set()
        for plan in self.plans:
            p=plan.payload;name=p['id']
            if not re.fullmatch(r'[a-z0-9_-]+',name):raise ValueError('Invalid reservoir partition name')
            partition=name.replace('-','_')
            if partition in names:raise ValueError('Duplicate reservoir partition')
            names.add(partition)
            if p['center']!=self.plans[0].payload['center'] or plan.dem!=self.plans[0].dem:
                raise ValueError('Reservoir plans must share city coordinates and terrain')
            for entry in p.get('cellExclusions',[]):
                for key in ['columnRange','rowRange']:
                    lo,hi=entry[key];limit=plan.dem['cols' if key=='columnRange' else 'rows']
                    # Source exclusions can name the full neighboring patch;
                    # only their intersection with this patch removes cells.
                    if any(type(v) is not int or v%2 for v in [lo,hi]) or not 0<=lo<hi<limit:
                        raise ValueError('Reservoir exclusion must align with both profiles inside the city')
            for j in range(*p['rowRange'],2):
                for i in range(*p['columnRange'],2):
                    if not plan.replaces_cell(i,j):continue
                    if (i,j) in self.cells:raise ValueError('Overlapping reservoir replacement cells')
                    self.cells[i,j]=plan
            for entry in p['waterBodies']:
                index=entry['geographyWaterIndex']
                if index in water_ids:raise ValueError('Duplicate reservoir water ownership')
                water_ids.add(index)
            for entry in p['dams']:
                if entry['id'] in dam_ids:raise ValueError('Duplicate reservoir dam ownership')
                dam_ids.add(entry['id'])
        self.dam_ids=frozenset(dam_ids)
        self.water_ids=frozenset(water_ids)

    def replaces_cell(self,i,j):return (i//2*2,j//2*2) in self.cells

    def contains(self,x,y):return any(p.contains(x,y) for p in self.plans)

    @staticmethod
    def _consistent(values):
        values=[v for v in values if v is not None]
        if not values:return None
        if max(values)-min(values)>.00005:
            raise ValueError('Reservoir samplers disagree at a shared boundary by more than 5 mm')
        return values[0]

    def water_level(self,x,y):
        return self._consistent(p.water_level(x,y) for p in self.plans if p.contains(x,y))

    def custom_water_contains(self,x,y):
        return any(p.contains(x,y) and p.custom_water_contains(x,y) for p in self.plans)

    def custom_water_triangles(self):
        return [face for p in self.plans for face in p.custom_water_triangles()]

    def sample(self,x,y,*args):
        return self._consistent(p.sample(x,y,*args) for p in self.plans if p.contains(x,y))

    def build(self,*args):
        for plan in self.plans:plan.build(*args)

    def land_xy_triangles(self):
        for plan in self.plans:
            for ids in plan.payload['triangles']:
                yield [plan.payload['points'][k] for k in ids]
