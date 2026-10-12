"""Reference geometry for validation of clipped native (east/north/up) faces."""
import numpy as np
from scope_city import crop_geometry


def retained_triangles(native, mask):
    points = native.reshape(-1, 3)[:, [0, 2, 1]].copy()
    points[:, 2] *= -1
    faces = np.arange(len(points)).reshape(-1, 3)
    normals = np.tile([0., 1., 0.], (len(points), 1))
    p, _, f, _ = crop_geometry(points, normals, faces, mask)
    if p is None:
        return np.empty((0, 3, 3))
    result = p[f][:, :, [0, 2, 1]].copy()
    result[:, :, 1] *= -1
    return result
