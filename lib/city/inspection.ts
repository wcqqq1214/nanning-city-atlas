import type { CameraView, VisualMode } from './types';

// World-space Three.js coordinates: X east, Y up, Z south; 100 m per unit.
// Presets deliberately do not depend on the current landmark bounds or model.
export const INSPECTION_VIEWS: Record<
  string,
  { label: string; camera: CameraView }
> = {
  overview: {
    label: '全城 · 斜俯视',
    camera: { position: [235, 340, 370], target: [0, 0, 0], fov: 40 },
  },
  residential: {
    label: '香榭里花园 · 街区',
    camera: {
      position: [87.4, 5.6, 12.8],
      target: [83.016, 0.6, 6.596],
      fov: 40,
    },
  },
  'residential-top': {
    label: '香榭里花园 · 俯视',
    camera: {
      position: [83.016, 10, 6.95],
      target: [83.016, 0.6, 6.596],
      fov: 40,
    },
  },
  waterfront: {
    label: '畅游阁—邕江大桥 · 北岸',
    camera: { position: [11, 4.5, 19.8], target: [15.1, 0.55, 11.6], fov: 40 },
  },
  'waterfront-low': {
    label: '畅游阁—邕江大桥 · 对岸低斜视',
    camera: { position: [17, 2.3, 21], target: [15.1, 0.55, 11.6], fov: 40 },
  },
  'waterfront-top': {
    label: '畅游阁—邕江大桥 · 岸线俯视',
    camera: { position: [14.7, 10.5, 12.2], target: [14.7, 0.4, 11.8], fov: 40 },
  },
  'waterfront-bridgehead': {
    label: '邕江大桥 · 北岸桥头',
    camera: { position: [19.2, 2.3, 15.1], target: [16.55, 0.45, 12.25], fov: 40 },
  },
  qingxiu: {
    label: '青秀山 · 山脊与山脚',
    camera: { position: [100, 13, 66], target: [88.058, 2.5, 46.641], fov: 40 },
  },
  'qingxiu-tower': {
    label: '青秀山 · 龙象塔与平台',
    camera: { position: [90.1, 3.9, 49.3], target: [88.058, 2.48, 46.641], fov: 40 },
  },
  'qingxiu-path': {
    label: '青秀山 · 山坡园路',
    camera: { position: [90, 4.8, 48], target: [87.8, 1.85, 44.6], fov: 40 },
  },
  'qingxiu-ridge': {
    label: '青秀山 · 北侧山脊',
    camera: { position: [94, 8, 42], target: [89, 2.42, 37], fov: 40 },
  },
  'qingxiu-lake': {
    label: '青秀山 · 天池湖岸',
    camera: { position: [84, 4.5, 48], target: [87.285, 1.775, 44.157], fov: 40 },
  },
  'qingxiu-foothill': {
    label: '青秀山 · 凤岭南路山脚界面',
    camera: { position: [96, 6.5, 34], target: [89.8, 0.8, 29.6], fov: 40 },
  },
  arts: {
    label: '广西文化艺术中心 · 场地',
    camera: {
      position: [63.5, 4.5, 55.4],
      target: [67.568, 0.75, 49.799],
      fov: 40,
    },
  },
  zhenning: {
    label: '镇宁炮台 · 场地',
    camera: {
      position: [23.2, 2.9, -2.5],
      target: [25.063, 1.1, -6.014],
      fov: 40,
    },
  },
  'arts-entry': {
    label: '广西文化艺术中心 · 入口台阶',
    camera: { position: [65.2, 2.6, 52.7], target: [67.568, 0.65, 49.799], fov: 40 },
  },
  'arts-back': {
    label: '广西文化艺术中心 · 北侧',
    camera: { position: [70.8, 3.5, 45.2], target: [67.568, 0.75, 49.799], fov: 40 },
  },
  'zhenning-close': {
    label: '镇宁炮台 · 南门与堡垒',
    camera: { position: [24.6, 2.2, -3.7], target: [25.063, 1.01, -6.014], fov: 20 },
  },
  'zhenning-back': {
    label: '镇宁炮台 · 北门与场地',
    camera: { position: [25.7, 2.6, -8.0], target: [25.063, 1.01, -6.014], fov: 20 },
  },
  diwang: {
    label: '地王大厦 · 塔楼与城市',
    camera: { position: [71.0, 5.4, 13.4], target: [67.326, 1.8, 7.086], fov: 40 },
  },
  'diwang-wide': {
    label: '地王大厦 · 高度比例对照',
    camera: { position: [74.0, 8.0, 19.0], target: [67.326, 2.6, 7.086], fov: 40 },
  },
  'diwang-base': {
    label: '地王大厦 · 裙房与街道',
    camera: { position: [65.0, 2.3, 10.4], target: [67.326, 0.8, 7.086], fov: 40 },
  },
  confucius: {
    label: '南宁孔庙 · 院落与山坡',
    camera: { position: [94.4, 3.6, 53.0], target: [91.608, 0.66, 49.167], fov: 40 },
  },
  'confucius-wide': {
    label: '南宁孔庙 · 场地比例对照',
    camera: { position: [97.0, 6.0, 57.0], target: [91.608, 0.9, 49.167], fov: 40 },
  },
  'confucius-courts': {
    label: '南宁孔庙 · 院落台阶',
    camera: { position: [92.5, 2.2, 51.6], target: [91.608, 0.63, 49.167], fov: 30 },
  },
  'confucius-back': {
    label: '南宁孔庙 · 后院与地形',
    camera: { position: [89.8, 2.8, 46.5], target: [91.608, 0.65, 49.167], fov: 40 },
  },
};

