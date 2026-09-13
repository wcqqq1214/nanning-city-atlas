import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import {
  INSPECTION_VIEWS,
  inspectionSearch,
  readInspection,
  validCamera,
} from '../lib/city/inspection.ts';
import { createInspectionMaterials } from '../lib/city/inspection-materials.ts';

test('saved inspection links restore every camera and display setting without precision loss', () => {
  for (const view of Object.keys(INSPECTION_VIEWS)) {
    const settings = readInspection(
      `?view=${view}&quality=smooth&material=clay&hour=18&height=0.75`,
    );
    assert.ok(validCamera(settings.camera), view);
    settings.camera.position[0] += 0.1234567890123;
    assert.deepEqual(readInspection(inspectionSearch(settings)), settings);
  }
});

test('malformed or unsafe camera values fall back to a known usable viewpoint', () => {
  const fallback = INSPECTION_VIEWS.residential.camera;
  for (const camera of [
    '1,2,3',
    '1,,3,4,5,6',
    'NaN,2,3,4,5,6',
    '1,2,3,1,2,3',
    '1,-10,3,1,0,3',
    '1,99999,3,4,5,6',
  ]) {
    assert.deepEqual(
      readInspection(`?view=residential&camera=${camera}`).camera,
      fallback,
    );
  }
  const bad = readInspection(
    '?view=__proto__&quality=broken&material=other&hour=Infinity&height=0',
  );
  assert.equal(bad.view, 'overview');
  assert.equal(bad.quality, 'detail');
  assert.equal(bad.material, 'lit');
  assert.equal(bad.hour, 14);
  assert.equal(bad.heightScale, 1);
});

test('clay and flat colors preserve geometry, restore original materials and release only inspection materials', () => {
  const city = new THREE.Group();
  const source = new THREE.MeshStandardMaterial({
    color: '#f09339',
    roughness: 0.3,
  });
  const second = new THREE.MeshStandardMaterial({
    color: '#47917e',
    vertexColors: true,
  });
  const water = new THREE.ShaderMaterial();
  const geometry = new THREE.BoxGeometry();
  const tower = new THREE.Mesh(geometry, [source, second]);
  const shared = new THREE.Mesh(geometry, source);
  const river = new THREE.Mesh(geometry, water);
  city.add(tower, shared, river);
  const originals = tower.material;
  let sourceDisposals = 0;
  source.addEventListener('dispose', () => sourceDisposals++);
  const inspection = createInspectionMaterials(city);
  inspection.apply('clay');
  assert.equal(tower.material, shared.material);
  assert.equal(river.material, tower.material);
  assert.equal(tower.geometry, geometry);
  const clay = tower.material;
  let temporaryDisposals = 0;
  clay.addEventListener('dispose', () => temporaryDisposals++);
  inspection.apply('color');
  assert.ok(tower.material[0] instanceof THREE.MeshBasicMaterial);
  assert.equal(tower.material[0], shared.material);
  assert.ok(tower.material[0].color.equals(source.color));
  assert.equal(tower.material[1].vertexColors, true);
  const flat = shared.material;
  flat.addEventListener('dispose', () => temporaryDisposals++);
  inspection.apply('lit');
  assert.equal(tower.material, originals);
  assert.equal(shared.material, source);
  assert.equal(river.material, water);
  inspection.apply('color');
  assert.equal(shared.material, flat);
  inspection.dispose();
  assert.equal(tower.material, originals);
  assert.equal(sourceDisposals, 0);
  assert.equal(temporaryDisposals, 2);
  geometry.dispose();
  source.dispose();
  second.dispose();
  water.dispose();
});
