/** Check actual normal/custom water shaders and UI layers with production captures. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH ?? 'playwright');
const output = path.resolve(process.env.CITY_CHECK_OUTPUT ?? 'work/urban-structure/p5/water-web');
const baseUrl = process.env.CITY_BASE_URL ?? 'http://localhost:3000';
const models = JSON.parse(await readFile(path.join(output, 'models.json'), 'utf8'));
const overview = JSON.parse(await readFile('public/data/overview.json', 'utf8'));
for (const profile of ['detail', 'smooth']) overview.models[profile].bytes = models[profile].bytes;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1500, height: 1120 }, deviceScaleFactor: 1 });
const errors = [], records = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
await page.route('**/models/nanning-city*.glb*', route => route.fulfill({ path: models[route.request().url().includes('-mobile') ? 'smooth' : 'detail'].path, contentType: 'model/gltf-binary' }));
await page.route('**/data/overview.json*', route => route.fulfill({ json: overview }));
// Observe actual GPU water draws, without changing scene state or its materials.
await page.addInitScript(() => {
  const probe = window.waterGpu = { frames: [], frame: 0 };
  const programs = new WeakMap(), locations = new WeakMap(), current = new WeakMap();
  let id = 0;
  const raf = window.requestAnimationFrame;
  window.requestAnimationFrame = cb => raf.call(window, time => { probe.frame++; cb(time); });
  const proto = WebGL2RenderingContext.prototype;
  // oxlint-disable-next-line typescript/unbound-method -- Forwarded with the original WebGL context via .call below.
  const get = proto.getUniformLocation;
  proto.getUniformLocation = function (program, name) {
    const location = get.call(this, program, name);
    if (!programs.has(program)) programs.set(program, { id: ++id, uniforms: {} });
    if (location) locations.set(location, { program: programs.get(program), name });
    return location;
  };
  // oxlint-disable-next-line typescript/unbound-method -- Forwarded with the original WebGL context via .call below.
  const use = proto.useProgram;
  proto.useProgram = function (program) { current.set(this, programs.get(program)); return use.call(this, program); };
  // oxlint-disable-next-line typescript/unbound-method -- Forwarded with the original WebGL context via .call below.
  const uniform = proto.uniform1f;
  proto.uniform1f = function (location, value) {
    const found = locations.get(location);
    if (found) found.program.uniforms[found.name] = value;
    return uniform.call(this, location, value);
  };
  for (const name of ['drawElements', 'drawArrays']) {
    const draw = proto[name];
    proto[name] = function (...args) {
      const program = current.get(this);
      if (program && 'uTime' in program.uniforms && 'uNight' in program.uniforms) {
        probe.frames.push({ frame: probe.frame, program: program.id, time: program.uniforms.uTime, night: program.uniforms.uNight });
        if (probe.frames.length > 2000) probe.frames.splice(0, 1000);
      }
      return draw.apply(this, args);
    };
  }
});
const reset = () => page.evaluate(() => { window.waterGpu.frames = []; });
const draws = () => page.evaluate(() => window.waterGpu.frames);
async function ready(profile) {
  await page.locator('[data-testid="inspection-stage"][data-ready="true"]').waitFor({ timeout: 90000 });
  await page.waitForFunction(p => document.querySelector('output')?.textContent.includes(p), profile);
  await page.waitForTimeout(350);
}
async function capture(id, expectedNight, expectBoth = true) {
  const trace = await draws();
  assert.ok(trace.length, `${id}: no dynamic-water draws`);
  const frames = Object.groupBy(trace, d => d.frame);
  if (expectBoth) assert.ok(Object.values(frames).some(frame => frame.length === 2 && new Set(frame.map(d => d.program)).size === 1), `${id}: both meshes did not draw with one water shader`);
  if (expectedNight !== undefined) assert.ok(trace.slice(-2).every(d => Math.abs(d.night - expectedNight) < 1e-6), `${id}: wrong night uniform`);
  await page.screenshot({ path: path.join(output, `${id}.png`) });
  records.push({ id, waterDraws: trace.length, programs: [...new Set(trace.map(d => d.program))], lastDraws: trace.slice(-4) });
}
try {
  await page.goto(`${baseUrl}/inspect?quality=detail&camera=77,6,94,73.477,0.5,88.852&hour=14`, { waitUntil: 'networkidle' });
  for (const profile of ['detail', 'smooth']) {
    if (profile === 'smooth') await page.getByLabel('模型画质', { exact: true }).selectOption(profile);
    await ready(profile);
    for (const [hour, night] of [[14, 0], [18, (1 / 7) ** 2 * (3 - 2 / 7)], [21, 1]]) {
      await reset();
      // Changing the hour triggers a fresh production frame even for inspection.
      await page.getByLabel('光照时间', { exact: true }).selectOption(String(hour === 14 ? 12 : 14));
      await page.getByLabel('光照时间', { exact: true }).selectOption(String(hour));
      await page.waitForTimeout(350);
      await capture(`${profile}-hour-${hour}`, night);
    }
    for (const mode of ['clay', 'color']) {
      await page.getByLabel('材质检查', { exact: true }).selectOption(mode);
      await page.waitForTimeout(200); await reset();
      await page.getByLabel('材质检查', { exact: true }).selectOption('lit');
      await page.waitForTimeout(300); await capture(`${profile}-${mode}-return`, 1);
    }
  }
  await page.goto(`${baseUrl}/?stats=1`, { waitUntil: 'networkidle' });
  for (const [profile, label] of [['detail', '精细'], ['smooth', '流畅']]) {
    await page.getByRole('tab', { name: '环境', exact: true }).click();
    await page.getByRole('radio', { name: label, exact: true }).check();
    await page.waitForFunction(p => document.querySelector('.performance-stats')?.textContent.includes(p), label, { timeout: 90000 });
    await page.waitForTimeout(600);
    await page.getByRole('tab', { name: '图层', exact: true }).click();
    const water = page.getByRole('switch', { name: /^河流湖泊/ });
    await water.uncheck(); await page.waitForTimeout(350);
    assert.equal(await water.getAttribute('aria-checked'), 'false');
    await reset();
    // Force another production frame with water off; a paused animation alone
    // cannot prove that both water meshes are hidden.
    await page.getByRole('switch', { name: /^林木植被/ }).check();
    await page.getByRole('switch', { name: /^林木植被/ }).uncheck();
    await page.waitForTimeout(350);
    assert.deepEqual(await draws(), [], `${profile}: hidden water still draws`);
    await page.screenshot({ path: path.join(output, `${profile}-water-off.png`) });
    records.push({ id: `${profile}-water-off`, waterDraws: 0 });
    await reset(); await water.check(); await page.waitForTimeout(600);
    await capture(`${profile}-water-on`, undefined);
    if (profile === 'detail') {
      const times = (await draws()).map(d => d.time);
      assert.ok(Math.max(...times) - Math.min(...times) > 0.1, 'Detail water animation did not advance');
      records.at(-1).animationSecondsAdvanced = Math.max(...times) - Math.min(...times);
    }
  }
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, 'browser-report.json'), JSON.stringify({ status: 'actual captured terrain/water through production scene and UI; full city pending', models, records, errors, frameworkIntrospection: 'Vinext endpoint returned404; agent-browser unavailable; existing Playwright/Chrome runtime used' }, null, 2) + '\n');
  console.log(`PASS: ${records.length} water runtime/UI records`);
} finally { await browser.close(); }
