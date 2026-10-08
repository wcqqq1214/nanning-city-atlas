"""Keep terrain object ownership in source captures and reduction plans."""
import hashlib
import json
import numpy as np


def partition_digest(names, indices):
    ids = np.asarray(indices)
    if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer):
        raise ValueError('Invalid terrain partition indices')
    if len(names) != len(set(names)) or np.any(ids < 0) or np.any(ids >= len(names)):
        raise ValueError('Invalid terrain partition names or ownership')
    digest = hashlib.sha256(json.dumps(list(names), separators=(',', ':')).encode())
    digest.update(np.asarray(ids, dtype='<i8').tobytes())
    return digest.hexdigest()


def collect_partitioned(objects, collect):
    groups = [obj for obj in sorted(objects, key=lambda obj: obj.name) if obj.type == 'MESH']
    data = [collect([obj]) for obj in groups]
    if not data:
        raise ValueError('No terrain partitions to capture')
    return {'triangles': np.concatenate([d[0] for d in data]),
            'materials': np.concatenate([d[1] for d in data]),
            'cornerNormals': np.concatenate([d[2] for d in data]),
            'partitionNames': [obj.name for obj in groups],
            'partitionIndices': np.concatenate([np.full(len(d[0]), i, dtype=np.int64)
                                                 for i, d in enumerate(data)])}
