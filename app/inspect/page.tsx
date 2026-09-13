'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { assetUrl } from '@/lib/city/assets';
import {
  INSPECTION_VIEWS,
  inspectionSearch,
  readInspection,
  type InspectionSettings,
} from '@/lib/city/inspection';
import {
  DEFAULT_LAYERS,
  type Overview,
  type SceneController,
  type SceneMetrics,
  type SceneOptions,
} from '@/lib/city/types';
import styles from './inspection.module.css';

const WIDTH = 1280;
const HEIGHT = 800;
const PROFILE = { pixelRatio: 1, frozenTime: 0 };
function sceneOptions(settings: InspectionSettings): SceneOptions {
  return {
    layers: {
      ...DEFAULT_LAYERS,
      labels: false,
      vegetation: settings.vegetation !== false,
    },
    hour: settings.hour,
    heightScale: settings.heightScale,
    autoRotate: false,
    topDown: false,
    selected: null,
  };
}

function InspectionWorkspace({ initial }: { initial: InspectionSettings }) {
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<SceneController | null>(null);
  const current = useRef<InspectionSettings>(initial);
  const [settings, setSettings] = useState<InspectionSettings>(initial);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState('准备视觉检查');
  const [error, setError] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [metrics, setMetrics] = useState<SceneMetrics | null>(null);
  const [savedUrl, setSavedUrl] = useState('');
  const quality = settings?.quality;
  useEffect(() => {
    current.current = settings;
  }, [settings]);

  useEffect(() => {
    if (!quality || !host.current) return;
    const container = host.current;
    const abort = new AbortController();
    setReady(false);
    setError('');
    setMetrics(null);
    import('@/lib/city/scene')
      .then(async ({ createCityScene }) => {
        if (abort.signal.aborted) return;
        const scene = await createCityScene(
          container,
          {
            progress: (message) => setStatus(message),
            ready: (_, summary) => setOverview(summary),
            select: () => {},
            heading: () => {},
            view: () => {},
            interaction: () => {},
            metrics: setMetrics,
            error: (message) => {
              setError(message);
              setReady(false);
            },
          },
          abort.signal,
          quality,
          PROFILE,
        );
        if (abort.signal.aborted) {
          scene.dispose();
          return;
        }
        controller.current = scene;
        const state = current.current!;
        scene.apply(sceneOptions(state));
        scene.setVisualMode(state.material);
        scene.restoreView(state.camera);
        setReady(true);
        setStatus('就绪 · 可以拖动观察，保存链接后可恢复镜头');
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : '检查场景载入失败',
          );
      });
    return () => {
      abort.abort();
      controller.current?.dispose();
      controller.current = null;
    };
  }, [quality]);

  useEffect(() => {
    if (!settings || !controller.current) return;
    controller.current.apply(sceneOptions(settings));
    controller.current.setVisualMode(settings.material);
    controller.current.restoreView(settings.camera);
  }, [settings]);

  function change(patch: Partial<InspectionSettings>) {
    setSettings(
      (previous) =>
        previous && {
          ...previous,
          camera: controller.current?.readView() ?? previous.camera,
          ...patch,
        },
    );
    setSavedUrl('');
  }

  function saveView() {
    if (!settings || !controller.current) return;
    const state = { ...settings, camera: controller.current.readView() };
    const url = new URL(window.location.href);
    url.search = inspectionSearch(state);
    window.history.replaceState(null, '', url);
    setSavedUrl(url.href);
    return state;
  }

  function exportRecord() {
    const state = saveView();
    if (!state || !overview) return;
    const snapshot = {
      schemaVersion: 1,
      capturedAt: new Date().toISOString(),
      url: new URL(window.location.href).href,
      settings: state,
      canvas: { width: WIDTH, height: HEIGHT, ...PROFILE },
      effectiveHour: state.material === 'lit' ? state.hour : 14,
      layers: sceneOptions(state).layers,
      source: {
        model: assetUrl(`/models/${overview.models[state.quality].file}`),
        overview: assetUrl('/data/overview.json'),
        modelBytes: overview.models[state.quality].bytes,
        metersPerUnit: overview.metersPerUnit,
        terrainExaggeration: overview.terrainExaggeration,
        buildingExaggeration: overview.buildingExaggeration,
        buildingScaleOverrides: overview.buildingScaleOverrides ?? [],
        osmTimestamp: overview.osmTimestamp,
      },
      renderer: metrics,
      userAgent: navigator.userAgent,
      note: '模型内还有地标独立展示倍率；网页高度倍率不是中性比例。静止帧率不代表连续操作性能。',
    };
    const blob = new Blob([JSON.stringify(snapshot, null, 2) + '\n'], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${state.view}-${state.quality}-${state.material}-h${state.hour}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>城市结构 · 视觉检查</h1>
          <p>固定 1280 × 800 画布 / 像素比 1 / 水面时间 0 / 隐藏标注</p>
        </div>
        <a href={assetUrl('/')}>返回城市浏览 →</a>
      </header>
      {settings && (
        <fieldset className={styles.controls} disabled={!ready}>
          <legend>镜头与显示</legend>
          <label>
            <input
              type="checkbox"
              checked={settings.vegetation !== false}
              onChange={(event) => change({ vegetation: event.target.checked })}
            />
            显示植被
          </label>
          <label>
            检查区域
            <select
              aria-label="检查区域"
              value={settings.view}
              onChange={(event) =>
                change({
                  view: event.target.value,
                  camera: structuredClone(
                    INSPECTION_VIEWS[event.target.value].camera,
                  ),
                })
              }
            >
              {Object.entries(INSPECTION_VIEWS).map(([id, preset]) => (
                <option key={id} value={id}>
                  {preset.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            模型画质
            <select
              aria-label="模型画质"
              value={settings.quality}
              onChange={(event) =>
                change({
                  quality: event.target.value as InspectionSettings['quality'],
                })
              }
            >
              <option value="detail">精细</option>
              <option value="smooth">流畅</option>
            </select>
          </label>
          <label>
            材质检查
            <select
              aria-label="材质检查"
              value={settings.material}
              onChange={(event) =>
                change({
                  material: event.target
                    .value as InspectionSettings['material'],
                })
              }
            >
              <option value="lit">完整光照</option>
              <option value="clay">灰模</option>
              <option value="color">基础颜色（无光照）</option>
            </select>
          </label>
          <label>
            光照时间
            <select
              aria-label="光照时间"
              disabled={settings.material !== 'lit'}
              value={settings.hour}
              onChange={(event) => change({ hour: Number(event.target.value) })}
            >
              {[6, 8, 10, 12, 14, 16, 18, 20, 21, 22, settings.hour]
                .filter((v, i, a) => a.indexOf(v) === i)
                .sort((a, b) => a - b)
                .map((hour) => (
                  <option key={hour} value={hour}>
                    {hour}:00
                  </option>
                ))}
            </select>
          </label>
          <label>
            网页高度倍率
            <input
              aria-label="网页高度倍率"
              type="number"
              min="0.5"
              max="2"
              step="0.05"
              value={settings.heightScale}
              onChange={(event) => {
                const heightScale = Number(event.target.value);
                if (
                  Number.isFinite(heightScale) &&
                  heightScale >= 0.5 &&
                  heightScale <= 2
                )
                  change({ heightScale });
              }}
            />
          </label>
          <button
            onClick={() =>
              change({
                camera: structuredClone(INSPECTION_VIEWS[settings.view].camera),
              })
            }
          >
            恢复预设镜头
          </button>
          <button onClick={saveView}>保存镜头链接</button>
          <button onClick={exportRecord}>导出参数 JSON</button>
          <button
            onClick={() =>
              controller.current
                ?.capture()
                .catch((reason: unknown) => setError(String(reason)))
            }
          >
            导出画面 PNG
          </button>
        </fieldset>
      )}
      <output className={styles.status}>
        {error || status}
        {metrics &&
          ` · ${metrics.profile} / ${(metrics.modelBytes / 1e6).toFixed(2)} MB / 当前绘制 ${metrics.triangles.toLocaleString()} 面 / ${metrics.calls} 次调用`}
      </output>
      {savedUrl && (
        <input
          className={styles.url}
          aria-label="已保存的镜头链接"
          value={savedUrl}
          readOnly
          onFocus={(event) => event.target.select()}
        />
      )}
      <div className={styles.scroll}>
        <div
          ref={host}
          className={styles.stage}
          style={{ width: WIDTH, height: HEIGHT }}
          data-testid="inspection-stage"
          data-ready={ready}
          data-material={settings?.material}
        />
      </div>
      <p className={styles.note}>
        灰模采用中性日间照明；基础颜色关闭材质光照与夜间光晕。两者隐藏雾以检查形体。模型已包含地形与建筑放大，网页
        1.0× 仅表示不追加整体高度缩放。
      </p>
    </main>
  );
}

function subscribeLocation(callback: () => void) {
  window.addEventListener('popstate', callback);
  return () => window.removeEventListener('popstate', callback);
}

export default function InspectionPage() {
  const search = useSyncExternalStore(
    subscribeLocation,
    () => window.location.search,
    () => null,
  );
  return search === null ? (
    <main className={styles.page}>准备视觉检查…</main>
  ) : (
    <InspectionWorkspace key={search} initial={readInspection(search)} />
  );
}
