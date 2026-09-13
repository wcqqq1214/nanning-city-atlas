"""Plot the generation mesh and source-grounded terrain sections; decoded exports are audited separately."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.patches import Circle
import rasterio
from scipy.ndimage import map_coordinates

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from mountain_terrain import PLAN, vertex_heights, surface
from forest_canopy import coarse_terrain_surface
from test_waterfront import ground, GEO, DEM


def inspect():
    output=ROOT/'work/urban-structure/p3';output.mkdir(exist_ok=True)
    points=np.asarray(PLAN['points']);triangles=np.asarray(PLAN['triangles'])
    meters=lambda z:(np.asarray(z)-DEM['verticalOffset'])/DEM['verticalExaggeration']*100+DEM['verticalDatumMeters']
    old=np.array([coarse_terrain_surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows']) for x,y in points])
    current=np.array(vertex_heights(ground,tuple(GEO['bounds']),DEM['cols'],DEM['rows'],False,coarse_terrain_surface))
    w,s,e,n=PLAN['bounds'];center=np.asarray(PLAN['towerCenterSceneXY'])
    xy_m=(points-center)*100;mesh=mtri.Triangulation(xy_m[:,0],xy_m[:,1],triangles)
    fig,axes=plt.subplots(2,2,figsize=(14,12),layout='constrained')
    for ax,title,values in [(axes[0,0],'A  P2 coarse display terrain',old),(axes[0,1],'B  P3 generation mesh + mapped paths',current)]:
        layer=ax.tripcolor(mesh,meters(values),shading='gouraud',cmap='terrain',vmin=60,vmax=300,rasterized=True)
        ax.tricontour(mesh,meters(values),levels=np.arange(80,301,20),colors='#384c42',linewidths=.35,alpha=.7)
        ax.add_patch(Circle((0,0),45,fill=False,linestyle='--',color='#a04940',linewidth=1,label='Previous 90 m base'))
        ax.add_patch(Circle((0,0),6,color='#a04940',label='12 m source base'))
        ax.set(xlim=((w-center[0])*100,(e-center[0])*100),ylim=((s-center[1])*100,(n-center[1])*100),xlabel='East from tower / m',ylabel='North from tower / m',title=title)
        ax.set_aspect('equal');ax.set_facecolor('#c3dedd');ax.grid(alpha=.12)
    # Render triangulated paving so courtyards enclosed by a path loop stay open.
    areas=[xy_m[ids] for ids,key in zip(triangles,PLAN['materials']) if key in ['walk','steps','service']]
    axes[0,1].add_collection(PolyCollection(areas,facecolors='#703a24',edgecolors='none',alpha=.85))
    for lake in PLAN['waterBodies']:
        from shapely.geometry import Polygon
        point=Polygon(lake['rings'][0],lake['rings'][1:]).representative_point()
        px,py=(np.asarray([point.x,point.y])-center)*100
        axes[0,1].annotate(f"{lake['levelMeters']:.1f} m",(px,py),xytext=(5,5),textcoords='offset points',fontsize=7,color='#164d66',bbox={'facecolor':'white','alpha':.8,'edgecolor':'none','pad':1})
    axes[0,1].legend(loc='upper left',fontsize=8)
    fig.colorbar(layer,ax=axes[0,:],label='Conditioned display elevation / m in existing DSM datum',shrink=.7)
    sections=[]
    definitions=[('C  East-west section through Longxiang',center+[-8,0],center+[7,0]),
                 ('D  Local tower platform: bounded grading',center+[-1.5,0],center+[1.5,0])]
    with rasterio.open(ROOT/'work/geodata'/Path(PLAN['sourceRasterUrl']).name) as raster:
        raw_grid=raster.read(1).astype(float);cx,cy=GEO['center'];kx=1113.2*np.cos(np.radians(cy))
        for ax,(title,a,b) in zip(axes[1],definitions):
            t=np.linspace(0,1,601);samples=a[None,:]+t[:,None]*(b-a);distance=(t-.5)*np.linalg.norm(b-a)*100
            lon=cx+samples[:,0]/kx;lat=cy+samples[:,1]/1113.2
            raw=map_coordinates(raw_grid,[(lat-raster.transform.f)/raster.transform.e-.5,(lon-raster.transform.c)/raster.transform.a-.5],order=1)
            baseline=meters([coarse_terrain_surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows']) for x,y in samples])
            candidates=[]
            for mobile in [False,True]:
                values=[]
                for x,y in samples:
                    value=surface(x,y,ground,GEO['bounds'],DEM['cols'],DEM['rows'],mobile,coarse_terrain_surface)
                    values.append(np.nan if value is None else value)
                candidates.append(meters(values))
            ax.plot(distance,raw,color='#95958b',linewidth=1,label='Raw GLO-30 DSM')
            ax.plot(distance,baseline,color='#b57935',linewidth=1.6,label='P2 display / detail')
            ax.plot(distance,candidates[0],color='#186651',linewidth=1.8,label='P3 generation / detail')
            ax.plot(distance,candidates[1],color='#2f81a0',linewidth=1,linestyle='--',label='P3 generation / smooth')
            ax.set(title=title,xlabel='Distance along section / m',ylabel='Elevation / m');ax.grid(alpha=.2);ax.legend(fontsize=8)
            sections.append({'name':title,'sceneEndpoints':[a.tolist(),b.tolist()],'distanceMeters':distance.tolist(),
                             'rawDsmMeters':raw.tolist(),'p2DetailMeters':baseline.tolist(),
                             'generationDetailMeters':[float(z) if np.isfinite(z) else None for z in candidates[0]],
                             'generationSmoothMeters':[float(z) if np.isfinite(z) else None for z in candidates[1]],
                             'missingValueMeaning':'Water is excluded from the replacement terrain; null is not an elevation sample.'})
    fig.suptitle('Qingxiu generation mesh: source relief, mapped paths and local platform',fontsize=16)
    fig.savefig(output/'terrain-sections.png',dpi=170);plt.close(fig)
    record={'status':'generation mesh; decoded export accuracy is audited separately','planSha256':hashlib.sha256((ROOT/'data/qingxiu-terrain-plan.json').read_bytes()).hexdigest(),
            'statistics':PLAN['statistics'],'sections':sections,
            'generationVertexChangeMeters':{'min':float((meters(current)-meters(old)).min()),'max':float((meters(current)-meters(old)).max())}}
    (output/'terrain-sections.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='sections'}))


if __name__=='__main__':inspect()
