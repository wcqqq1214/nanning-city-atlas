import test from 'node:test';
import assert from 'node:assert/strict';
import { DetailStream, selectDetails } from '../lib/city/detail-stream.ts';
const tick = () => new Promise((resolve) => setImmediate(resolve));
const asset = (id, layer = 'buildings', bounds = [0, 0, 2, 2]) => ({
  id,
  layer,
  bounds,
  bytes: 100,
  geometryBytes: 1000,
  url: `/${id}.glb`,
});
const view = {
  x: 1,
  y: 1,
  radius: 10,
  selected: null,
  budget: 1e6,
  layers: { buildings: true, roads: true, railways: true },
};

test('选中地标优先，远景只加载被选中细节，隐藏图层不占预算', () => {
  const a = [
    asset('landmark-a'),
    asset('landmark-b'),
    asset('transport-0', 'roads'),
  ];
  const costs = new Map(a.map((v) => [v.id, 100]));
  assert.deepEqual(
    [
      ...selectDetails(
        a,
        { ...view, selected: 'b', budget: 100 },
        costs,
      ).keys(),
    ],
    ['landmark-b'],
  );
  assert.deepEqual(
    [...selectDetails(a, { ...view, radius: 0 }, costs).keys()],
    [],
  );
  assert.deepEqual(
    [...selectDetails(a, { ...view, radius: 0, selected: 'a' }, costs).keys()],
    ['landmark-a'],
  );
  assert.equal(
    selectDetails(
      a,
      { ...view, layers: { buildings: false, roads: false, railways: false } },
      costs,
    ).size,
    0,
  );
  assert.equal(selectDetails(a, { ...view, budget: 99 }, costs).size, 0);
});

test('离开镜头范围释放几何，迟到的已取消资源不会挂入场景', async () => {
  const releases = [],
    attached = [],
    signals = [],
    resolve = [];
  const stream = new DetailStream([asset('a'), asset('b')], {
    load: (a, signal) => {
      signals.push(signal);
      return new Promise((r) => resolve.push(() => r(a)));
    },
    attach: (a) => {
      attached.push(a.id);
      return 100;
    },
    release: (a, ready) => releases.push([a.id, ready]),
    status: () => {},
  });
  stream.update(view);
  resolve[0]();
  await tick();
  assert.equal(stream.loadedCount, 1);
  stream.update({ ...view, x: 100, y: 100 });
  assert.equal(signals[1].aborted, true);
  resolve[1]();
  await tick();
  assert.deepEqual(attached, ['a']);
  assert.deepEqual(releases, [
    ['a', true],
    ['b', false],
  ]);
  assert.equal(stream.geometryBytes, 0);
  stream.dispose();
});

test('细节失败保留基础场景且只在重试后重新请求，销毁释放资源', async () => {
  let calls = 0,
    released = 0;
  const statuses = [];
  const stream = new DetailStream([asset('landmark-a')], {
    load: async (a) => {
      if (++calls === 1) throw new Error('offline');
      return a;
    },
    attach: () => 100,
    release: () => released++,
    status: (s, r) => statuses.push([s, r]),
  });
  stream.update(view);
  await tick();
  stream.update(view);
  await tick();
  assert.equal(calls, 1);
  assert.ok(statuses.some(([, r]) => r));
  stream.retry();
  await tick();
  assert.equal(stream.loadedCount, 1);
  assert.equal(calls, 2);
  stream.dispose();
  assert.equal(released, 1);
  assert.equal(stream.loadedCount, 0);
});

test('解码后实际内存超过预算时会回收，不因压缩文件很小持续占用', async () => {
  let released = 0;
  const stream = new DetailStream([asset('a')], {
    load: async (a) => a,
    attach: () => 2e6,
    release: () => released++,
    status: () => {},
  });
  stream.update(view);
  await tick();
  assert.equal(stream.loadedCount, 0);
  assert.equal(released, 1);
  stream.dispose();
});

test('已排队的背景地标被选中后提升优先级，不必等待其他背景区块', async () => {
  const started = [],
    finish = new Map();
  const stream = new DetailStream(
    ['a', 'b', 'c', 'd'].map((id) => asset(`landmark-${id}`)),
    {
      load: (a) =>
        new Promise((resolve) => {
          started.push(a.id);
          finish.set(a.id, () => resolve(a));
        }),
      attach: () => 100,
      release: () => {},
      status: () => {},
    },
  );
  stream.update(view);
  assert.deepEqual(started, ['landmark-a', 'landmark-b']);
  stream.update({ ...view, selected: 'd' });
  finish.get('landmark-a')();
  await tick();
  assert.equal(started[2], 'landmark-d');
  finish.get('landmark-b')();
  finish.get('landmark-d')();
  await tick();
  finish.get('landmark-c')();
  await tick();
  stream.dispose();
});
