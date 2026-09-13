import * as THREE from 'three';
import type { VisualMode } from './types';

/** Replace materials on the existing meshes, preserving geometry and ownership. */
export function createInspectionMaterials(city: THREE.Object3D) {
  const originals = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  const colors = new Map<THREE.Material, THREE.MeshBasicMaterial>();
  const clay = new THREE.MeshStandardMaterial({
    name: 'Inspection clay',
    color: '#bcc5c0',
    roughness: 1,
    metalness: 0,
    side: THREE.DoubleSide,
  });
  city.traverse((object) => {
    if (object instanceof THREE.Mesh) originals.set(object, object.material);
  });

  function baseColor(source: THREE.Material) {
    let material = colors.get(source);
    if (!material) {
      const standard = source as THREE.MeshStandardMaterial;
      material = new THREE.MeshBasicMaterial({
        name: `Inspection color: ${source.name}`,
        color: standard.color?.clone() ?? new THREE.Color('#33978c'),
        map: standard.map ?? null,
        vertexColors: standard.vertexColors ?? false,
        side: source.side,
        opacity: source.opacity,
        transparent: source.transparent,
        alphaTest: source.alphaTest,
      });
      colors.set(source, material);
    }
    return material;
  }

  return {
    apply(mode: VisualMode) {
      for (const [mesh, source] of originals) {
        mesh.material =
          mode === 'lit'
            ? source
            : mode === 'clay'
              ? clay
              : Array.isArray(source)
                ? source.map(baseColor)
                : baseColor(source);
      }
    },
    dispose() {
      // Restore originals before the normal scene disposer visits its materials.
      for (const [mesh, material] of originals) mesh.material = material;
      clay.dispose();
      for (const material of colors.values()) material.dispose();
      colors.clear();
      originals.clear();
    },
  };
}
