"""Measure the actual shoreline/paving meshes and audit changes outside P2."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from check_urban_block_exports import meshes
from validate_cultural_landmarks import glb
from test_waterfront import ground, GEO, DEM
from local_terrain import PLAN, vertex_heights
from forest_canopy import coarse_terrain_surface

ROOT=Path(__file__).resolve().parents[1]


def main():
    result={}
    source_walk=unary_union([Polygon([PLAN['points'][i] for i in face])
                            for face,key in zip(PLAN['triangles'],PLAN['materials']) if key=='waterfront_paving'])
    # Source geographic data and original elevation arrays are immutable in P2.
    for name in ['geography.json','terrain.json']:
        a=ROOT/'public/data'/name;b=ROOT/'work/urban-structure/baseline-p1/public/data'/name
        assert a.read_bytes()==b.read_bytes(),f'P2 modified original {name}'
    for profile,suffix,budget in [('detail','',26_000_000),('smooth','-mobile',18_000_000)]:
        relative=Path(f'public/models/nanning-city{suffix}.glb')
        old,before=meshes(ROOT/'work/urban-structure/baseline-p1'/relative)
        new,after=meshes(ROOT/relative)
        assert after['bytes']<budget
        changes=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
        # Roads are validated across the whole network by validate_assets.py.
        # This check separately catches unintended model/material RNG propagation.
        allowed={'Terrain_2_1','Buildings_2_1','Vegetation_2_1','Landmark_changyou',
                 'Landmark_yongjiang-bridge','RiverBridge_Details_yongjiang-bridge'}
        unexpected=[n for n in changes if n not in allowed and not n.startswith(('GroundRoads_','ElevatedRoads_','MinzuAvenue_','MinzuAvenue_Details'))]
        assert not unexpected,f'Unexpected changes outside waterfront: {unexpected}'
        assert old['Buildings_3_1']==new['Buildings_3_1'],'P1 residential sample changed'
        doc,decode=glb(ROOT/relative)
        paving=[];wall=[];terrain=[];bridge_deck=[]
        for node in doc['nodes']:
            if node.get('name')=='Landmark_yongjiang-bridge':
                for p in doc['meshes'][node['mesh']]['primitives']:
                    if doc['materials'][p['material']]['name']=='River bridge asphalt':
                        bridge_deck.append(decode(p).points)
            if 'mesh' not in node or not node.get('name','').startswith('Terrain_'):continue
            for p in doc['meshes'][node['mesh']]['primitives']:
                material=doc['materials'][p['material']]['name']
                mesh=decode(p);faces=mesh.points[mesh.faces]
                if material=='Riverside promenade stone':paving.append(faces)
                elif material=='Riverside retaining stone':wall.append(faces)
                else:
                    w,s,e,n=PLAN['bounds'];xy=faces[:,:,[0,2]]*np.array([1,-1]);center=xy.mean(axis=1)
                    take=(center[:,0]>=w)&(center[:,0]<=e)&(center[:,1]>=s)&(center[:,1]<=n)
                    terrain.append(faces[take])
        paving=np.concatenate(paving);wall=np.concatenate(wall);terrain=np.concatenate(terrain+[paving])
        paving_xy=paving[:,:,[0,2]]*np.array([1,-1])
        coverage=unary_union([Polygon(t) for t in paving_xy])
        coverage_error=coverage.symmetric_difference(source_walk).area/source_walk.area
        assert coverage_error<.012,f'Exported promenade coverage error: {coverage_error}'
        # Match known native shared points to both decoded material primitives.
        points=np.asarray(PLAN['points']);ids=PLAN['wallVertexIds']
        land_vertices=terrain.reshape(-1,3);wall_vertices=wall.reshape(-1,3)
        wall_vertices=wall_vertices[wall_vertices[:,1]>PLAN['section']['waterSceneZ']]
        land_tree=cKDTree(land_vertices[:,[0,2]]*np.array([1,-1]))
        wall_tree=cKDTree(wall_vertices[:,[0,2]]*np.array([1,-1]))
        dl,il=land_tree.query(points[ids]);dw,iw=wall_tree.query(points[ids])
        gap=np.linalg.norm(land_vertices[il]-wall_vertices[iw],axis=1)
        assert float(gap.max())<.001,f'Decoded wall/land seam exceeds 10 cm: {gap.max()*100}'
        assert paving[:,:,1].min()>PLAN['section']['waterSceneZ']+.003,'Promenade falls below river stage'
        levels=vertex_heights(ground,tuple(GEO['bounds']),DEM['cols'],DEM['rows'],profile=='smooth',coarse_terrain_surface)
        native_top=np.asarray(levels)[ids]
        assert np.abs(wall_vertices[iw,1]-native_top).max()<.001,'Wall elevation no longer matches its plan'
        bridge_deck=np.concatenate(bridge_deck)
        bridge_range=[float(bridge_deck[:,1].min()),float(bridge_deck[:,1].max())]
        assert .52<bridge_range[0]<=bridge_range[1]<.70,'Export did not use the calibrated Yongjiang bridge'
        result[profile]={'before':before,'after':after,'byteDelta':after['bytes']-before['bytes'],
                         'triangleDelta':after['triangles']-before['triangles'],'changedMeshNodes':changes,
                         'identicalOtherMeshNodes':len(new)-len(changes),'residentialP1Unchanged':True,
                         'pavingCoverageErrorPercent':round(coverage_error*100,4),
                         'maxWallLandSeamCm':round(float(gap.max())*10000,3),
                         'wallSegments':len(ids)-1,'pavingTriangles':len(paving),
                         'bridgeDeckSceneRange':bridge_range,
                         'bridgeDeckAboveDisplayWaterMeters':[(z-PLAN['section']['waterSceneZ'])*100 for z in bridge_range]}
    output=ROOT/'work/urban-structure/p2/exports.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