export type InspectionSettings = {
  vegetation?: boolean;
  view: string;
  camera: CameraView;
  quality: 'detail' | 'smooth';
  material: VisualMode;
  hour: number;
  heightScale: number;
};

export function validCamera(view: CameraView): boolean {
  const numbers = [...view.position, ...view.target, view.fov];
  if (
    view.position.length !== 3 ||
    view.target.length !== 3 ||
    !numbers.every(Number.isFinite) ||
    numbers.some((v) => Math.abs(v) > 2000) ||
    view.fov < 20 ||
    view.fov > 80
  )
    return false;
  const [x, y, z] = view.position.map((v, i) => v - view.target[i]);
  const distance = Math.hypot(x, y, z);
  const polar = Math.acos(y / distance);
  return (
    distance >= 2.4 &&
    distance <= 1200 &&
    polar >= 0.025 &&
    polar <= Math.PI / 2.12
  );
}

function bounded(
  value: string | null,
  min: number,
  max: number,
  fallback: number,
) {
  const n = value === null || value.trim() === '' ? NaN : Number(value);
  return Number.isFinite(n) && n >= min && n <= max ? n : fallback;
}

export function readInspection(search: string): InspectionSettings {
  const params = new URLSearchParams(search);
  const requested = params.get('view') ?? 'overview';
  const view = Object.hasOwn(INSPECTION_VIEWS, requested)
    ? requested
    : 'overview';
  let camera = structuredClone(INSPECTION_VIEWS[view].camera);
  const raw = params.get('camera');
  if (raw) {
    const values = raw
      .split(',')
      .map((v) => (v.trim() === '' ? NaN : Number(v)));
    if (values.length === 6) {
      const candidate: CameraView = {
        position: values.slice(0, 3) as CameraView['position'],
        target: values.slice(3) as CameraView['target'],
        fov: bounded(params.get('fov'), 20, 80, 40),
      };
      if (validCamera(candidate)) camera = candidate;
    }
  }
  const material = params.get('material');
  return {
    view,
    camera,
    quality: params.get('quality') === 'smooth' ? 'smooth' : 'detail',
    material: material === 'clay' || material === 'color' ? material : 'lit',
    hour: bounded(params.get('hour'), 6, 22, 14),
    heightScale: bounded(params.get('height'), 0.5, 2, 1),
    vegetation: params.get('vegetation') !== 'off',
  };
}

export function inspectionSearch(settings: InspectionSettings): string {
  return new URLSearchParams({
    view: settings.view,
    quality: settings.quality,
    material: settings.material,
    hour: String(settings.hour),
    height: String(settings.heightScale),
    camera: [...settings.camera.position, ...settings.camera.target].join(','),
    fov: String(settings.camera.fov),
    ...(settings.vegetation === false ? { vegetation: 'off' } : {}),
  }).toString();
}
