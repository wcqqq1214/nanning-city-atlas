"""Explicit local input root for historical comparisons; never substitute current data."""
import os
from pathlib import Path


def baseline_input(relative):
    root = os.environ.get('CITY_TEST_INPUT_ROOT')
    if not root:
        raise RuntimeError('Run npm run test:data:baseline -- --input-root <preserved-work-directory>')
    path = Path(root) / relative
    if not path.exists():
        raise FileNotFoundError(f'Historical input missing: {path}; restore the original baseline/candidate first')
    return path
