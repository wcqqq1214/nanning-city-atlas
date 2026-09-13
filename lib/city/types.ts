export type LayerKey =
  | 'buildings'
  | 'vegetation'
  | 'roads'
  | 'railways'
  | 'water'
  | 'labels';
export type Layers = Record<LayerKey, boolean>;
export type QualityPreference = 'auto' | 'smooth' | 'detail';
export type SceneMetrics = {
  profile: 'smooth' | 'detail';
  loadMs: number;
  modelBytes: number;
  fps: number;
  triangles: number;
  calls: number;
  pixelRatio: number;
};
export type Landmark = {
  id: string;
  name: string;
  lon: number;
  lat: number;
  position: [number, number, number];
  anchorHeight: number;
  cameraDistance: number;
  closeDistance?: number;
  cameraBearing?: number;
  modelled: boolean;
  layer?: 'buildings' | 'roads';
  category: string;
  description: string;
};
export type Overview = {
  bbox: number[];
  previousBbox: number[];
  center: number[];
  bounds: number[];
  metersPerUnit: number;
  water: number[][][][];
  minElevation: number;
  maxElevation: number;
  terrainExaggeration: number;
  buildingExaggeration: number;
  buildingScaleOverrides?: {
    blockId: string;
    scale: number;
    layoutSource: string;
    buildings: number;
  }[];
  osmTimestamp: string;
  mobileTrees: number;
  models: Record<'smooth' | 'detail', { file: string; bytes: number }>;
  stats: {
    mappedBuildings: number;
    infillBuildings: number;
    roadSegments: number;
    trees: number;
  };
};
export type SceneOptions = {
  layers: Layers;
  hour: number;
  heightScale: number;
  autoRotate: boolean;
  topDown: boolean;
  selected: string | null;
};
export type VisualMode = 'lit' | 'clay' | 'color';
export type CameraView = {
  position: [number, number, number];
  target: [number, number, number];
  fov: number;
};
export type InspectionProfile = {
  pixelRatio: number;
  frozenTime: number;
};
export type SceneController = {
  apply: (options: SceneOptions) => void;
  focus: (id: string | null, close?: boolean) => void;
  zoom: (factor: number) => void;
  north: () => void;
  capture: () => Promise<void>;
  readView: () => CameraView;
  restoreView: (view: CameraView) => void;
  setVisualMode: (mode: VisualMode) => void;
  dispose: () => void;
};
export const DEFAULT_LAYERS: Layers = {
  buildings: true,
  vegetation: true,
  roads: true,
  railways: true,
  water: true,
  labels: true,
};
