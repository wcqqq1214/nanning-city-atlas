"""Decode city face arrays using the runtime's missing-normal convention."""
import numpy as np


def face_arrays(mesh):
    positions = np.asarray(mesh.points, dtype=float)[:, [0, 2, 1]].copy()
    positions[:, 1] *= -1
    faces = positions[mesh.faces]
    if mesh.normals is not None:
        normals = np.asarray(mesh.normals, dtype=float)[:, [0, 2, 1]].copy()
        if normals.shape != positions.shape or not np.isfinite(normals).all():
            raise ValueError('Invalid explicit normals')
        normals[:, 1] *= -1
        return faces, normals[mesh.faces]
    normals = np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-15):
        raise ValueError('A degenerate face cannot discard its explicit normals')
    # restoreFlatSurfaceNormals expands indexed faces before computing normals.
    # Averaging shared vertex normals here would check a different surface.
    return faces, np.repeat((normals/lengths[:, None])[:, None, :], 3, axis=1)
