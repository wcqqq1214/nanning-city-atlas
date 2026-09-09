import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { assetUrl } from '../lib/city/assets.ts';

const originalBase = process.env.NEXT_PUBLIC_BASE_PATH;
after(() => {
  if (originalBase === undefined) delete process.env.NEXT_PUBLIC_BASE_PATH;
  else process.env.NEXT_PUBLIC_BASE_PATH = originalBase;
  delete globalThis.__CITY_ASSET_VERSION__;
});

test('a new city release bypasses cached models and geographic data', () => {
  process.env.NEXT_PUBLIC_BASE_PATH = '/nanning-city-atlas';
  const paths = [
    '/models/nanning-city.glb',
    '/models/nanning-city-mobile.glb',
    '/data/landmarks.json',
    '/data/overview.json',
  ];
  // Vite replaces this build constant; separate values represent two releases.
  globalThis.__CITY_ASSET_VERSION__ = 'previous-city';
  const cached = paths.map(assetUrl);
  globalThis.__CITY_ASSET_VERSION__ = 'updated-city';
  paths.forEach((path, index) => {
    const current = assetUrl(path);
    assert.notEqual(current, cached[index], `Old cache is still used for ${path}`);
    const url = new URL(current, 'https://example.test');
    assert.equal(url.pathname, `/nanning-city-atlas${path}`);
    assert.equal(url.searchParams.get('v'), 'updated-city');
    assert.equal(assetUrl(path), current, 'Unchanged releases should reuse cache');
  });
});

test('root hosting works and decoder directories remain valid URL prefixes', () => {
  delete process.env.NEXT_PUBLIC_BASE_PATH;
  globalThis.__CITY_ASSET_VERSION__ = 'current-city';
  assert.equal(assetUrl('/data/landmarks.json'), '/data/landmarks.json?v=current-city');
  for (const prefix of ['', '/nanning-city-atlas']) {
    process.env.NEXT_PUBLIC_BASE_PATH = prefix;
    assert.equal(assetUrl('/draco/'), `${prefix}/draco/`);
    assert.equal(assetUrl('/favicon.svg'), `${prefix}/favicon.svg`);
  }
});
