"""Extrude source footprints, including courtyard walls and open roofs.

Placement belongs to the caller: this module does not flatten terrain or certify
site access. Prepared roof triangles must already cover the polygon with holes.
"""
import math


def signed_area(ring):
    x,y=ring[0]
    return math.fsum((a[0]-x)*(b[1]-y)-(b[0]-x)*(a[1]-y) for a,b in zip(ring,ring[1:]))/2


def build_mapped(batch, building, bottom, top, material):
    if not math.isfinite(bottom) or not math.isfinite(top):
        raise ValueError('Building elevations must be finite')
    if top <= bottom:
        return None
    if building.get('qualityGeometry') and 'meshRoofTriangles' not in building:
        raise ValueError('Reprepare this quality candidate with storage-precision roof triangles')
    rings=building['rings']
    roof=building.get('meshRoofTriangles',building['roofTriangles'])
    if not rings or not roof:
        raise ValueError('Mapped building needs footprint and prepared roof')
    oriented=[]
    for index,ring in enumerate(rings):
        if len(ring)<4 or ring[0]!=ring[-1]:
            raise ValueError('Footprint rings must be closed')
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in ring):
            raise ValueError('Footprint positions must be finite XY pairs')
        area=signed_area(ring)
        if abs(area)<1e-12:
            raise ValueError('Degenerate footprint ring')
        # With this winding, the right-hand wall normal faces open space:
        # outward for the outer boundary and inward into each courtyard.
        oriented.append(ring if (area>0)==(index==0) else list(reversed(ring)))
    upper=[];degenerate=0
    for triangle in roof:
        if len(triangle)!=3 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in triangle):
            raise ValueError('Roof positions must be finite XY triangles')
        area=signed_area([*triangle,triangle[0]])
        if abs(area)<1e-12:
            # Rounded source coordinates can leave an Earcut triangle on a
            # straight boundary. Report its omission; never emit a zero-area
            # face whose float32 normal could point in either direction.
            degenerate+=1
            continue
        upper.append(triangle if area>0 else list(reversed(triangle)))
    if not upper:
        raise ValueError('Roof has no nondegenerate triangles')
    # Validate every component before appending any geometry to the shared batch.
    for ring in oriented:
        for a,b in zip(ring,ring[1:]):
            batch.face([(*a,bottom),(*b,bottom),(*b,top),(*a,top)],material)
    for triangle in upper:
        batch.face([(*point,top) for point in triangle],'roof')
    return {'id':building['id'],'bottom':bottom,'top':top,
            'courtyards':len(rings)-1,
            'omittedDegenerateRoofTriangles':degenerate,
            'triangles':2*sum(len(ring)-1 for ring in rings)+len(upper)}
