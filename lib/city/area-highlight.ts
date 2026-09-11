import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import type { LandmarkArea } from './landmark-areas';

type Point = [number, number];
type Triangle = [THREE.Vector3, THREE.Vector3, THREE.Vector3];

/** Sample only the selected area's actual terrain/water, in unscaled city space. */
function surfaceSampler(city: THREE.Group, bounds: THREE.Box3) {
  const bins = new Map<string, Triangle[]>();
  const inverse = city.matrixWorld.clone().invert();
  for (const name of ['Terrain', 'Water']) {
    city.getObjectByName(name)?.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const geometry = object.geometry;
      if (!geometry.boundingBox) geometry.computeBoundingBox();
      const matrix = inverse.clone().multiply(object.matrixWorld);
      const box = geometry.boundingBox!.clone().applyMatrix4(matrix);
      if (
        box.max.x < bounds.min.x ||
        box.min.x > bounds.max.x ||
        box.max.z < bounds.min.z ||
        box.min.z > bounds.max.z
      )
        return;
      const positions = geometry.getAttribute('position');
      const index = geometry.index;
      for (let i = 0; i < (index?.count ?? positions.count); i += 3) {
        const tri = [0, 1, 2].map((j) =>
          new THREE.Vector3()
            .fromBufferAttribute(positions, index ? index.getX(i + j) : i + j)
            .applyMatrix4(matrix),
        ) as Triangle;
        const minX = Math.min(...tri.map((p) => p.x)),
          maxX = Math.max(...tri.map((p) => p.x));
        const minZ = Math.min(...tri.map((p) => p.z)),
          maxZ = Math.max(...tri.map((p) => p.z));
        if (
          maxX < bounds.min.x ||
          minX > bounds.max.x ||
          maxZ < bounds.min.z ||
          minZ > bounds.max.z
        )
          continue;
        const [a, b, c] = tri;
        if (
          Math.abs((b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z)) <
          1e-10
        )
          continue;
        for (
          let x = Math.floor(Math.max(minX, bounds.min.x));
          x <= Math.floor(Math.min(maxX, bounds.max.x));
          x++
        ) {
          for (
            let z = Math.floor(Math.max(minZ, bounds.min.z));
            z <= Math.floor(Math.min(maxZ, bounds.max.z));
            z++
          ) {
            const key = `${x},${z}`;
            const list = bins.get(key) ?? [];
            list.push(tri);
            bins.set(key, list);
          }
        }
      }
    });
  }
  return (x: number, z: number) => {
    let height = -Infinity,
      closest = Infinity,
      fallback = 0;
    for (const [a, b, c] of bins.get(`${Math.floor(x)},${Math.floor(z)}`) ??
      []) {
      const denominator = (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z);
      const u =
        ((b.z - c.z) * (x - c.x) + (c.x - b.x) * (z - c.z)) / denominator;
      const v =
        ((c.z - a.z) * (x - c.x) + (a.x - c.x) * (z - c.z)) / denominator;
      if (u >= -1e-4 && v >= -1e-4 && u + v <= 1.0001)
        height = Math.max(height, u * a.y + v * b.y + (1 - u - v) * c.y);
      // Draco may leave tiny seams between terrain chunks: use a nearby surface
      // height there instead of letting the boundary plunge to the scene datum.
      for (const p of [a, b, c]) {
        const distance = (x - p.x) ** 2 + (z - p.z) ** 2;
        if (distance < closest) {
          closest = distance;
          fallback = p.y;
        }
      }
    }
    return Number.isFinite(height) ? height : fallback;
  };
}

