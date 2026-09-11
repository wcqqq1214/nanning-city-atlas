import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import * as THREE from 'three';
import { createAreaHighlight } from '../lib/city/area-highlight.ts';

const { areas } = JSON.parse(
  readFileSync(new URL('../data/landmark-areas.json', import.meta.url)),
);
const { center } = JSON.parse(
  readFileSync(new URL('../public/data/overview.json', import.meta.url)),
);
const height = (x, z) => 3 + x * 0.02 + z * 0.01;
function fixture(scale = 1) {
  const city = new THREE.Group();
  city.scale.y = scale;
  const points = [
    [-200, -200],
    [200, -200],
    [200, 200],
    [-200, -200],
    [200, 200],
    [-200, 200],
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(
      points.flatMap(([x, z]) => [x, height(x, z), z]),
      3,
    ),
  );
  const terrain = new THREE.Mesh(geometry);
  terrain.name = 'Terrain';
  city.add(terrain);
  return {
    city,
    overlay: createAreaHighlight(city, center, (id) => areas[id]),
  };
}

test('all published areas drape onto sloped terrain without double-applying height scale', () => {
  const { city, overlay } = fixture(2);
  assert.equal(Object.keys(areas).length, 8);
  for (const id of Object.keys(areas)) {
    const bounds = overlay.select(id);
    assert.ok(bounds && !bounds.isEmpty(), id);
    const group = city.getObjectByName(`SelectionArea_${id}`);
    const mesh = group.children.find((object) => object.type === 'Mesh');
    const positions = mesh.geometry.getAttribute('position');
    assert.ok(
      positions.count > 0 && positions.count < 150000,
      `${id}: bounded mesh size`,
    );
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i),
        y = positions.getY(i),
        z = positions.getZ(i);
      assert.ok(Number.isFinite(x + y + z));
      assert.ok(
        Math.abs(y - height(x, z) - 0.035) < 0.00001,
        `${id}: terrain height at vertex ${i}`,
      );
    }
  }
});

test('selection switches areas, reuses geometry, and clears for landmarks or overview', () => {
  const { city, overlay } = fixture();
  overlay.select('gxu');
  const first = city.getObjectByName('SelectionArea_gxu');
  const geometry = first.children.at(-1).geometry;
  overlay.select('gxmzu');
  assert.equal(first.visible, false);
  assert.equal(city.getObjectByName('SelectionArea_gxmzu').visible, true);
  overlay.select('gxu');
  assert.equal(first.visible, true);
  assert.equal(first.children.at(-1).geometry, geometry);
  for (const id of ['nanningbridge', null]) {
    overlay.select(id);
    assert.ok(
      city
        .getObjectByName('SelectionAreas')
        .children.every((group) => !group.visible),
    );
  }
});
