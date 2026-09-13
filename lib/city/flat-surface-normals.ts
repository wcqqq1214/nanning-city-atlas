import * as THREE from 'three';

/** Restore per-face normals needed by shadow normalBias after compact loading. */
export function restoreFlatSurfaceNormals(root: THREE.Object3D) {
  const restored = new Map<THREE.BufferGeometry, THREE.BufferGeometry>();
  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    const source: THREE.BufferGeometry = object.geometry;
    if (source.hasAttribute('normal')) return;
    let geometry = restored.get(source);
    if (!geometry) {
      // Indexed shared positions cannot hold a different normal for each face.
      // Expanding only these primitives restores the original flat GPU layout.
      geometry = source.index ? source.toNonIndexed() : source;
      geometry.computeVertexNormals();
      restored.set(source, geometry);
    }
    object.geometry = geometry;
  });
  for (const [source, geometry] of restored) {
    if (source !== geometry) source.dispose();
  }
}
