from pathlib import Path
import numpy as np,json
import shapely
from shapely.geometry import Point,LineString
from shapely.strtree import STRtree
b=Path('work/urban-structure/p5/full-city-review')
p=b/'canopy-nanhu-final-native/nearby-smooth.npz'
f=np.load(p)['triangles'];low=f[:,:,:2].min(axis=1);high=f[:,:,:2].max(axis=1)
f=f[(low[:,0]<56)&(high[:,0]>54.9)&(low[:,1]<-6.8)&(high[:,1]>-7.8)]
vertices=np.unique(f.reshape(-1,3),axis=0);tree=STRtree(shapely.points(vertices[:,:2]));records=[]
for fi,face in enumerate(f):
 for a,c in zip(face,np.roll(face,-1,axis=0)):
  delta=c[:2]-a[:2];l=delta@delta
  if l<1e-12:continue
  line=LineString([a[:2],c[:2]])
  for vi in tree.query(line.buffer(1e-5)):
   v=vertices[vi];t=(v[:2]-a[:2])@delta/l
   if 1e-5<t<1-1e-5 and line.distance(Point(v[:2]))<1e-6:
    dz=v[2]-(a[2]+t*(c[2]-a[2]))
    if abs(dz)>.00001:records.append({'face':fi,'a':a.tolist(),'b':c.tolist(),'vertex':v.tolist(),'heightGapMeters':float(dz*100)})
records.sort(key=lambda r:-abs(r['heightGapMeters']));(b/'nanhu-slit-native-edges.json').write_text(json.dumps({'source':str(p),'triangles':len(f),'mismatches':records},indent=2)+'\n');print(len(f),len(records));print(records[:5])
