'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronRight,
  CircleHelp,
  Compass,
  Expand,
  Eye,
  Focus,
  Info,
  Layers3,
  LoaderCircle,
  MapPin,
  Menu,
  Minus,
  Moon,
  Mountain,
  MousePointer2,
  Navigation,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Route,
  SlidersHorizontal,
  Sun,
  Sunset,
  Trees,
  Waves,
  X,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  DEFAULT_LAYERS,
  type Landmark,
  type LayerKey,
  type Overview,
  type SceneController,
  type SceneOptions,
} from '@/lib/city/types';
import { registerAtlasTools } from '@/lib/city/webmcp';

const ORDER = [
  'changyou',
  'nanhu',
  'diwang',
  'expo',
  'cr',
  'qingxiu',
  'bridge',
];
const LAYER_INFO: {
  key: LayerKey;
  name: string;
  detail: string;
  icon: typeof Building2;
}[] = [
  {
    key: 'buildings',
    name: '城市建筑',
    detail: '街区体块与标志性建筑',
    icon: Building2,
  },
  {
    key: 'vegetation',
    name: '林木植被',
    detail: '山林、滨江与公园树冠',
    icon: Trees,
  },
  { key: 'roads', name: '道路桥梁', detail: '城市路网与跨江连接', icon: Route },
  {
    key: 'water',
    name: '河流湖泊',
    detail: '邕江、南湖与城区水面',
    icon: Waves,
  },
  { key: 'labels', name: '地名标注', detail: '可点击的城市地标', icon: MapPin },
];
const iconFor = (id: string) =>
  id === 'qingxiu'
    ? Mountain
    : id === 'nanhu' || id === 'bridge'
      ? Waves
      : Building2;

function MiniMap({
  overview,
  places,
  selected,
  onReset,
}: {
  overview: Overview;
  places: Landmark[];
  selected: string | null;
  onReset: () => void;
}) {
  const [minX, minY, maxX, maxY] = overview.bounds;
  const paths = overview.water.map((polygon) =>
    polygon
      .map(
        (ring) =>
          ring.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' ') + 'Z',
      )
      .join(' '),
  );
  return (
    <button className="minimap" onClick={onReset} aria-label="返回南宁全景">
      <span className="minimap-caption">
        区域总览 <ArrowUpRight size={13} />
      </span>
      <svg
        viewBox={`${minX} ${-maxY} ${maxX - minX} ${maxY - minY}`}
        aria-label="邕江与南湖位置示意图"
      >
        <rect
          x={minX}
          y={-maxY}
          width={maxX - minX}
          height={maxY - minY}
          fill="var(--mini-land)"
        />
        {paths.map((d, i) => (
          <path key={i} d={d} fill="var(--mini-water)" fillRule="evenodd" />
        ))}
        {places.map((p) => (
          <circle
            key={p.id}
            cx={p.position[0]}
            cy={p.position[2]}
            r={selected === p.id ? 3.1 : 1.7}
            fill={selected === p.id ? '#b88232' : '#315e53'}
            stroke="#fff"
            strokeWidth=".7"
          />
        ))}
      </svg>
      <span className="mini-north">N ↑</span>
    </button>
  );
}

