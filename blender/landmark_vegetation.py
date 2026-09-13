"""Local display correction for the legacy 60–70 m park tree symbols.

These are style parameters, not measured tree dimensions. Shrinking the fort
must also restore a plausible relation to its surrounding symbolic vegetation.
Only individual trees are affected; forest footprints and terrain stay intact.
"""
import math

SETTINGS = {'zhenning': {'coreRadiusMeters': 80, 'transitionMeters': 50,
                         'treeScale': .2, 'status': 'display estimate'}}


def canopy_factor(identity, u, v):
    spec = SETTINGS.get(identity)
    if spec is None:
        return 1.0
    distance = math.hypot(u, v)*100
    t = max(0, min(1, (distance-spec['coreRadiusMeters'])/spec['transitionMeters']))
    t = t*t*(3-2*t)
    return spec['treeScale']+(1-spec['treeScale'])*t
