"""A ramp landing must be one exterior solid with an exposed marking support."""
import numpy as np
import manifold3d as mf
from prepare_road_solids import prism
from road_collision_checks import intersections
from finish_road_solids import Surface, clear_interface_paint
from types import SimpleNamespace


def test_landing():
    # Sloping ramp enters a wider, horizontal main-road slab at its edge.
    main=np.array([[0.,0.,1.1],[1.,0.,1.1],[1.,.2,1.1],[0.,.2,1.1]])
    ramp=np.array([[.3,-.2,1.3],[.5,-.2,1.3],[.5,.1,1.1],[.3,.1,1.1]])
    ground=np.array([[.6,-.1,1.0],[.8,-.1,1.0],[.8,.25,1.2],[.6,.25,1.2]])
    parts=[]
    for q,owner,kind in [(main,1000000,8),(ramp,0,0),(ground,2000,3)]:
        for ids in [[0,1,2],[0,2,3]]:
            top=q[ids];bottom=top.copy();bottom[:,2]-=.035
            parts.append(prism(top,bottom,owner,kind))
    native=[mf.Manifold.batch_boolean(parts[:2],mf.OpType.Add).to_mesh64(),mf.Manifold.batch_boolean(parts[2:],mf.OpType.Add).to_mesh64()]
    raw=[np.asarray(m.vert_properties)[np.asarray(m.tri_verts)] for m in native]
    assert intersections(raw[0],raw[1],'unresolved landing')['pairs']>0
    merged=mf.Manifold.batch_boolean(parts,mf.OpType.Add)
    assert merged.status()==mf.Error.NoError
    mesh=merged.to_mesh64();faces=np.asarray(mesh.vert_properties)[np.asarray(mesh.tri_verts)];kinds=np.asarray(mesh.face_id)%16
    assert {0,1,2,3,6,7,8,9,10}<=set(kinds),'Main road, ramp and ground approach must retain their material ownership'
    assert intersections(faces,faces,'resolved landing',self_test=True)['pairs']==0
    # The horizontal marking crosses into the ramp. Keep only exposed main road.
    paint=np.array([[[.31,.02,1.102],[.48,.02,1.102],[.48,.08,1.102]]])
    support=Surface(faces[kinds==8]);paint=support.paint(paint,SimpleNamespace(near=lambda face:False))
    assert len(paint)>0
    paint=clear_interface_paint(paint,faces)
    assert len(paint)>0,'Keep the portion of the marking outside the ramp'
    assert intersections(paint,faces,'landing markings')['pairs']==0
    print('PASS: complete Minzu/ramp union, retained ownership and visible markings.')


if __name__=='__main__':test_landing()
