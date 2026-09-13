"""Shared candidate platform surface; the final city supplies its base terrain.

Geometry is a replacement patch, not a paving mesh laid over existing terrain.
Weights vanish at the patch/effect boundary and equal one throughout the pad.
No global plan is loaded: callers must explicitly select a validated plan.
"""


class GradePatch:
    def __init__(self, plan):
        self.plan = plan

    def replaces_cell(self, i, j):
        p = self.plan
        return p['columnRange'][0] <= i < p['columnRange'][1] and p['rowRange'][0] <= j < p['rowRange'][1]

    def levels(self, base):
        return [(1-w)*base(x, y)+w*self.plan['targetSceneZ']
                for (x, y), w in zip(self.plan['points'], self.plan['weights'])]

    def sample(self, x, y, levels):
        p = self.plan; west, south, east, north = p['bounds']
        margin=max(p.get('nativeXYGridSceneUnits',[1e-8]))
        if not (west-margin <= x <= east+margin and south-margin <= y <= north+margin): return None
        grid = p['grid']; i = min(grid['columns']-1, max(0, int((x-west)/grid['dx'])))
        j = min(grid['rows']-1, max(0, int((y-south)/grid['dy'])))
        for di, dj in [(0,0),(-1,0),(0,-1),(1,0),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            for face in p['cells'].get(f'{i+di},{j+dj}', []):
                ids = p['triangles'][face]; a, b, c = [p['points'][k] for k in ids]
                d = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                if abs(d)<1e-12: continue
                u = ((x-a[0])*(c[1]-a[1])-(y-a[1])*(c[0]-a[0]))/d
                v = ((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/d
                if min(u, v, 1-u-v)>=-1e-8:
                    return levels[ids[0]]*(1-u-v)+levels[ids[1]]*u+levels[ids[2]]*v
        return None

    def build(self, batch, base, base_material):
        levels = self.levels(base)
        for ids, material in zip(self.plan['triangles'], self.plan['materials']):
            if material == 'base':
                material = base_material(*[sum(self.plan['points'][i][k] for i in ids)/3 for k in [0, 1]])
            elif material == 'ground':
                a,b,c=[(*self.plan['points'][i],levels[i]) for i in ids]
                u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
                normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                grade=(normal[0]**2+normal[1]**2)**.5/abs(normal[2])
                if grade>self.plan['retainingFaceGradeThreshold'] and any(self.plan['weights'][i]>1e-8 for i in ids):
                    # Steep cut/fill is expressed as a battered retaining face,
                    # sharing the solid terrain vertices rather than an overlay.
                    material='block_retaining'
            batch.face([(*self.plan['points'][i], levels[i]) for i in ids], material)
