/** P4 published selection, close focus, tier persistence and layer behavior. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH ?? 'playwright');
const output = path.resolve(process.env.CITY_CHECK_OUTPUT ?? 'work/urban-structure/p4/interaction');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const errors = [], records = [];
const assets = {};
for (const file of ['public/models/nanning-city.glb', 'public/models/nanning-city-mobile.glb', 'public/data/overview.json', 'public/data/landmarks.json']) {
  assets[file] = createHash('sha256').update(await readFile(file)).digest('hex');
}
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
const sites = [['arts-center', '广西文化艺术中心'], ['zhenning', '人民公园 · 镇宁炮台'], ['diwang', '地王大厦'], ['confucius', '南宁孔庙']];
async function ready(label) {
  await page.waitForFunction(p => {
    const text = document.querySelector('.performance-stats')?.textContent ?? '';
    return text.includes(p) && text.includes('MB');
  }, label, { timeout: 90000 });
  await page.waitForTimeout(1800);
}
async function capture(id) {
  const stats = await page.getByLabel('场景性能统计').textContent();
  await page.screenshot({ path: path.join(output, `${id}.png`) });
  const calls = Number(stats.match(/(\d+) 次绘制/)[1]);
  records.push({ id, stats, calls });
  return calls;
}
try {
  await page.goto(`${process.env.CITY_BASE_URL ?? 'http://localhost:3000'}/?stats=1`, { waitUntil: 'networkidle' });
  for (const [id, name] of sites) {
    await page.getByRole('tab', { name: '探索', exact: true }).click();
    await page.locator('.place-item').filter({ hasText: name }).click({ timeout: 90000 });
    for (const [quality, label] of [['detail', '精细'], ['smooth', '流畅']]) {
      await page.getByRole('tab', { name: '环境', exact: true }).click();
      await page.getByRole('radio', { name: label, exact: true }).check();
      await ready(label);
      assert.equal(await page.getByRole('button', { name: '关闭地标详情' }).count(), 1);
      await capture(`${id}-${quality}-focus`);
      await page.getByRole('button', { name: '近景', exact: true }).click();
      await page.waitForTimeout(1800);
      await capture(`${id}-${quality}-close`);
      await page.getByRole('tab', { name: '图层', exact: true }).click();
      for (const layer of ['城市建筑', '河流湖泊']) {
        const control = page.getByRole('switch', { name: new RegExp(`^${layer}`) });
        const before = await capture(`${id}-${quality}-${layer}-on`);
        await control.uncheck();
        await page.waitForTimeout(1800);
        assert.equal(await control.getAttribute('aria-checked'), 'false');
        const after = await capture(`${id}-${quality}-${layer}-off`);
        if (layer === '城市建筑') assert.ok(after < before, `${id}/${quality}: buildings did not disappear`);
        await control.check();
        await page.waitForTimeout(1800);
      }
    }
  }
  assert.deepEqual(errors, []);
  for (const [file, hash] of Object.entries(assets)) {
    assert.equal(createHash('sha256').update(await readFile(file)).digest('hex'), hash, 'Assets changed during interaction checks');
  }
  await writeFile(path.join(output, 'report.json'), JSON.stringify({ assets, records, errors, checks: ['four-site-selection', 'close-focus', 'both-qualities', 'building-layer-draws', 'water-layer-captures'] }, null, 2)+'\n');
  console.log(`PASS: ${records.length} landmark interaction records`);
} finally {
  await browser.close();
}
