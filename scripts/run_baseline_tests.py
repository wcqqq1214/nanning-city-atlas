"""Run historical comparisons against an explicitly supplied preserved work directory."""
import argparse
import os
from pathlib import Path
import unittest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True,
                        help='Preserved work directory containing urban-structure/ and geodata/')
    args = parser.parse_args()
    root = args.input_root.resolve()
    if not root.is_dir():
        parser.error(f'Input directory does not exist: {root}')
    os.environ['CITY_TEST_INPUT_ROOT'] = str(root)
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent), pattern='baseline_test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
