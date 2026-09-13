"""One native terrain emitter for the city, context exports and reduction inputs.

Detailed terrain consumes the legacy palette RNG draws exactly as before.
The smooth profile consumes none. Replacements are applied after this native
batch has been validated, so they do not feed back into their own source mesh.
"""
from terrain_reduction_plan import suspended
from site_access_plan import suspended as access_suspended
from site_grading import PLAN as GRADING_PLAN, replaces_cell as replaces_grading_cell
from reservoir_runtime import PLAN as RESERVOIR_PLAN, replaces_cell as replaces_reservoir_cell, input_paths as reservoir_input_paths

# These data determine the native ground before any reduction. Resolved roads,
# bridge heights and forest meshes depend on that ground and must not feed back
# into this manifest. The builder separately requires the forest center/bounds
# to equal geography; only those fields affect its native terrain sampling.
NATIVE_DATA_INPUTS=[
    'public/data/geography.json','public/data/terrain.json','data/landmarks.json',
    'data/nanhu-plan.json','data/qingxiu-terrain-plan.json','data/waterfront-plan.json',
    'data/railways-plan.json','data/stations-plan.json','data/sports-center-footprints.json',
    'data/qingxiu-terrain-source.json',
]
if GRADING_PLAN is not None:NATIVE_DATA_INPUTS+=['data/block-grading-plan.json','data/block-grading-source.json']
NATIVE_DATA_INPUTS+=reservoir_input_paths()


def build(env,lightweight=False):
    with suspended(),access_suspended():return _build_native(env,lightweight)


