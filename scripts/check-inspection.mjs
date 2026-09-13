/** Real browser checks and fixed-view screenshots for /inspect.
 * npm install --prefix work/urban-structure/browser --no-audit --no-fund playwright
 * PLAYWRIGHT_MODULE_PATH=$PWD/work/urban-structure/browser/node_modules/playwright node scripts/check-inspection.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { INSPECTION_VIEWS } from '../lib/city/inspection.ts';

const require = createRequire(import.meta.url);
const { chromium } = require(
  process.env.PLAYWRIGHT_MODULE_PATH ?? 'playwright',
);
const baseUrl = process.env.CITY_BASE_URL ?? 'http://localhost:3000';
const output = path.resolve(
  process.env.CITY_CHECK_OUTPUT ?? 'work/urban-structure/inspection',
);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath:
    process.env.BROWSER_EXECUTABLE ??
    (process.platform === 'darwin'
      ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
      : undefined),
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 1140 },
  deviceScaleFactor: 1,
});
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text());
});
const records = [];
const baseline = process.env.CITY_CHECK_BASELINE_PATH;
const suppliedAssets = {};
if (baseline) {
  await page.route(
    /\/(models\/nanning-city(?:-mobile)?\.glb|data\/(?:overview|landmarks)\.json)(?:\?|$)/,
    async (route) => {
      const { readFile } = await import('node:fs/promises');
      const pathname = new URL(route.request().url()).pathname.replace(/^.*(?=\/(?:models|data)\/)/, '');
      const file = path.resolve(baseline, `public${pathname}`);
      const body = await readFile(file);
      suppliedAssets[pathname] = { file, sha256: createHash('sha256').update(body).digest('hex') };
      await route.fulfill({ body, contentType: pathname.endsWith('.glb') ? 'model/gltf-binary' : 'application/json' });
    },
  );
}
const views = process.env.CITY_CHECK_VIEW
  ? process.env.CITY_CHECK_VIEW.split(',')
  : Object.keys(INSPECTION_VIEWS);
assert.ok(
  views.every((view) => Object.hasOwn(INSPECTION_VIEWS, view)),
  'Unknown inspection view',
);
const stage = page.getByTestId('inspection-stage');
const manifestButton = page.getByRole('button', {
  name: '导出参数 JSON',
  exact: true,
});

async function settled() {
  await page.waitForFunction(
    () => {
      const element = document.querySelector(
        '[data-testid="inspection-stage"]',
      );
      return (
        element?.getAttribute('data-ready') === 'true' &&
        element.querySelector('canvas')?.width === 1280
      );
    },
    null,
    { timeout: 90000 },
  );
  // Let pending camera/material work and the one-second diagnostic sample finish.
  await page.waitForTimeout(1200);
}

async function record(id) {
  const pending = page.waitForEvent('download');
  await manifestButton.click();
  const download = await pending;
  const target = path.join(output, `${id}.json`);
  await download.saveAs(target);
  const { readFile } = await import('node:fs/promises');
  const data = JSON.parse(await readFile(target, 'utf8'));
  assert.equal(data.canvas.width, 1280);
  assert.equal(data.canvas.height, 800);
  assert.equal(data.canvas.pixelRatio, 1);
  assert.equal(data.canvas.frozenTime, 0);
  assert.equal(data.layers.labels, false);
  assert.ok(data.source.model.includes('?v='));
  records.push({
    id,
    settings: data.settings,
    source: data.source,
    renderer: data.renderer,
  });
  return data;
}

try {
  await page.goto(`${baseUrl}/inspect/?view=residential&material=clay`, {
    waitUntil: 'networkidle',
  });
  await settled();
  const first = await record('restore-before');
  await page.getByLabel('材质检查', { exact: true }).selectOption('color');
  await settled();
  await page.getByLabel('材质检查', { exact: true }).selectOption('lit');
  await page.getByLabel('光照时间', { exact: true }).selectOption('21');
  await settled();
  await page.getByLabel('材质检查', { exact: true }).selectOption('clay');
  await settled();
  const clayA = await stage.screenshot();
  await page.waitForTimeout(1400);
  const clayB = await stage.screenshot();
  assert.deepEqual(
    clayA,
    clayB,
    'A stationary clay view must not change with wall-clock time',
  );
  const saved = await record('restore-link');
  assert.equal(saved.effectiveHour, 14);
  assert.deepEqual(saved.settings.camera, first.settings.camera);
  await page.goto(saved.url, { waitUntil: 'networkidle' });
  await settled();
  const restored = await record('restore-after');
  for (const key of ['position', 'target'])
    restored.settings.camera[key].forEach((value, i) =>
      assert.ok(Math.abs(value - saved.settings.camera[key][i]) < 1e-10),
    );
  assert.equal(restored.settings.material, 'clay');
  assert.equal(restored.settings.hour, 21);
  console.log(
    'Verified material switching, frozen frames and camera-link restoration.',
  );

  for (const quality of ['detail', 'smooth']) {
    await page.getByLabel('模型画质', { exact: true }).selectOption(quality);
    await settled();
    for (const view of views) {
      await page.getByLabel('检查区域', { exact: true }).selectOption(view);
      for (const material of ['clay', 'color', 'lit']) {
        await page
          .getByLabel('材质检查', { exact: true })
          .selectOption(material);
        if (material === 'lit')
          await page.getByLabel('光照时间', { exact: true }).selectOption('14');
        await settled();
        const id = `${view}-${quality}-${material}-h14`;
        await stage.screenshot({ path: path.join(output, `${id}.png`) });
        const data = await record(id);
        assert.equal(data.settings.quality, quality);
        assert.equal(data.settings.material, material);
        assert.equal(data.renderer.profile, quality);
      }
      if (['waterfront', 'arts', 'residential', 'qingxiu', 'qingxiu-tower', 'zhenning-close', 'diwang', 'confucius'].includes(view)) {
        for (const hour of ['18', '21']) {
          await page.getByLabel('光照时间', { exact: true }).selectOption(hour);
          await settled();
          const id = `${view}-${quality}-lit-h${hour}`;
          await stage.screenshot({ path: path.join(output, `${id}.png`) });
          await record(id);
        }
      }
      console.log(`Captured ${quality} / ${view}.`);
    }
  }
  // A frozen asset comparison only tests its inspection views. The current
  // release separately exercises the ordinary application against live assets.
  if (!baseline) {
  await page.goto(`${baseUrl}/?stats=1`, { waitUntil: 'networkidle' });
  await page
    .getByRole('button', { name: '缩小', exact: true })
    .waitFor({ timeout: 90000 });
  await page.waitForFunction(
    () =>
      document.querySelector('.performance-stats')?.textContent?.includes('MB'),
    null,
    { timeout: 90000 },
  );
  await page.screenshot({ path: path.join(output, 'normal-browser.png') });
  assert.equal(
    await page.getByRole('heading', { name: '城市结构 · 视觉检查' }).count(),
    0,
  );
  }
  assert.deepEqual(errors, [], 'Browser console errors');
  await writeFile(
    path.join(output, 'report.json'),
    JSON.stringify(
      {
        baseUrl,
        baseline: baseline ?? null,
        suppliedAssets,
        capturedAt: new Date().toISOString(),
        records,
        errors,
        checks: [
          'material-switching',
          'frozen-frames',
          'camera-roundtrip',
          'both-profiles',
          ...(baseline ? [] : ['normal-home-load']),
        ],
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`Inspection passed: ${records.length} records; ${output}`);
} finally {
  await browser.close();
}
