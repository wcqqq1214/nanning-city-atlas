import {
  CanvasTexture,
  Color,
  Vector4,
  type MeshStandardMaterial,
} from 'three';
import type { Overview } from './types';

/** Continuous landscape colors; the city boundary controls a gradual falloff. */
export function createContextStyle(overview: Overview) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1024;
  const ctx = canvas.getContext('2d')!;
  const [west, south, east, north] = overview.bounds;
  const bounds = new Vector4(
    west - 1,
    south - 1,
    east - west + 2,
    north - south + 2,
  );
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Draw in model units so the outward fade has the same width in both axes.
  ctx.setTransform(
    canvas.width / bounds.z,
    0,
    0,
    canvas.height / bounds.w,
    (-bounds.x * canvas.width) / bounds.z,
    (-bounds.y * canvas.height) / bounds.w,
  );
  ctx.beginPath();
  for (const ring of overview.urbanScope?.core.coordinates ?? []) {
    ring.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
  }
  ctx.lineJoin = 'round';
  const fade =
    (overview.urbanScope?.landscapeFadeMeters ?? 1800) / overview.metersPerUnit;
  for (let i = 64; i > 0; i--) {
    const t = i / 64;
    const value = Math.round(255 * (1 - t * t * (3 - 2 * t)));
    ctx.strokeStyle = `rgb(${value},${value},${value})`;
    ctx.lineWidth = fade * t * 2;
    ctx.stroke();
  }
  ctx.fillStyle = 'white';
  ctx.fill('evenodd');
  // Pack actual woodland coverage into G, alongside the detail weight in R.
  // One small texture replaces dense peripheral trees without erasing hills.
  ctx.resetTransform();
  const detail = ctx.getImageData(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'white';
  ctx.filter = 'blur(1px)';
  ctx.beginPath();
  for (const polygon of overview.urbanScope?.woodland?.coordinates ?? []) {
    for (const ring of polygon) {
      ring.forEach(([x, y], i) => {
        const u = ((x - bounds.x) / bounds.z) * canvas.width;
        const v = ((y - bounds.y) / bounds.w) * canvas.height;
        if (i === 0) ctx.moveTo(u, v);
        else ctx.lineTo(u, v);
      });
      ctx.closePath();
    }
  }
  ctx.fill('evenodd');
  const woodland = ctx.getImageData(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < detail.data.length; i += 4)
    detail.data[i + 1] = woodland.data[i];
  ctx.putImageData(detail, 0, 0);
  const mask = new CanvasTexture(canvas);
  mask.flipY = false;
  const uniforms = {
    contextMask: { value: mask },
    contextBounds: { value: bounds },
  };
  const applied = new WeakSet<MeshStandardMaterial>();
  return {
    uniforms,
    apply(material: MeshStandardMaterial, kind: 'ground' | 'forest' | 'road') {
      if (applied.has(material)) return;
      applied.add(material);
      material.onBeforeCompile = (shader) => {
        Object.assign(shader.uniforms, uniforms, {
          contextTint: {
            value: new Color(kind === 'road' ? '#a3aaa3' : '#b9c0ab'),
          },
          woodlandTint: { value: new Color('#91a592') },
        });
        shader.vertexShader =
          'varying vec2 cityPosition;\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace(
          '#include <worldpos_vertex>',
          '#include <worldpos_vertex>\ncityPosition = (modelMatrix * vec4(transformed, 1.0)).xz * vec2(1.0, -1.0);',
        );
        shader.fragmentShader =
          'uniform sampler2D contextMask;\nuniform vec4 contextBounds;\nuniform vec3 contextTint;\nuniform vec3 woodlandTint;\nvarying vec2 cityPosition;\n' +
          shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <map_fragment>',
          `#include <map_fragment>
          vec2 cityUV = (cityPosition - contextBounds.xy) / contextBounds.zw;
          vec2 landscape = texture2D(contextMask, cityUV).rg;
          vec3 tint = ${kind === 'road' ? 'contextTint' : 'mix(contextTint, woodlandTint, landscape.g)'};
          diffuseColor.rgb = mix(diffuseColor.rgb, tint, 1.0 - landscape.r);`,
        );
      };
      material.customProgramCacheKey = () => `city-context-v2-${kind}`;
      material.needsUpdate = true;
    },
    dispose: () => mask.dispose(),
  };
}
