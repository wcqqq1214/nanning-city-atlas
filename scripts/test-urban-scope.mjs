import assert from 'node:assert/strict';
import { test } from 'node:test';
import { constrainToScope, overviewCenter } from '../lib/city/scope.ts';

test('the overview centers the cropped model instead of the old origin', () => {
  assert.deepEqual(
    overviewCenter({ bounds: [-140, -139, 185, 109] }),
    [22.5, -15],
  );
  assert.deepEqual(overviewCenter(null), [0, 0]);
});

test('panning includes the rectangular background outside the city detail line', () => {
  const overview = {
    bounds: [0, 0, 4, 4],
    urbanScope: {
      core: {
        coordinates: [
          [
            [0, 0],
            [4, 0],
            [4, 1],
            [1, 1],
            [1, 4],
            [0, 4],
            [0, 0],
          ],
        ],
      },
    },
  };
  assert.deepEqual(constrainToScope(0.5, 3, overview), [0.5, 3]);
  assert.deepEqual(constrainToScope(3, 3, overview), [3, 3]);
  assert.deepEqual(constrainToScope(-2, 2, overview), [0, 2]);
  assert.deepEqual(constrainToScope(4, 0, overview), [4, 0]);
});

test('unscoped legacy data retains its rectangular bounds', () => {
  assert.deepEqual(
    constrainToScope(4, -3, { bounds: [-1, -1, 1, 1] }),
    [1, -1],
  );
});
