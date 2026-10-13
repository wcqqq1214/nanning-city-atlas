import { validCamera } from './inspection.ts';
import { DEFAULT_LAYERS, type CameraView, type SceneOptions } from './types.ts';

export type SharedView = { camera: CameraView; options: SceneOptions };

export function encodeShare(camera: CameraView, options: SceneOptions): string {
  return (
    '#' +
    new URLSearchParams({
      // Keep precision at OrbitControls' distance/polar limits. Rounding a
      // valid near/top-down view can move it outside the accepted range.
      camera: [...camera.position, ...camera.target].join(','),
      fov: String(camera.fov),
      span: String(camera.span ?? 0),
      place: options.selected ?? '',
      hour: String(options.hour),
      height: String(options.heightScale),
      top: options.topDown ? '1' : '0',
      hidden: Object.keys(DEFAULT_LAYERS)
        .filter((k) => !options.layers[k as keyof typeof DEFAULT_LAYERS])
        .join(','),
    }).toString()
  );
}

export function decodeShare(
  hash: string,
  ids: string[],
  bounds: number[],
): SharedView | null {
  const p = new URLSearchParams(hash.replace(/^#/, ''));
  const values = p
    .get('camera')
    ?.split(',')
    .map((v) => (v.trim() ? Number(v) : NaN));
  if (values?.length !== 6) return null;
  const camera: CameraView = {
    position: values.slice(0, 3) as CameraView['position'],
    target: values.slice(3) as CameraView['target'],
    fov: Number(p.get('fov')),
  };
  if (
    !validCamera(camera) ||
    camera.target[0] < bounds[0] ||
    camera.target[0] > bounds[2] ||
    -camera.target[2] < bounds[1] ||
    -camera.target[2] > bounds[3]
  )
    return null;
  const span = Number(p.get('span'));
  if (Number.isFinite(span) && span > 0 && span < 2000) camera.span = span;
  const hour = Number(p.get('hour')),
    height = Number(p.get('height'));
  const layers = { ...DEFAULT_LAYERS };
  for (const key of p.get('hidden')?.split(',') ?? [])
    if (Object.hasOwn(layers, key)) layers[key as keyof typeof layers] = false;
  return {
    camera,
    options: {
      layers,
      hour: hour >= 6 && hour <= 22 ? hour : 14,
      heightScale: height >= 0.5 && height <= 2 ? height : 1,
      selected: ids.includes(p.get('place') ?? '') ? p.get('place')! : null,
      autoRotate: false,
      topDown: p.get('top') === '1',
    },
  };
}
