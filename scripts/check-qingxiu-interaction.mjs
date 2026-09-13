/** Exercise the published landmark focus, layers and quality switching. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH ?? 'playwright');
const output = path.resolve(process.env.CITY_CHECK_OUTPUT ?? 'work/urban-structure/p3/interaction');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const errors = [], records = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
async function ready(profile) {
  await page.waitForFunction(p => {
    const text = document.querySelector('.performance-stats')?.textContent ?? '';
    return text.includes(p) && text.includes('MB');
  }, profile, { timeout: 90000 });
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
  await page.locator('.place-item').filter({ hasText: '青秀山' }).click({ timeout: 90000 });
  await page.getByRole('button', { name: '近景', exact: true }).click();
  for (const [quality, label] of [['detail', '精细'], ['smooth', '流畅']]) {
    await page.getByRole('tab', { name: '环境', exact: true }).click();
    await page.getByRole('radio', { name: label, exact: true }).check();
    await ready(label);
    await page.getByRole('button', { name: '近景', exact: true }).click();
    await page.waitForTimeout(1800);
    assert.equal(await page.getByRole('button', { name: '关闭地标详情' }).count(), 1);
    await capture(`${quality}-focus`);
    await page.getByRole('tab', { name: '图层', exact: true }).click();
    for (const layer of ['林木植被', '道路桥梁', '河流湖泊', '城市建筑']) {
      const control = page.getByRole('switch', { name: new RegExp(`^${layer}`) });
      const before = await capture(`${quality}-${layer}-on`);
      await control.uncheck();
      await page.waitForTimeout(1800);
      assert.equal(await control.getAttribute('aria-checked'), 'false');
      const after = await capture(`${quality}-${layer}-off`);
      if (layer==='河流湖泊') {
        // Hiding animated water leaves a single shadow-refresh frame in the
        // stats; its total calls are not comparable to a later water-only frame.
        const counts = JSON.parse(execFileSync('work/venv/bin/python', ['-c',
          'import sys,json,numpy as np;from PIL import Image\nresult=[]\nfor path in sys.argv[1:]:\n a=np.asarray(Image.open(path).convert("RGB"),dtype=float)[80:960,302:];r,g,b=a[:,:,0],a[:,:,1],a[:,:,2];result.append(int(((r<g*.65)&(b>g*.7)&(g>100)).sum()))\nprint(json.dumps(result))',
          path.join(output, `${quality}-${layer}-on.png`), path.join(output, `${quality}-${layer}-off.png`),
        ], { encoding: 'utf8' }));
        assert.ok(counts[0]>500 && counts[1]<counts[0]*.5, `Visible lake water did not disappear: ${counts}`);
        records.at(-1).waterPixels = { before: counts[0], after: counts[1] };
      } else {
        assert.ok(after < before, `${quality}/${layer}: render calls did not decrease (${before} -> ${after})`);
      }
      await control.check();
      await page.waitForTimeout(1800);
    }
  }
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, 'report.json'), JSON.stringify({ records, errors, checks: ['tower-close-focus', 'both-qualities', 'layer-render-calls', 'lake-pixel-removal'] }, null, 2)+'\n');
  console.log(`PASS: ${records.length} Qingxiu interaction records`);
} finally {
  await browser.close();
}
