"""Plan-view evidence from serialized geometry, not a rendered city preview."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as DrawPath
from matplotlib.patches import PathPatch
from shapely.affinity import translate,scale
from shapely.geometry import Polygon,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def draw(ax,geometry,origin,color,edge=None,width=.7):
    geometry=scale(translate(geometry,-origin[0],-origin[1]),100,100,origin=(0,0))
    polygons=[geometry] if geometry.geom_type=='Polygon' else getattr(geometry,'geoms',[])
    for polygon in polygons:
        if polygon.is_empty or polygon.geom_type!='Polygon':continue
        polygon=orient(polygon);points=[];codes=[]
        for ring in [polygon.exterior,*polygon.interiors]:
            coords=list(ring.coords);points.extend(coords)
            codes.extend([DrawPath.MOVETO]+[DrawPath.LINETO]*(len(coords)-2)+[DrawPath.CLOSEPOLY])
        ax.add_patch(PathPatch(DrawPath(points,codes),facecolor=color,edgecolor=edge or color,lw=width))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['before','after','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source',type=Path,help='Optional restoration manifest; plot each selected footprint')
    args=parser.parse_args();datasets=[json.loads(p.read_text()) for p in [args.before,args.after]]
    groups=[('Tianchi / restaurant',['osm/5ae9b829076de2274e1e']),
            ('Two ponds / adjoining buildings',['osm/4aa0a75908b7f599b5b1','osm/85637fa090a86f54abb5'])]
    if args.source:
        manifest=json.loads(args.source.read_text())
        groups=[(entry['sourceRef'],[entry['id']]) for entry in manifest['buildings']]
        if not groups:raise ValueError('No source footprints to plot')
    fig,axes=plt.subplots(len(groups),2,figsize=(11,4.25*len(groups)),layout='constrained',squeeze=False)
    for row,(title,identities) in enumerate(groups):
        both=[Polygon(b['rings'][0],b['rings'][1:]) for g in datasets for b in g['buildings'] if b['id'] in identities]
        minx,miny,maxx,maxy=unary_union(both).buffer(.22).bounds
        origin=((minx+maxx)/2,(miny+maxy)/2);window=box(minx,miny,maxx,maxy)
        for col,geo in enumerate(datasets):
            ax=axes[row,col];ax.set_facecolor('#f2f1e9')
            water=unary_union([Polygon(r[0],r[1:]) for r in geo['water']]).intersection(window)
            buildings=unary_union([Polygon(b['rings'][0],b['rings'][1:]) for b in geo['buildings'] if b['id'] in identities])
            overlap=water.intersection(buildings)
            draw(ax,water,origin,'#a4cede','#528ca1');draw(ax,buildings,origin,'#d8d4cb','#363c3d',1.1)
            draw(ax,overlap,origin,'#dc785e')
            ax.set_xlim((minx-origin[0])*100,(maxx-origin[0])*100);ax.set_ylim((miny-origin[1])*100,(maxy-origin[1])*100)
            ax.set_aspect('equal');ax.set_xlabel('East from plot centre (m)');ax.set_ylabel('North (m)')
            ax.set_title(title+'\n'+('Previous display geometry' if col==0 else 'Source-restored candidate'))
            ax.text(.02,.98,f'Water / building overlap: {overlap.area*10000:.3f} m²',transform=ax.transAxes,va='top',fontsize=9,
                    bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
            ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Shoreline and footprint restoration\nBlue: water   Grey: building   Red: overlap   |   Plan geometry only',fontsize=13)
    args.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(args.output,dpi=150);plt.close(fig)
    paths=[args.before,args.after,args.output,Path(__file__)]
    if args.source:paths.append(args.source)
    args.output.with_suffix('.json').write_text(json.dumps({'status':'plan-view source diagnosis; terrain/3D acceptance separate',
        'files':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n')
