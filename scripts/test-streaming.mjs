import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import {
  ResourceQueue,
  withRetry,
  HttpError,
  fetchJson,
  fetchModel,
} from '../lib/city/streaming.ts';
const tick = () => new Promise((resolve) => setImmediate(resolve));
test('加载并发最多两项，等待的精选地标优先于背景区块', async () => {
  const queue = new ResourceQueue(2);
  const started = [];
  const resolvers = {};
  const work = (key) => async () => {
    started.push(key);
    await new Promise((resolve) => (resolvers[key] = resolve));
  };
  const promises = [
    queue.enqueue('a', 2, work('a')),
    queue.enqueue('b', 2, work('b')),
    queue.enqueue('c', 2, work('c')),
    queue.enqueue('library', 0, work('library')),
  ];
  await tick();
  assert.deepEqual(started, ['a', 'b']);
  resolvers.a();
  await tick();
  assert.deepEqual(started, ['a', 'b', 'library']);
  resolvers.b();
  resolvers.library();
  await tick();
  resolvers.c();
  await Promise.all(promises);
  await tick();
  assert.equal(queue.tasks.size, 0);
});
test('离开区块会取消排队和传输中的资源，后续任务仍可运行', async () => {
  const queue = new ResourceQueue(1);
  const started = [];
  const first = queue.enqueue('a', 1, async (signal) => {
    started.push('a');
    await new Promise((_, reject) =>
      signal.addEventListener(
        'abort',
        () => reject(new DOMException('cancel', 'AbortError')),
        { once: true },
      ),
    );
  });
  const second = queue.enqueue('b', 2, async () => {
    started.push('b');
  });
  const checked = Promise.all([
    assert.rejects(first, { name: 'AbortError' }),
    assert.rejects(second, { name: 'AbortError' }),
  ]);
  await tick();
  queue.cancel('b');
  queue.cancel('a');
  await checked;
  await tick();
  await queue.enqueue('c', 0, async () => {
    started.push('c');
  });
  assert.deepEqual(started, ['a', 'c']);
});
test('503 自动重试能恢复；持续失败最多三次；404 不自动重试', async () => {
  const signal = new AbortController().signal;
  let count = 0;
  assert.equal(
    await withRetry(
      async () => {
        if (++count === 1) throw new HttpError(503);
        return 'ok';
      },
      signal,
      [0, 0],
    ),
    'ok',
  );
  assert.equal(count, 2);
  count = 0;
  await assert.rejects(
    withRetry(
      async () => {
        count++;
        throw new HttpError(503);
      },
      signal,
      [0, 0],
    ),
  );
  assert.equal(count, 3);
  count = 0;
  await assert.rejects(
    withRetry(
      async () => {
        count++;
        throw new HttpError(404);
      },
      signal,
      [0, 0],
    ),
  );
  assert.equal(count, 1);
});
test('JSON请求503自动恢复，超时退出并可重试，生命周期取消停止所有后续请求', async (t) => {
  let calls = 0;
  const fake = t.mock.method(globalThis, 'fetch', async () => {
    calls++;
    return calls === 1
      ? new Response('', { status: 503 })
      : Response.json({ ready: true });
  });
  assert.deepEqual(
    await fetchJson(
      'https://example.com/data.json',
      new AbortController().signal,
      { delays: [0, 0] },
    ),
    { ready: true },
  );
  assert.equal(calls, 2);
  calls = 0;
  fake.mock.mockImplementation(async (_url, { signal }) => {
    calls++;
    return new Promise((_, reject) =>
      signal.addEventListener(
        'abort',
        () => reject(new DOMException('Aborted', 'AbortError')),
        { once: true },
      ),
    );
  });
  await assert.rejects(
    fetchJson('https://example.com/hang.json', new AbortController().signal, {
      timeoutMs: 10,
      delays: [0, 0],
    }),
  );
  assert.equal(calls, 3);
  calls = 0;
  const lifetime = new AbortController();
  const pending = fetchJson(
    'https://example.com/cancel.json',
    lifetime.signal,
    { timeoutMs: 1000, delays: [0, 0] },
  );
  lifetime.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(calls, 1);
  fake.mock.mockImplementation(async () => Response.json({ recovered: true }));
  assert.deepEqual(
    await fetchJson(
      'https://example.com/retry.json',
      new AbortController().signal,
    ),
    { recovered: true },
  );
});

test('真实GLB传输：分段重组、503重试、正文超时、取消后停止请求', async (t) => {
  const attempts = new Map();
  const server = createServer((req, res) => {
    const count = (attempts.get(req.url) ?? 0) + 1;
    attempts.set(req.url, count);
    if (req.url === '/retry' && count === 1) {
      res.writeHead(503).end();
      return;
    }
    res.writeHead(200, { 'Content-Type': 'model/gltf-binary' });
    res.write(new Uint8Array([1, 2]));
    if (req.url === '/stall' || req.url === '/cancel') return;
    setImmediate(() => res.end(new Uint8Array([3, 4])));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => {
    server.closeAllConnections();
    server.close();
  });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const progress = [];
  const buffer = await fetchModel(
    `${origin}/retry`,
    4,
    new AbortController().signal,
    (value) => progress.push(value),
    { delays: [0, 0] },
  );
  assert.deepEqual([...new Uint8Array(buffer)], [1, 2, 3, 4]);
  assert.equal(attempts.get('/retry'), 2);
  assert.ok(progress.some((value) => value > 0));
  await assert.rejects(
    fetchModel(`${origin}/stall`, 4, new AbortController().signal, () => {}, {
      timeoutMs: 30,
      delays: [0, 0],
    }),
  );
  assert.equal(attempts.get('/stall'), 3);
  const lifetime = new AbortController();
  await assert.rejects(
    fetchModel(
      `${origin}/cancel`,
      4,
      lifetime.signal,
      (value) => {
        if (value > 0) lifetime.abort();
      },
      { delays: [0, 0] },
    ),
    { name: 'AbortError' },
  );
  assert.equal(attempts.get('/cancel'), 1);
});