export function createAreaHighlight(
  city: THREE.Group,
  center: number[],
  findArea: (id: string) => LandmarkArea | undefined,
) {
  const root = new THREE.Group();
  root.name = 'SelectionAreas';
  city.add(root);
  const cache = new Map<string, { group: THREE.Group; bounds: THREE.Box3 }>();
  const fill = new THREE.MeshBasicMaterial({
    color: '#dda640',
    transparent: true,
    opacity: 0.15,
    side: THREE.DoubleSide,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  });
  const outline = new LineMaterial({
    color: '#bc7c19',
    linewidth: 2.5,
    transparent: true,
    opacity: 0.95,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  });
  // The root remains attached, including hidden cached geometry, so the scene's
  // existing disposal traversal frees every overlay when switching quality.
  const kx = 1113.2 * Math.cos(THREE.MathUtils.degToRad(center[1]));
  function build(id: string) {
    const area = findArea(id);
    if (!area) return undefined;
    city.updateMatrixWorld(true);
    const polygons = area.polygons.map((polygon) =>
      polygon.map((ring) =>
        ring
          .slice(0, -1)
          .map(
            ([lon, lat]): Point => [
              (lon - center[0]) * kx,
              -(lat - center[1]) * 1113.2,
            ],
          ),
      ),
    );
    const bounds = new THREE.Box3();
    polygons
      .flat(2)
      .forEach(([x, z]) => bounds.expandByPoint(new THREE.Vector3(x, 0, z)));
    const height = surfaceSampler(city, bounds);
    const group = new THREE.Group();
    group.name = `SelectionArea_${id}`;
    const vertices: number[] = [];
    const point3 = ([x, z]: Point) => [x, height(x, z) + 0.035, z];
    function triangle(a: Point, b: Point, c: Point, depth = 0) {
      const lengths = [
        Math.hypot(a[0] - b[0], a[1] - b[1]),
        Math.hypot(b[0] - c[0], b[1] - c[1]),
        Math.hypot(c[0] - a[0], c[1] - a[1]),
      ];
      const longest = Math.max(...lengths);
      if (longest > 0.7 && depth < 14) {
        const edge = lengths.indexOf(longest);
        const [p, q, r] =
          edge === 0 ? [a, b, c] : edge === 1 ? [b, c, a] : [c, a, b];
        const middle: Point = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
        triangle(p, middle, r, depth + 1);
        triangle(middle, q, r, depth + 1);
      } else {
        for (const p of [a, b, c]) vertices.push(...point3(p));
      }
    }
    for (const polygon of polygons) {
      const rings = polygon.map((ring) =>
        ring.map(([x, z]) => new THREE.Vector2(x, z)),
      );
      const flat = polygon.flat();
      for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(
        rings[0],
        rings.slice(1),
      ))
        triangle(flat[a], flat[b], flat[c]);
      for (const ring of polygon) {
        const points: number[] = [];
        for (let i = 0; i < ring.length; i++) {
          const a = ring[i],
            b = ring[(i + 1) % ring.length];
          const steps = Math.max(
            1,
            Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.2),
          );
          for (let j = 0; j < steps; j++)
            points.push(
              ...point3([
                a[0] + ((b[0] - a[0]) * j) / steps,
                a[1] + ((b[1] - a[1]) * j) / steps,
              ]),
            );
        }
        points.push(...points.slice(0, 3));
        const line = new Line2(
          new LineGeometry().setPositions(points),
          outline,
        );
        line.renderOrder = 102;
        group.add(line);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      'position',
      new THREE.Float32BufferAttribute(vertices, 3),
    );
    geometry.computeBoundingBox();
    const mesh = new THREE.Mesh(geometry, fill);
    mesh.renderOrder = 101;
    group.add(mesh);
    root.add(group);
    const entry = { group, bounds: geometry.boundingBox!.clone() };
    cache.set(id, entry);
    return entry;
  }
  return {
    select(id: string | null) {
      const entry = id ? (cache.get(id) ?? build(id)) : undefined;
      cache.forEach(({ group }) => {
        group.visible = group === entry?.group;
      });
      return entry?.bounds;
    },
    resize(width: number, height: number) {
      outline.resolution.set(width, height);
    },
    // Materials may never enter the scene if no area was selected.
    dispose() {
      if (cache.size === 0) {
        fill.dispose();
        outline.dispose();
      }
    },
  };
}
