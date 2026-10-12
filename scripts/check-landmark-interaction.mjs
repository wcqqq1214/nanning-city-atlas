import {
  withBrowserCheck,
  openPanelTab,
  selectQuality,
  openLandmarkDetails,
} from './browser-check-helpers.mjs';
/** P4 published selection, close focus, tier persistence and layer behavior. */
import assert from 'node:assert/strict';
import { writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';

await withBrowserCheck(
  'landmark-interaction',
  async ({ browser, baseUrl, output, errors, watchPage }) => {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
    });
    watchPage(page);
    const records = [];
    const assets = {};
    for (const file of [
      'public/models/nanning-city.glb',
      'public/models/nanning-city-mobile.glb',
      'public/data/overview.json',
      'public/data/landmarks.json',
    ]) {
      assets[file] = createHash('sha256')
        .update(await readFile(file))
        .digest('hex');
    }
    const sites = [
      ['arts-center', '广西文化艺术中心'],
      ['zhenning', '人民公园 · 镇宁炮台'],
      ['diwang', '地王大厦'],
      ['confucius', '南宁孔庙'],
    ];
    async function ready(label) {
      await page.waitForFunction(
        (p) => {
          const text =
            document.querySelector('.performance-stats')?.textContent ?? '';
          return text.includes(p) && text.includes('MB');
        },
        label,
        { timeout: 90000 },
      );
      await page.waitForTimeout(1800);
    }
    async function capture(id) {
      const stats = await page.getByLabel('场景性能统计').textContent();
      await page.screenshot({ path: path.join(output, `${id}.png`) });
      const calls = Number(stats.match(/(\d+) 次绘制/)[1]);
      records.push({ id, stats, calls });
      return calls;
    }
    await page.goto(`${baseUrl}/?stats=1`, { waitUntil: 'networkidle' });
    for (const [id, name] of sites) {
      await openPanelTab(page, '地点');
      await page
        .locator('.place-item')
        .filter({ hasText: name })
        .click({ timeout: 90000 });
      for (const [quality, label] of [
        ['detail', '精细'],
        ['smooth', '流畅'],
      ]) {
        await selectQuality(page, label);
        await ready(label);
        await openLandmarkDetails(page);
        assert.equal(
          await page.getByRole('article', { name: '地标详情' }).count(),
          1,
        );
        await capture(`${id}-${quality}-focus`);
        await page.getByRole('button', { name: '近景', exact: true }).click();
        await page.waitForTimeout(1800);
        await capture(`${id}-${quality}-close`);
        await openPanelTab(page, '图层');
        for (const layer of ['城市建筑', '河流湖泊']) {
          const control = page.getByRole('switch', {
            name: new RegExp(`^${layer}`),
          });
          const before = await capture(`${id}-${quality}-${layer}-on`);
          await control.uncheck();
          await page.waitForTimeout(1800);
          assert.equal(await control.getAttribute('aria-checked'), 'false');
          const after = await capture(`${id}-${quality}-${layer}-off`);
          if (layer === '城市建筑')
            assert.ok(
              after < before,
              `${id}/${quality}: buildings did not disappear`,
            );
          await control.check();
          await page.waitForTimeout(1800);
        }
      }
    }
    assert.deepEqual(errors, []);
    for (const [file, hash] of Object.entries(assets)) {
      assert.equal(
        createHash('sha256')
          .update(await readFile(file))
          .digest('hex'),
        hash,
        'Assets changed during interaction checks',
      );
    }
    await writeFile(
      path.join(output, 'report.json'),
      JSON.stringify(
        {
          assets,
          records,
          errors,
          checks: [
            'four-site-selection',
            'close-focus',
            'both-qualities',
            'building-layer-draws',
            'water-layer-captures',
          ],
        },
        null,
        2,
      ) + '\n',
    );
    console.log(`PASS: ${records.length} landmark interaction records`);
  },
);