def _build_native(env,lightweight):
    Batch=env['Batch'];geo=env['GEO'];dem=env['DEM'];cols,rows=env['COLS'],env['ROWS']
    west,south,east,north=geo['bounds'];height=env['height'];rng=env['RNG']
    landcover=dem.get('landcover',env.get('LANDCOVER'))
    replaces_park=env['replaces_terrain_cell'];replaces_local=env['replaces_local_cell'];replaces_mountain=env['replaces_mountain_cell']
    batch=Batch('Terrain',env['TERRAIN_MATERIALS'])
    grading_palette={};reservoir_palette={}
    raw_height=getattr(height,'unpatched',height)
    def grid_height(x,y):
        # The shared height wrapper serves objects placed on the finished pad.
        # Base-grid vertices on the patch boundary must retain their ungraded
        # source values; otherwise neighboring, unreplaced faces also move.
        patched=(GRADING_PLAN is not None and GRADING_PLAN.contains(x,y) or
                 RESERVOIR_PLAN is not None and RESERVOIR_PLAN.contains(x,y))
        return raw_height(x,y) if patched else height(x,y)
    def grading_cell_material(i,j,ii,jj,mobile):
        average=sum(raw_height(west+(east-west)*c/(cols-1),north-(north-south)*r/(rows-1))
                    for c,r in [(i,j),(ii,j),(ii,jj),(i,jj)])/4
        lc=landcover[j*cols+i]
        if lc==1 or average>2.6:return 'hill' if mobile or rng.random()>.22 else 'hillLight'
        return 'bank' if lc==2 else 'ground'
    if not lightweight:
        for j in range(rows-1):
            for i in range(cols-1):
                if replaces_reservoir_cell(i,j):
                    if replaces_park(i,j) or replaces_local(i,j) or replaces_mountain(i,j) or replaces_grading_cell(i,j):
                        raise ValueError('Reservoir overlaps an existing terrain replacement')
                    reservoir_palette[(i,j)]=grading_cell_material(i,j,i+1,j+1,False)
                    continue
                if replaces_grading_cell(i,j):
                    if replaces_park(i,j) or replaces_local(i,j) or replaces_mountain(i,j):raise ValueError('Site grading overlaps an existing terrain replacement')
                    grading_palette[(i,j)]=grading_cell_material(i,j,i+1,j+1,False)
                    continue
                if replaces_park(i,j):continue
                if replaces_local(i,j) or replaces_mountain(i,j):
                    average=sum(env['unpatched_height'](west+(east-west)*ii/(cols-1),north-(north-south)*jj/(rows-1))
                                for ii,jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)])/4
                    if landcover[j*cols+i]==1 or average>2.6:rng.random()
                    continue
                vertices=[]
                for ii,jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]:
                    x=west+(east-west)*ii/(cols-1);y=north-(north-south)*jj/(rows-1)
                    vertices.append((x,y,grid_height(x,y)))
                lc=landcover[j*cols+i];average=sum(p[2] for p in vertices)/4
                key=('hill' if rng.random()>.22 else 'hillLight') if lc==1 or average>2.6 else ('bank' if lc==2 else 'ground')
                batch.face([vertices[0],vertices[2],vertices[1]],key)
                batch.face([vertices[0],vertices[3],vertices[2]],key)
    else:
        ix=sorted(set(range(0,cols,2))|{cols-1});jy=sorted(set(range(0,rows,2))|{rows-1})
        zi0,zj0,zi1,zj1=env['zhenning_terrain_patch'](tuple(geo['bounds']),cols,rows,tuple(geo['center']))
        for j,jj in zip(jy,jy[1:]):
            for i,ii in zip(ix,ix[1:]):
                if replaces_reservoir_cell(i,j):
                    if replaces_park(i,j) or replaces_local(i,j) or replaces_mountain(i,j) or replaces_grading_cell(i,j):
                        raise ValueError('Reservoir overlaps an existing terrain replacement')
                    reservoir_palette[(i,j)]=grading_cell_material(i,j,ii,jj,True)
                    continue
                if replaces_grading_cell(i,j):
                    if replaces_park(i,j) or replaces_local(i,j) or replaces_mountain(i,j):raise ValueError('Site grading overlaps an existing terrain replacement')
                    grading_palette[(i,j)]=grading_cell_material(i,j,ii,jj,True)
                    continue
                if replaces_park(i,j) or replaces_local(i,j) or replaces_mountain(i,j):continue
                refined=zi0<=i<zi1 and zj0<=j<zj1
                cc=list(range(i,ii+1)) if refined else [i,ii];rr=list(range(j,jj+1)) if refined else [j,jj]
                for r0,r1 in zip(rr,rr[1:]):
                    for c0,c1 in zip(cc,cc[1:]):
                        vertices=[]
                        for col,row in [(c0,r0),(c1,r0),(c1,r1),(c0,r1)]:
                            x=west+(east-west)*col/(cols-1);y=north-(north-south)*row/(rows-1)
                            z=env['refined_terrain_height'](col,row,grid_height,geo['bounds'],cols,rows) if refined else grid_height(x,y)
                            vertices.append((x,y,z))
                        lc=landcover[r0*cols+c0]
                        key='hill' if lc==1 or sum(v[2] for v in vertices)/4>2.6 else ('bank' if lc==2 else 'ground')
                        batch.face([vertices[0],vertices[2],vertices[1]],key)
                        batch.face([vertices[0],vertices[3],vertices[2]],key)
    env['build_park_terrain'](batch,env['NANHU_X'],env['NANHU_Y'],height)
    env['build_local_terrain'](batch,height,geo['bounds'],cols,rows,lightweight,env['coarse_terrain_surface'])
    env['build_mountain_terrain'](batch,height,geo['bounds'],cols,rows,lightweight,env['coarse_terrain_surface'])
    if GRADING_PLAN is not None:
        def base_material(x,y):
            step=2 if lightweight else 1
            i=int((x-west)/(east-west)*(cols-1))//step*step
            j=int((north-y)/(north-south)*(rows-1))//step*step
            return grading_palette[(i,j)]
        GRADING_PLAN.build(batch,raw_height,geo['bounds'],cols,rows,lightweight,env['coarse_terrain_surface'],base_material)
    if RESERVOIR_PLAN is not None:
        def reservoir_material(x,y):
            step=2 if lightweight else 1
            i=int((x-west)/(east-west)*(cols-1))//step*step
            j=int((north-y)/(north-south)*(rows-1))//step*step
            return reservoir_palette[(i,j)]
        RESERVOIR_PLAN.build(batch,raw_height,geo['bounds'],cols,rows,lightweight,env['coarse_terrain_surface'],reservoir_material)
    return batch