export default function Home() {
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<SceneController | null>(null);
  const [places, setPlaces] = useState<Landmark[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [progress, setProgress] = useState({
    message: '准备南宁地理图景',
    value: 0,
  });
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState('explore');
  const [selected, setSelected] = useState<string | null>(null);
  const [layers, setLayers] = useState({ ...DEFAULT_LAYERS });
  const [hour, setHour] = useState(14);
  const [heightScale, setHeightScale] = useState(1);
  const [autoRotate, setAutoRotate] = useState(false);
  const [topDown, setTopDown] = useState(false);
  const [tour, setTour] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [heading, setHeading] = useState(0);
  const [coordinates, setCoordinates] = useState([108.365, 22.805]);
  const [toast, setToast] = useState('');
  const [exporting, setExporting] = useState(false);
  const options = useRef<SceneOptions>({
    layers,
    hour,
    heightScale,
    autoRotate,
    topDown,
    selected,
  });
  const selectRef = useRef<(id: string | null) => void>(() => {});
  const interactionRef = useRef<() => void>(() => {});
  const webState = useRef({
    ready,
    options: { layers, hour, heightScale, autoRotate, topDown, selected },
    landmarks: places.map(({ id, name }) => ({ id, name })),
  });
  const active = places.find((place) => place.id === selected);
  const ordered = ORDER.map((id) => places.find((p) => p.id === id)).filter(
    (p): p is Landmark => Boolean(p),
  );
  const night = hour >= 19;

  const choose = useCallback((id: string | null) => {
    setSelected(id);
    setTour(false);
    setAutoRotate(false);
    setMobileOpen(false);
    controller.current?.focus(id);
  }, []);
  useEffect(() => {
    selectRef.current = choose;
    interactionRef.current = () => {
      setTour(false);
      setAutoRotate(false);
    };
  }, [choose]);
  useEffect(() => {
    options.current = {
      layers,
      hour,
      heightScale,
      autoRotate,
      topDown,
      selected,
    };
    webState.current = {
      ready,
      options: options.current,
      landmarks: places.map(({ id, name }) => ({ id, name })),
    };
    controller.current?.apply(options.current);
  }, [layers, hour, heightScale, autoRotate, topDown, selected, ready, places]);
  useEffect(
    () =>
      registerAtlasTools({
        read: () => webState.current,
        focus: (id) => selectRef.current(id),
        configure: (patch) => {
          if (patch.hour !== undefined) setHour(patch.hour);
          if (patch.topDown !== undefined) setTopDown(patch.topDown);
          if (patch.layers)
            setLayers((current) => ({ ...current, ...patch.layers }));
        },
      }),
    [],
  );

  useEffect(() => {
    if (!host.current) return;
    const abort = new AbortController();
    const container = host.current;
    setReady(false);
    setError('');
    setProgress({ message: '准备南宁地理图景', value: 0 });
    import('@/lib/city/scene')
      .then(({ createCityScene }) => {
        if (abort.signal.aborted) return null;
        return createCityScene(
          container,
          {
            progress: (message, value) => setProgress({ message, value }),
            ready: (landmarks, summary) => {
              setPlaces(landmarks);
              setOverview(summary);
              setReady(true);
            },
            select: (id) => selectRef.current(id),
            heading: setHeading,
            view: (lon, lat) => setCoordinates([lon, lat]),
            interaction: () => interactionRef.current(),
            error: (message) => {
              setError(message);
              setReady(false);
            },
          },
          abort.signal,
        );
      })
      .then((scene) => {
        if (!scene) return;
        if (abort.signal.aborted) {
          scene.dispose();
          return;
        }
        controller.current = scene;
        scene.apply(options.current);
      })
      .catch((err: unknown) => {
        if (!abort.signal.aborted) {
          setReady(false);
          setError(err instanceof Error ? err.message : '三维场景载入失败');
        }
      });
    return () => {
      abort.abort();
      controller.current?.dispose();
      controller.current = null;
    };
  }, [reload]);

  useEffect(() => {
    if (!tour || !ready) return;
    const timer = window.setInterval(
      () =>
        setSelected((current) => {
          const next = ORDER[(ORDER.indexOf(current ?? '') + 1) % ORDER.length];
          controller.current?.focus(next);
          return next;
        }),
      6500,
    );
    return () => window.clearInterval(timer);
  }, [tour, ready]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const startTour = () => {
    if (tour) {
      setTour(false);
      return;
    }
    const id = selected ?? ORDER[0];
    setSelected(id);
    controller.current?.focus(id);
    setTour(true);
    setAutoRotate(false);
    setMobileOpen(false);
  };
  const reset = () => {
    setSelected(null);
    setTour(false);
    setAutoRotate(false);
    setTopDown(false);
    requestAnimationFrame(() => controller.current?.focus(null));
  };
  const screenshot = async () => {
    if (!controller.current) return;
    setExporting(true);
    try {
      await controller.current.capture();
      setToast('当前三维视图已导出为 PNG');
    } catch {
      setToast('图片导出失败，请再试一次');
    } finally {
      setExporting(false);
    }
  };
  const fullScreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.documentElement.requestFullscreen)
        await document.documentElement.requestFullscreen();
      else setToast('当前浏览器不支持全屏，可使用浏览器的全屏菜单');
    } catch {
      setToast('未能进入全屏，请使用浏览器的全屏菜单');
    }
  };
  const updateLayer = (key: LayerKey, value: boolean) =>
    setLayers((current) => ({ ...current, [key]: value }));
  const timeLabel = `${Math.floor(hour).toString().padStart(2, '0')}:${hour % 1 ? '30' : '00'}`;

  return (
    <main className={`atlas ${night ? 'is-night' : ''}`}>
      <header className="app-header">
        <div className="identity">
          <div className="brand-mark">
            <Mountain strokeWidth={1.35} />
          </div>
          <div className="brand-word">
            邕城<span>NANNING ATLAS</span>
          </div>
          <span className="brand-divider" />
          <p>
            南宁地理图景<span>山 · 水 · 城</span>
          </p>
        </div>
        <div className="header-center">
          <span className="live-dot" />
          广西壮族自治区 <span className="slash">/</span> 南宁
        </div>
        <div className="header-actions">
          <button
            className="text-button about-button"
            onClick={() => setInfoOpen(true)}
          >
            <Info size={16} />
            项目说明
          </button>
          <button
            className="export-button"
            disabled={!ready || exporting}
            onClick={screenshot}
          >
            {exporting ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <ArrowDownToLine size={16} />
            )}
            <span>导出视图</span>
          </button>
        </div>
      </header>

      <button
        className="mobile-menu-button"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-expanded={mobileOpen}
        aria-controls="explorer-sidebar"
      >
        {mobileOpen ? <X size={19} /> : <Menu size={19} />}城市菜单
      </button>
      {mobileOpen && (
        <button
          className="mobile-scrim"
          onClick={() => setMobileOpen(false)}
          aria-label="关闭城市菜单"
        />
      )}
      <aside
        id="explorer-sidebar"
        className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}
      >
        <div className="sidebar-intro">
          <span className="eyebrow">EXPLORE THE GREEN CITY</span>
          <h1>
            探索南宁<span>01 / 广西</span>
          </h1>
          <p>沿着邕江，读懂一座城。</p>
        </div>
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(String(value))}
          className="sidebar-tabs"
        >
          <TabsList className="panel-tabs" aria-label="城市菜单">
            <TabsTrigger value="explore">
              <Compass size={15} />
              探索
            </TabsTrigger>
            <TabsTrigger value="layers">
              <Layers3 size={15} />
              图层
            </TabsTrigger>
            <TabsTrigger value="scene">
              <SlidersHorizontal size={15} />
              环境
            </TabsTrigger>
          </TabsList>
          <TabsContent value="explore" className="tab-body">
            <div className="section-caption">
              <span>城市探索点</span>
              <span>07 个地标</span>
            </div>
            <button
              className={`overview-place ${!selected ? 'active' : ''}`}
              disabled={!ready}
              onClick={() => choose(null)}
            >
              <div className="place-icon overview-icon">
                <Navigation size={21} />
              </div>
              <div>
                <strong>邕江两岸</strong>
                <span>中心城区 · 全景鸟瞰</span>
              </div>
              <ArrowUpRight size={18} />
            </button>
            <div className="place-list">
              {(ready
                ? ordered
                : ORDER.map((id) => ({
                    id,
                    name: (
                      {
                        changyou: '三街两巷 · 畅游阁',
                        nanhu: '南湖公园',
                        diwang: '地王大厦',
                        expo: '国际会展中心',
                        cr: '华润大厦',
                        qingxiu: '青秀山 · 龙象塔',
                        bridge: '南宁大桥',
                      } as Record<string, string>
                    )[id],
                    category: '',
                  }))
              ).map((place, index) => {
                const Icon = iconFor(place.id);
                return (
                  <button
                    key={place.id}
                    className={`place-item ${selected === place.id ? 'active' : ''}`}
                    disabled={!ready}
                    onClick={() => choose(place.id)}
                    aria-pressed={selected === place.id}
                  >
                    <span className="place-number">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className={`place-icon place-${place.id}`}>
                      <Icon size={19} strokeWidth={1.6} />
                    </span>
                    <span className="place-text">
                      <strong>{place.name}</strong>
                      <small>{place.category || '城市探索点'}</small>
                    </span>
                    <ChevronRight size={15} />
                  </button>
                );
              })}
            </div>
            <div className="explore-note">
              <Waves size={18} />
              <p>
                一江穿城，青山入城。
                <br />
                <span>从老城街巷，走向绿城天际线。</span>
              </p>
            </div>
          </TabsContent>
          <TabsContent value="layers" className="tab-body">
            <div className="section-caption">
              <span>地图内容</span>
              <button onClick={() => setLayers({ ...DEFAULT_LAYERS })}>
                全部显示
              </button>
            </div>
            <p className="panel-description">
              选择要观察的城市要素，读清山水与街区的关系。
            </p>
            <div className="layer-list">
              {LAYER_INFO.map(({ key, name, detail, icon: Icon }) => (
                <div className="layer-row" key={key}>
                  <Icon size={20} />
                  <label htmlFor={`layer-${key}`}>
                    <strong>{name}</strong>
                    <span>{detail}</span>
                  </label>
                  <Switch
                    id={`layer-${key}`}
                    checked={layers[key]}
                    onCheckedChange={(value) => updateLayer(key, value)}
                    aria-label={name}
                  />
                </div>
              ))}
            </div>
            <div className="data-card">
              <span className="eyebrow">GEOGRAPHIC SNAPSHOT</span>
              <h3>看得见的城市脉络</h3>
              <dl>
                <div>
                  <dt>地图建筑</dt>
                  <dd>
                    {overview?.stats.mappedBuildings.toLocaleString() ?? '—'}
                    <small>栋</small>
                  </dd>
                </div>
                <div>
                  <dt>简化补充</dt>
                  <dd>
                    {overview?.stats.infillBuildings.toLocaleString() ?? '—'}
                    <small>栋</small>
                  </dd>
                </div>
                <div>
                  <dt>道路片段</dt>
                  <dd>
                    {overview?.stats.roadSegments.toLocaleString() ?? '—'}
                    <small>段</small>
                  </dd>
                </div>
              </dl>
              <p>补充建筑用于表达街区密度，位置与高度均为示意。</p>
            </div>
          </TabsContent>
          <TabsContent value="scene" className="tab-body">
            <div className="section-caption">
              <span>光照与视角</span>
              <Sun size={15} />
            </div>
            <p className="panel-description">把一天的光，留在城市里。</p>
            <div className="time-display">
              <span>{timeLabel}</span>
              <div>
                {hour < 10
                  ? '晨光'
                  : hour < 17
                    ? '日间'
                    : hour < 19
                      ? '落日'
                      : '夜色'}
                <small>场景模拟时间</small>
              </div>
            </div>
            <Slider
              className="time-slider"
              value={[hour]}
              onValueChange={(value) =>
                setHour(Array.isArray(value) ? value[0] : value)
              }
              min={6}
              max={22}
              step={0.5}
              aria-label="场景时间"
            />
            <div className="slider-ends">
              <span>06:00</span>
              <span>22:00</span>
            </div>
            <div className="time-presets">
              {[
                { hour: 8, text: '晨光', icon: Sun },
                { hour: 14, text: '日间', icon: Sun },
                { hour: 18, text: '日落', icon: Sunset },
                { hour: 21, text: '夜色', icon: Moon },
              ].map(({ hour: h, text, icon: Icon }) => (
                <button
                  key={h}
                  className={hour === h ? 'active' : ''}
                  onClick={() => setHour(h)}
                  aria-pressed={hour === h}
                >
                  <Icon size={18} />
                  {text}
                </button>
              ))}
            </div>
            <div className="setting-divider" />
            <div className="setting-row">
              <label htmlFor="height-scale">
                高度夸张<small>同时调整地形与建筑的竖向比例</small>
              </label>
              <strong>{heightScale.toFixed(1)}×</strong>
            </div>
            <Slider
              id="height-scale"
              value={[heightScale]}
              onValueChange={(value) =>
                setHeightScale(Array.isArray(value) ? value[0] : value)
              }
              min={0.5}
              max={2}
              step={0.1}
              aria-label="高度夸张"
            />
            <div className="slider-ends">
              <span>平缓 0.5×</span>
              <span>突出 2.0×</span>
            </div>
            <div className="setting-divider" />
            <div className="setting-row">
              <label htmlFor="top-down">
                俯视地图<small>从正上方观察地理布局</small>
              </label>
              <Switch
                id="top-down"
                checked={topDown}
                onCheckedChange={setTopDown}
              />
            </div>
            <div className="setting-row">
              <label htmlFor="auto-orbit">
                环绕观察<small>镜头缓慢围绕当前中心旋转</small>
              </label>
              <Switch
                id="auto-orbit"
                checked={autoRotate}
                onCheckedChange={(value) => {
                  setAutoRotate(value);
                  setTour(false);
                }}
              />
            </div>
            <button
              className="restore-settings"
              onClick={() => {
                setHour(14);
                setHeightScale(1);
                setTopDown(false);
                setAutoRotate(false);
              }}
            >
              恢复默认环境 <RotateCcw size={14} />
            </button>
          </TabsContent>
        </Tabs>
        <div className="sidebar-bottom">
          <button
            className={`tour-button ${tour ? 'tour-playing' : ''}`}
            disabled={!ready}
            onClick={startTour}
          >
            {tour ? (
              <Pause size={16} fill="currentColor" />
            ) : (
              <Play size={16} fill="currentColor" />
            )}
            <span>{tour ? '暂停城市漫游' : '开始城市漫游'}</span>
            <span className="tour-duration">
              {tour ? `${ORDER.indexOf(selected ?? '') + 1} / 7` : '7 站'}
            </span>
          </button>
          <button className="help-button" onClick={() => setInfoOpen(true)}>
            <CircleHelp size={14} />
            操作指南与数据来源
            <ArrowUpRight size={13} />
          </button>
        </div>
      </aside>

      <section className="map-stage" aria-label="三维地理沙盘">
        <div className="scene-host" ref={host} />
        <div className="map-title">
          <div className="map-kicker">
            <span className="tiny-square" />
            广西 · 南宁<span className="map-version">3D ATLAS / 01</span>
          </div>
          <h2>{active ? active.name : '邕江河谷 · 中心城区'}</h2>
          <p>
            {active
              ? `${active.lon.toFixed(4)}° E  /  ${active.lat.toFixed(4)}° N`
              : '一条邕江，连接山水与城市。'}
          </p>
        </div>
        <div className="view-badges">
          <span className="view-chip">
            <span className="live-dot" />
            {ready ? '三维场景' : '载入中'}
          </span>
          <button
            className="view-chip time-chip"
            onClick={() => {
              setTab('scene');
              setMobileOpen(true);
            }}
          >
            {night ? (
              <Moon size={14} />
            ) : hour >= 17 ? (
              <Sunset size={14} />
            ) : (
              <Sun size={14} />
            )}
            <span>{timeLabel}</span>
          </button>
        </div>
        {!ready && (
          <div className="loading-card" role={error ? 'alert' : 'status'}>
            {error ? (
              <>
                <Info size={26} />
                <h3>暂时无法打开三维场景</h3>
                <p>{error}</p>
                <button
                  className="retry-button"
                  onClick={() => setReload((r) => r + 1)}
                >
                  重新载入 <RotateCcw size={15} />
                </button>
              </>
            ) : (
              <>
                <Mountain size={30} strokeWidth={1.25} />
                <h3>正在展开南宁</h3>
                <p>{progress.message}</p>
                <div className="loading-track">
                  <span style={{ width: `${progress.value}%` }} />
                </div>
                <span className="load-percent">
                  {Math.round(progress.value)}%
                </span>
              </>
            )}
          </div>
        )}
        <div className="map-toolbar">
          <button
            className="north-button"
            onClick={() => controller.current?.north()}
            disabled={!ready}
            aria-label="朝向正北"
          >
            <span>N</span>
            <Navigation
              size={21}
              style={{ transform: `rotate(${-heading}deg)` }}
            />
          </button>
          <div className="tool-group">
            <button
              onClick={() => controller.current?.zoom(0.78)}
              disabled={!ready}
              aria-label="放大"
            >
              <Plus size={20} />
            </button>
            <button
              onClick={() => controller.current?.zoom(1.28)}
              disabled={!ready}
              aria-label="缩小"
            >
              <Minus size={20} />
            </button>
          </div>
          <div className="tool-group">
            <button onClick={reset} disabled={!ready} aria-label="返回全景">
              <Focus size={19} />
            </button>
            <button
              className={topDown ? 'active' : ''}
              onClick={() => setTopDown(!topDown)}
              disabled={!ready}
              aria-label={topDown ? '切换倾斜视角' : '切换俯视地图'}
              aria-pressed={topDown}
            >
              <Layers3 size={18} />
            </button>
            <button onClick={fullScreen} aria-label="全屏查看">
              <Expand size={18} />
            </button>
          </div>
        </div>
        {active && (
          <article className="place-detail">
            <div className="detail-heading">
              <span>{active.category}</span>
              <button onClick={() => choose(null)} aria-label="关闭地标详情">
                <X size={16} />
              </button>
            </div>
            <h3>{active.name}</h3>
            <p>{active.description}</p>
            <div className="detail-footer">
              <span>
                <MapPin size={13} />
                {active.lon.toFixed(4)}° E · {active.lat.toFixed(4)}° N
              </span>
              <button
                onClick={() =>
                  choose(ORDER[(ORDER.indexOf(active.id) + 1) % ORDER.length])
                }
              >
                下一站
                <ArrowRight size={15} />
              </button>
            </div>
          </article>
        )}
        <div className="map-bottom-left">
          <div className="legend">
            <span>
              <i className="legend-water" />
              水系
            </span>
            <span>
              <i className="legend-forest" />
              山林
            </span>
            <span>
              <i className="legend-city" />
              建成区
            </span>
          </div>
          <div className="interaction-hint">
            <MousePointer2 size={14} />
            <span>拖动旋转</span>
            <span>右键平移</span>
            <span>滚轮缩放</span>
          </div>
        </div>
        {overview && (
          <MiniMap
            overview={overview}
            places={places}
            selected={selected}
            onReset={reset}
          />
        )}
        <footer className="map-status">
          <span>
            {coordinates[0].toFixed(4)}° E{' '}
            <span className="status-divider">/</span>{' '}
            {coordinates[1].toFixed(4)}° N
          </span>
          <button onClick={() => setInfoOpen(true)}>
            艺术化地理重建 <span className="status-divider">·</span> ©
            OpenStreetMap / Mapzen
          </button>
        </footer>
        {toast && (
          <output className="toast">
            <Check size={16} />
            {toast}
          </output>
        )}
      </section>
      <Sheet open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent className="info-sheet">
          <SheetHeader>
            <span className="eyebrow">ABOUT THIS ATLAS</span>
            <SheetTitle>山水为骨，城市为景。</SheetTitle>
            <SheetDescription>邕城 · 南宁地理图景</SheetDescription>
          </SheetHeader>
          <div className="info-content">
            <p>
              这是覆盖南宁中心城区的可交互地理沙盘。以真实河道、路网、建筑轮廓与公开高程数据为基础，用青绿山水与浅色建筑表达城市结构。
            </p>
            <h3>怎样探索</h3>
            <ul className="guide-list">
              <li>
                <MousePointer2 size={18} />
                <div>
                  <strong>自由观察</strong>
                  <p>
                    鼠标左键旋转，右键平移，滚轮缩放。触屏单指旋转，双指缩放与平移。
                  </p>
                </div>
              </li>
              <li>
                <MapPin size={18} />
                <div>
                  <strong>地标与漫游</strong>
                  <p>
                    点击地图标记或左侧探索点，镜头会飞往地标。城市漫游每 6.5
                    秒切换一站，手动拖动会暂停。
                  </p>
                </div>
              </li>
              <li>
                <Layers3 size={18} />
                <div>
                  <strong>图层与环境</strong>
                  <p>
                    开关建筑、水面、树木、道路和标注；调整光照、竖向比例与俯视角度。
                  </p>
                </div>
              </li>
              <li>
                <Eye size={18} />
                <div>
                  <strong>键盘操作</strong>
                  <p>
                    聚焦地图后使用方向键平移，+ / − 缩放，Home 复位。Tab
                    可访问菜单与地标。
                  </p>
                </div>
              </li>
            </ul>
            <h3>范围与精度</h3>
            <p>
              范围：108.265°–108.465° E，22.735°–22.875° N，约 20.5 × 15.6
              km。表现南宁中心城区，未覆盖南宁全市行政范围。
            </p>
            <p>
              地形使用公开 DEM 网格，初始高程起伏放大 3 倍；建筑高度初始放大
              1.55
              倍。水面经统一显示高度处理。地图缺少高度的建筑采用估算值，补充街区和地标造型为程序化示意。
            </p>
            <p>
              该沙盘用于空间浏览与视觉表达，不提供测绘、导航或洪水分析精度。模拟光照不是实时天气，也不对应精确天文日照。
            </p>
            <h3>公开数据与制作</h3>
            <div className="source-list">
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                OpenStreetMap contributors
                <span>
                  河道、道路、绿地与建筑 · ODbL 1.0
                  <ArrowUpRight size={14} />
                </span>
              </a>
              <a
                href="https://registry.opendata.aws/terrain-tiles/"
                target="_blank"
                rel="noreferrer"
              >
                Mapzen / AWS Terrain Tiles
                <span>
                  高程 · SRTM data courtesy of USGS
                  <ArrowUpRight size={14} />
                </span>
              </a>
              <a
                href="https://github.com/wcqqq1214/nanning-city-atlas"
                target="_blank"
                rel="noreferrer"
              >
                项目源码与 Blender 文件
                <span>
                  Three.js + Blender · GitHub
                  <ArrowUpRight size={14} />
                </span>
              </a>
            </div>
            <p className="source-date">
              地图快照：{overview?.osmTimestamp?.slice(0, 10) ?? '2026-09-08'}
              。完整许可与重建流程见仓库文档。
            </p>
          </div>
        </SheetContent>
      </Sheet>
    </main>
  );
}
