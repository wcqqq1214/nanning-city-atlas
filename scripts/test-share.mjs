import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeShare, decodeShare } from '../lib/city/share.ts';
import { DEFAULT_LAYERS } from '../lib/city/types.ts';
const camera = { position: [20, 40, 60], target: [2, 1, 4], fov: 40, span: 15 };
const options = {
  layers: { ...DEFAULT_LAYERS, water: false },
  hour: 19.5,
  heightScale: 1.2,
  selected: 'nanhu',
  autoRotate: true,
  topDown: false,
};
const bounds = [-200, -200, 200, 200];
test('正式分享保存镜头可见跨度、地点与环境，恢复时不自动旋转', () => {
  const value = decodeShare(encodeShare(camera, options), ['nanhu'], bounds);
  assert.deepEqual(value, {
    camera,
    options: { ...options, autoRotate: false },
  });
});
test('非法镜头和范围外目标不加载，未知图层地点不能污染状态', () => {
  assert.equal(decodeShare('#camera=NaN,2,3,4,5,6&fov=40', [], bounds), null);
  assert.equal(
    decodeShare(
      encodeShare({ ...camera, target: [250, 0, 0] }, options),
      ['nanhu'],
      bounds,
    ),
    null,
  );
  const value = decodeShare(
    encodeShare(camera, options) + '&unused=1',
    [],
    bounds,
  );
  assert.equal(value.options.selected, null);
  assert.equal(Object.hasOwn(value.options.layers, 'unused'), false);
});

test('极近和俯视边界的有效镜头分享后仍可恢复，不因坐标舍入失效', () => {
  for (const distance of [2.4, 1200]) {
    for (const polar of [0.025, Math.PI / 2.12]) {
      const view = {
        position: [
          2 + Math.sin(polar) * distance,
          1 + Math.cos(polar) * distance,
          4,
        ],
        target: [2, 1, 4],
        fov: 40,
      };
      assert.deepEqual(
        decodeShare(encodeShare(view, options), ['nanhu'], bounds)?.camera,
        view,
      );
    }
  }
});
