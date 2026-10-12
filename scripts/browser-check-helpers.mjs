/** Shared environment and browser lifetime for standalone visual checks. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { access, mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const projectRoot = fileURLToPath(new URL('../', import.meta.url));

export async function withBrowserCheck(name, check) {
  const baseUrl = (
    process.env.CITY_BASE_URL ?? 'http://127.0.0.1:4300/nanning-city-atlas'
  ).replace(/\/+$/, '');
  const output = path.resolve(
    projectRoot,
    process.env.CITY_CHECK_OUTPUT ?? `work/checks/${name}`,
  );
  const { chromium } = require(
    process.env.PLAYWRIGHT_MODULE_PATH ?? 'playwright',
  );
  await mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXECUTABLE || undefined,
  });
  const errors = [];
  const watchPage = (page) => {
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('response', (response) => {
      if (response.status() >= 400)
        errors.push(`${response.status()} ${response.url()}`);
    });
  };
  try {
    await check({ browser, baseUrl, output, errors, watchPage });
    assert.deepEqual(errors, [], 'Browser errors');
    await rm(path.join(output, 'failure.json'), { force: true });
  } catch (error) {
    await writeFile(
      path.join(output, 'failure.json'),
      JSON.stringify(
        {
          capturedAt: new Date().toISOString(),
          baseUrl,
          error: String(error),
          errors,
        },
        null,
        2,
      ) + '\n',
    );
    throw error;
  } finally {
    await browser.close();
  }
}

export async function openPanelTab(page, name) {
  const expand = page.getByRole('button', {
    name: '展开浏览面板',
    exact: true,
  });
  if (await expand.isVisible()) await expand.click();
  const back = page.getByRole('button', { name: '返回列表', exact: true });
  if (await back.isVisible()) await back.click();
  await page.getByRole('tab', { name, exact: true }).click();
}

export async function selectQuality(page, label) {
  await openPanelTab(page, '环境');
  const radio = page.getByRole('radio', { name: label, exact: true });
  if (!(await radio.isVisible()))
    await page
      .locator('summary')
      .filter({ hasText: /^画质/ })
      .click();
  await radio.check();
}

export async function openLandmarkDetails(page) {
  await page.getByRole('button', { name: /^继续查看 / }).click();
  await page.getByRole('article', { name: '地标详情' }).waitFor();
}

/** Validate an explicit historical/candidate input before starting a browser. */
export async function requireCityAssets(root) {
  for (const file of [
    'models/nanning-city.glb',
    'models/nanning-city-mobile.glb',
    'data/overview.json',
    'data/landmarks.json',
  ]) {
    await access(path.resolve(root, 'public', file));
  }
}
