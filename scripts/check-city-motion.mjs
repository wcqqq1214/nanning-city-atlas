/** Local before/after camera-orbit comparison; requires the frozen P0 assets. */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
const require = createRequire(import.meta.url);
const { chromium } = require(
  path.resolve('work/urban-structure/browser/node_modules/playwright'),
);
const output = path.resolve(
  process.env.CITY_MOTION_OUTPUT ?? 'work/urban-structure/p1/motion',
);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath:
    process.env.BROWSER_EXECUTABLE ??
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
});
const results = [];
const errors = [];
try {
  for (const quality of ['detail', 'smooth'])
    for (const version of ['before', 'after', 'after', 'before']) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 1140 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      page.on('pageerror', (e) => errors.push(e.message));
      const prefix =
        version === 'before'
          ? (process.env.CITY_BASELINE_PATH ??
              'work/urban-structure/baseline-73edbb7') + '/'
          : process.env.CITY_CANDIDATE_PATH
            ? process.env.CITY_CANDIDATE_PATH + '/'
            : '';
      const suppliedAssets = {};
      await page.route(
        /\/(models\/nanning-city(?:-mobile)?\.glb|data\/(?:overview|landmarks)\.json)(?:\?|$)/,
        async (route) => {
          const url = new URL(route.request().url());
          const pathname = url.pathname.replace(/^.*(?=\/(?:models|data)\/)/, '');
          const file = prefix + 'public' + pathname;
          const body = await readFile(file);
          suppliedAssets[pathname] = { file: path.resolve(file), sha256: createHash('sha256').update(body).digest('hex') };
          await route.fulfill({
            body,
            contentType: url.pathname.endsWith('.glb')
              ? 'model/gltf-binary'
              : 'application/json',
          });
        },
      );
      await page.goto(
        `${process.env.CITY_BASE_URL ?? 'http://localhost:3000'}/inspect/?view=${encodeURIComponent(process.env.CITY_MOTION_VIEW ?? 'residential')}&quality=${quality}&material=lit`,
        { waitUntil: 'networkidle' },
      );
      await page.waitForFunction(
        () =>
          document
            .querySelector('[data-testid="inspection-stage"]')
            ?.getAttribute('data-ready') === 'true',
        null,
        { timeout: 90000 },
      );
      await page.waitForTimeout(1300);
      const stage = page.getByTestId('inspection-stage');
      const downloadPending = page.waitForEvent('download');
      await page
        .getByRole('button', { name: '导出参数 JSON', exact: true })
        .click();
      const download = await downloadPending;
      const file = path.join(
        output,
        `${quality}-${version}-${results.length}.json`,
      );
      await download.saveAs(file);
      const metadata = JSON.parse(await readFile(file, 'utf8'));
      await stage.screenshot({
        path: path.join(output, `${quality}-${version}-${results.length}.png`),
      });
      const rect = await stage.boundingBox();
      const x = rect.x + 640,
        y = rect.y + 400;
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.evaluate(() => {
        window.motionFrames = [];
        window.motionRunning = true;
        let previous = performance.now();
        function tick(now) {
          if (!window.motionRunning) return;
          window.motionFrames.push(now - previous);
          previous = now;
          requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
      const start = Date.now();
      let i = 0;
      while (Date.now() - start < 3500) {
        await page.mouse.move(
          x + 120 * Math.sin(i * 0.065),
          y + 20 * Math.cos(i * 0.065),
        );
        i++;
        await page.waitForTimeout(12);
      }
      await page.mouse.up();
      const frames = await page.evaluate(() => {
        window.motionRunning = false;
        return window.motionFrames.slice(4);
      });
      const endDownloadPending = page.waitForEvent('download');
      await page.getByRole('button', { name: '导出参数 JSON', exact: true }).click();
      const endDownload = await endDownloadPending;
      const endFile = path.join(output, `${quality}-${version}-${results.length}-end.json`);
      await endDownload.saveAs(endFile);
      const endMetadata = JSON.parse(await readFile(endFile, 'utf8'));
      assert.notDeepEqual(endMetadata.settings.camera, metadata.settings.camera, 'Orbit workload did not move the camera');
      assert.equal(metadata.settings.quality, quality);
      assert.ok(frames.length > 50, 'Insufficient continuous frame samples');
      const sorted = frames.sort((a, b) => a - b);
      const quantile = (q) => sorted[Math.floor((sorted.length - 1) * q)];
      results.push({
        version,
        quality,
        loadMs: metadata.renderer.loadMs,
        samples: frames.length,
        medianFrameMs: quantile(0.5),
        p95FrameMs: quantile(0.95),
        over50ms: frames.filter((v) => v > 50).length,
        renderer: metadata.renderer,
        source: metadata.source,
        suppliedAssets,
        cameraBefore: metadata.settings.camera,
        cameraAfter: endMetadata.settings.camera,
      });
      console.log(
        version,
        quality,
        results.at(-1).medianFrameMs,
        results.at(-1).p95FrameMs,
      );
      await context.close();
    }
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, 'report.json'),
    JSON.stringify(
      {
        results,
        errors,
        method:
          'Headless Chrome, 1280×800 DPR1. Local-file routed assets disable browser HTTP caching in both versions. 3.5-second mouse orbit; RAF intervals include UI/scheduling and are not isolated GPU timing. Two runs per version/quality, ABBA order. No mobile device claim.',
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
