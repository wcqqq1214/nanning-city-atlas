"""Inventory every unselected water touched by a reservoir replacement domain."""
import numpy as np
from shapely import distance,points
from shapely.geometry import Polygon,LineString,box
from shapely.ops import polygonize,unary_union
from prepare_block_grading import NativeXYGrid


def audit_interfaces(plan,geography):
    native=NativeXYGrid(plan['bounds'])
    if plan.get('replacementBoundarySegments'):
        domain=unary_union(list(polygonize([LineString(s) for s in plan['replacementBoundarySegments']])))
    else:domain=native.decode(native.encode(box(*plan['bounds'])))
    selected={w['geographyWaterIndex'] for w in plan['waterBodies']}
    selected_water=unary_union([Polygon(geography['water'][i][0],geography['water'][i][1:]) for i in selected])
    vertices=points(np.asarray(plan['points'],dtype=float).reshape((-1,2)));weights=np.asarray(plan['weights'])
    records=[]
    for index,rings in enumerate(geography['water']):
        if index in selected:continue
        water=Polygon(rings[0],rings[1:])
        if water.intersection(domain).area<1e-10:continue
        boundary=native.decode(native.encode(water)).boundary.intersection(domain)
        near=distance(vertices,boundary)<.00005
        maximum=float(weights[near].max()) if near.any() else None
        shared=water.boundary.intersection(selected_water.boundary).intersection(domain).length*100
        unresolved=maximum is None or maximum>1e-12 or shared>1
        records.append({'geographyWaterIndex':index,'boundaryVertexCount':int(near.sum()),
                        'maximumRestoreWeight':maximum,'sharedSelectedBoundaryMeters':shared,
                        'requiresInterfaceResolution':unresolved})
    return {'schemaVersion':1,'method':'all unselected water boundaries in actual native replacement domain; 5 mm vertex proximity',
            'neighbors':records,'unresolvedWaterIndices':[r['geographyWaterIndex'] for r in records if r['requiresInterfaceResolution']]}
