'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpRight,
  Building2,
  GraduationCap,
  Landmark as LandmarkIcon,
  Check,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  Search,
  Orbit,
  Grid2X2,
  Compass,
  Expand,
  Ellipsis,
  Eye,
  Focus,
  Info,
  Layers3,
  LoaderCircle,
  MapPin,
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
  Trophy,
  Sunset,
  Trees,
  TrainFront,
  Waves,
  X,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useCompactLayout, useReducedMotion } from '@/lib/city/display';
import { searchLandmarks } from '@/lib/city/navigation';
import { assetUrl } from '@/lib/city/assets';
import { Slider } from '@/components/ui/slider';
import {
  Sheet,
  SheetContent,
  SheetClose,
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
  type QualityPreference,
  type SceneMetrics,
} from '@/lib/city/types';
import { registerAtlasTools } from '@/lib/city/webmcp';
import { BridgeIcon } from '@/components/bridge-icon';
import {
  LANDMARK_CATEGORIES,
  landmarkCategory,
  type LandmarkCategory,
} from '@/lib/city/landmark-categories';
import landmarkCatalog from '@/data/landmarks.json';
import region from '@/data/region.json';
import { landmarkArea } from '@/lib/city/landmark-areas';

const ORDER = landmarkCatalog.map((place) => place.id);
const LAYER_INFO: {
  key: LayerKey;
  name: string;
  detail: string;
  icon: typeof Building2;
}[] = [
  {
    key: 'buildings',
    name: '城市建筑',
    detail: '普通建筑和城市地标',
    icon: Building2,
  },
  {
    key: 'vegetation',
    name: '林木植被',
    detail: '山林、江边和公园里的树木',
    icon: Trees,
  },
  {
    key: 'roads',
    name: '道路桥梁',
    detail: '道路、高架和跨江大桥',
    icon: Route,
  },
  {
    key: 'railways',
    name: '铁路轨道',
    detail: '铁路、站场股道与铁路桥',
    icon: TrainFront,
  },
  {
    key: 'water',
    name: '河流湖泊',
    detail: '邕江、南湖与城区水面',
    icon: Waves,
  },
  { key: 'labels', name: '地名标注', detail: '可点击的城市地标', icon: MapPin },
];
const iconFor = (place: Pick<Landmark, 'id' | 'category'>) => {
  const { id } = place;
  if (landmarkCategory(place) === 'bridges') return BridgeIcon;
  if (id === 'qingxiang-viaduct') return Route;
  if (id === 'qingxiu') return Mountain;
  if (id === 'zhenning') return LandmarkIcon;
  if (['gxu', 'gxmzu'].includes(id)) return GraduationCap;
  if (id === 'east-station' || id === 'nanning-station') return TrainFront;
  if (id === 'sports-center') return Trophy;
  if (['nanhu', 'xiangsi', 'mingyue', 'tingzi'].includes(id)) return Waves;
  if (['gx-museum', 'ethnic-museum', 'confucius'].includes(id))
    return LandmarkIcon;
  if (landmarkCategory(place) === 'nature') return Trees;
  if (landmarkCategory(place) === 'culture') return LandmarkIcon;
  return Building2;
};

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
  const dock = useRef<HTMLElement>(null);
  const dockBody = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const detailBack = useRef<HTMLButtonElement>(null);
  const menuScroll = useRef(0);
  const measureViewport = useRef<() => void>(() => {});
  const pendingFocus = useRef<'menu' | 'detail' | null>(null);
  const isMobile = useCompactLayout();
  const reducedMotion = useReducedMotion();
  const [quality, setQuality] = useState<QualityPreference>('auto');
  const [metrics, setMetrics] = useState<SceneMetrics | null>(null);
  const showStats =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).has('stats');
  const [panelMode, setPanelMode] = useState<'menu' | 'detail'>('menu');
  const [collapsed, setCollapsed] = useState(false);
  const [panelExpanded, setPanelExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [tourStarted, setTourStarted] = useState(false);
  const [detailView, setDetailView] = useState<'overview' | 'close'>(
    'overview',
  );
  const controller = useRef<SceneController | null>(null);
  const [places, setPlaces] = useState<Landmark[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [progress, setProgress] = useState({
    message: '正在加载地图',
    value: 0,
  });
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState('explore');
  const [selected, setSelected] = useState<string | null>(null);
  const [category, setCategory] = useState<LandmarkCategory | 'all'>('all');
  const [layers, setLayers] = useState({ ...DEFAULT_LAYERS });
  const [hour, setHour] = useState(14);
  const [heightScale, setHeightScale] = useState(1);
  const [autoRotate, setAutoRotate] = useState(false);
  const [topDown, setTopDown] = useState(false);
  const [tour, setTour] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
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
  const activeArea = landmarkArea(selected);
  const ordered = ORDER.map((id) => places.find((p) => p.id === id)).filter(
    (p): p is Landmark => Boolean(p),
  );
  const groupedPlaces = LANDMARK_CATEGORIES.map((group) => ({
    ...group,
    places: (ready ? ordered : landmarkCatalog).filter(
      (place) => landmarkCategory(place) === group.id,
    ),
  })).filter((group) => group.places.length > 0);
  const visibleGroups = groupedPlaces
    .filter((group) => category === 'all' || category === group.id)
    .map((group) => ({
      ...group,
      places: searchLandmarks(group.places, query),
    }))
    .filter((group) => group.places.length > 0);
  const resultCount = visibleGroups.reduce(
    (sum, group) => sum + group.places.length,
    0,
  );
  const night = hour >= 19;

  const pauseMotion = useCallback(() => {
    setTour(false);
    setAutoRotate(false);
  }, []);
  const openInfo = () => {
    pauseMotion();
    setInfoOpen(true);
  };
  useEffect(() => {
    const pauseWhenHidden = () => {
      if (document.hidden) pauseMotion();
    };
    document.addEventListener('visibilitychange', pauseWhenHidden);
    return () =>
      document.removeEventListener('visibilitychange', pauseWhenHidden);
  }, [pauseMotion]);

  const choose = useCallback((id: string | null) => {
    setSelected(id);
    if (!id) setTourStarted(false);
    setPanelMode(id ? 'detail' : 'menu');
    setDetailView('overview');
    setCollapsed(false);
    setPanelExpanded(false);
    pendingFocus.current = id ? 'detail' : null;
    setTour(false);
    setAutoRotate(false);

    requestAnimationFrame(() => {
      measureViewport.current();
      controller.current?.focus(id);
    });
  }, []);
  useEffect(() => {
    selectRef.current = choose;
    interactionRef.current = pauseMotion;
  }, [choose, pauseMotion]);
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
    setMetrics(null);
    setProgress({ message: '正在加载地图', value: 0 });
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
            metrics: setMetrics,
            view: (lon, lat) => setCoordinates([lon, lat]),
            interaction: () => interactionRef.current(),
            error: (message) => {
              setError(message);
              setReady(false);
            },
          },
          abort.signal,
          quality,
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
        if (options.current.selected) scene.focus(options.current.selected);
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
  }, [reload, quality]);

  useEffect(() => {
    if (!tour || !ready) return;
    const timer = window.setTimeout(() => {
      const next = ORDER[(ORDER.indexOf(selected ?? '') + 1) % ORDER.length];
      setSelected(next);
      setDetailView('overview');
      controller.current?.focus(next);
    }, 6500);
    return () => window.clearTimeout(timer);
  }, [tour, ready, selected]);

  useEffect(() => {
    if (!dock.current || !host.current) return;
    const root = dock.current.closest<HTMLElement>('.atlas')!;
    const measure = () => {
      const panel = dock.current!.getBoundingClientRect();
      const scene = host.current!.getBoundingClientRect();
      root.style.setProperty('--dock-height', `${panel.height}px`);
      const bottomDock = isMobile && window.innerHeight > 520;
      const left = bottomDock ? 20 : panel.right + 24;
      root.style.setProperty('--scene-left', `${left}px`);
      controller.current?.setViewport({
        left,
        top: isMobile ? 45 : 90,
        width: Math.max(120, scene.width - left - (isMobile ? 68 : 84)),
        height: Math.max(
          100,
          (bottomDock ? panel.top - scene.top : scene.height - 32) -
            (isMobile ? 55 : 90),
        ),
      });
    };
    measureViewport.current = measure;
    const observer = new ResizeObserver(measure);
    observer.observe(dock.current);
    observer.observe(host.current);
    measure();
    return () => observer.disconnect();
  }, [ready, isMobile, collapsed]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const update = () => {
      // Keep the bottom panel above the software keyboard on mobile browsers.
      dock.current
        ?.closest<HTMLElement>('.atlas')
        ?.style.setProperty(
          '--app-height',
          `${viewport?.height ?? window.innerHeight}px`,
        );
    };
    update();
    viewport?.addEventListener('resize', update);
    return () => viewport?.removeEventListener('resize', update);
  }, []);

  useEffect(() => {
    if (collapsed || !pendingFocus.current) return;
    const destination = pendingFocus.current;
    pendingFocus.current = null;
    if (destination === 'detail') {
      if (dockBody.current) dockBody.current.scrollTop = 0;
      detailBack.current?.focus({ preventScroll: true });
    } else {
      const row = Array.from(
        dock.current?.querySelectorAll<HTMLButtonElement>('[data-place-id]') ??
          [],
      ).find((element) => element.dataset.placeId === selected);
      (row ?? searchInput.current)?.focus({ preventScroll: true });
      if (dockBody.current) dockBody.current.scrollTop = menuScroll.current;
    }
  }, [panelMode, collapsed, selected]);

  const returnToMenu = () => {
    setTour(false);
    setAutoRotate(false);
    setPanelMode('menu');
    setTab('explore');
    setPanelExpanded(true);
    pendingFocus.current = 'menu';
  };
  const changeView = (view: 'overview' | 'top' | 'close') => {
    setTour(false);
    setAutoRotate(false);
    setTopDown(view === 'top');
    setDetailView(view === 'close' ? 'close' : 'overview');
    requestAnimationFrame(() => {
      measureViewport.current();
      controller.current?.focus(selected, view === 'close');
    });
  };
  const jump = (delta: number) => {
    const id =
      ORDER[
        (ORDER.indexOf(selected ?? ORDER[0]) + delta + ORDER.length) %
          ORDER.length
      ];
    setSelected(id);
    setDetailView('overview');
    setPanelMode('detail');
    setAutoRotate(false);
    requestAnimationFrame(() => {
      measureViewport.current();
      controller.current?.focus(id);
    });
  };
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
    requestAnimationFrame(() => {
      measureViewport.current();
      controller.current?.focus(id);
    });
    setTour(true);
    setTourStarted(true);
    setPanelMode('detail');
    setPanelExpanded(false);
    setDetailView('overview');
    setAutoRotate(false);
  };
  const reset = () => {
    setSelected(null);
    setPanelExpanded(false);
    setPanelMode('menu');
    setTourStarted(false);
    setTour(false);
    setAutoRotate(false);
    setTopDown(false);
    requestAnimationFrame(() => {
      measureViewport.current();
      controller.current?.focus(null);
    });
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

  const sidebar = (
    <>
      <Tabs
        value={tab}
        onValueChange={(value) => {
          pauseMotion();
          setTab(String(value));
          if (dockBody.current) dockBody.current.scrollTop = 0;
        }}
        className="sidebar-tabs"
      >
        <TabsList className="panel-tabs" aria-label="城市菜单">
          <TabsTrigger value="explore">
            <Compass size={15} />
            地点
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
          <div className="search-wrap">
            <Search size={17} aria-hidden="true" />
            <input
              ref={searchInput}
              type="search"
              value={query}
              placeholder="搜索地标，如南湖、西大"
              aria-label="搜索南宁地标"
              onFocus={() => {
                pauseMotion();
                setPanelExpanded(true);
              }}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
            />
            {query && (
              <button
                aria-label="清除搜索"
                onClick={() => {
                  setQuery('');
                  searchInput.current?.focus();
                }}
              >
                <X size={16} />
              </button>
            )}
          </div>
          <div className="browse-actions">
            <button
              className="overview-shortcut"
              disabled={!ready}
              onClick={() => choose(null)}
            >
              <Navigation size={15} />
              城市全景
            </button>
            <button
              className="filter-toggle"
              aria-expanded={filtersOpen}
              aria-controls="place-filters"
              onClick={() => {
                setFiltersOpen((value) => !value);
                if (!filtersOpen && isMobile) setPanelExpanded(true);
              }}
            >
              <SlidersHorizontal size={15} />
              {category === 'all'
                ? '筛选'
                : LANDMARK_CATEGORIES.find((item) => item.id === category)
                    ?.shortName}
              <ChevronDown size={14} />
            </button>
          </div>
          <fieldset
            id="place-filters"
            className="place-category-filters"
            aria-label="地标分类"
            hidden={!filtersOpen}
          >
            <button
              type="button"
              aria-pressed={category === 'all'}
              onClick={() => setCategory('all')}
            >
              全部
            </button>
            {groupedPlaces.map((group) => (
              <button
                key={group.id}
                type="button"
                aria-label={`${group.name}，${group.places.length}处`}
                aria-pressed={category === group.id}
                onClick={() => setCategory(group.id)}
              >
                {group.shortName}
                <span aria-hidden="true">{group.places.length}</span>
              </button>
            ))}
          </fieldset>
          <output
            className="result-heading"
            aria-live="polite"
            aria-atomic="true"
          >
            <span>
              {query.trim()
                ? '搜索结果'
                : category === 'all'
                  ? '全部地点'
                  : '当前分类'}
              <small>
                {category !== 'all'
                  ? ` · ${LANDMARK_CATEGORIES.find((item) => item.id === category)?.name}`
                  : ''}
              </small>
            </span>
            <span>{resultCount} 处</span>
          </output>
          <div className="place-list">
            {!resultCount && (
              <div className="empty-state">
                <Search size={24} />
                <p>没有找到相关地标</p>
                <span>换个名称，或清除分类和搜索条件。</span>
                <button
                  onClick={() => {
                    setQuery('');
                    setCategory('all');
                    searchInput.current?.focus();
                  }}
                >
                  查看全部地标
                </button>
              </div>
            )}
            {visibleGroups.map((group) => (
              <section
                key={group.id}
                className="place-group"
                aria-label={group.name}
              >
                <h3 className="place-group-heading">
                  {group.name}
                  <span>{group.places.length} 处</span>
                </h3>
                {group.places.map((place) => {
                  const Icon = iconFor(place);
                  return (
                    <button
                      key={place.id}
                      data-place-id={place.id}
                      className={`place-item ${selected === place.id ? 'active' : ''}`}
                      disabled={!ready}
                      onClick={() => choose(place.id)}
                      aria-pressed={selected === place.id}
                    >
                      <span
                        className={`place-icon place-${place.id} category-${group.id}`}
                      >
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
              </section>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="layers" className="tab-body">
          <div className="section-caption">
            <span>地图内容</span>
            <button onClick={() => setLayers({ ...DEFAULT_LAYERS })}>
              全部显示
            </button>
          </div>
          <p className="panel-description">选择地图上要显示的内容。</p>
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
          <details className="menu-disclosure data-disclosure">
            <summary>
              地图数据与精度 <ChevronDown size={15} />
            </summary>
            <div className="data-card">
              <span className="eyebrow">GEOGRAPHIC SNAPSHOT</span>
              <h3>地图数据</h3>
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
              <p>部分建筑由程序补充，位置和高度不代表实景。</p>
            </div>
          </details>
        </TabsContent>
        <TabsContent value="scene" className="tab-body">
          <div className="section-caption">
            <span>光照与视角</span>
            <Sun size={15} />
          </div>
          <p className="panel-description">
            调整时间，查看晨昏光照、夜间窗灯与地标亮化。
          </p>
          <div className="time-presets">
            {[
              { hour: 8, text: '晨光', caption: '清晨的邕江', icon: Sun },
              { hour: 14, text: '日间', caption: '明亮的城市', icon: Sun },
              { hour: 18, text: '日落', caption: '江岸染上暖金', icon: Sunset },
              { hour: 21, text: '夜色', caption: '灯火沿江亮起', icon: Moon },
            ].map(({ hour: h, text, caption, icon: Icon }) => (
              <button
                key={h}
                className={`light-preset light-${h} ${hour === h ? 'active' : ''}`}
                onClick={() => setHour(h)}
                aria-pressed={hour === h}
              >
                <span className="light-art" aria-hidden="true">
                  <i />
                  <b />
                  <em />
                </span>
                <span className="light-name">
                  <Icon size={16} />
                  {text}
                  {hour === h && <Check size={14} />}
                </span>
                <small>{caption}</small>
              </button>
            ))}
          </div>
          <details className="menu-disclosure">
            <summary>
              <span>
                精确时间 <strong>{timeLabel}</strong>
              </span>
              <ChevronDown size={15} />
            </summary>
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
          </details>
          <details className="menu-disclosure">
            <summary>
              <span id="quality-label">
                画质{' '}
                <strong>
                  {{ auto: '自动', smooth: '流畅', detail: '精细' }[quality]}
                </strong>
              </span>
              <ChevronDown size={15} />
            </summary>
            <RadioGroup
              className="quality-options"
              aria-labelledby="quality-label"
              value={quality}
              onValueChange={(value) => {
                setTour(false);
                setAutoRotate(false);
                setDetailView('overview');
                setQuality(value as QualityPreference);
              }}
            >
              {(
                [
                  ['auto', '自动'],
                  ['smooth', '流畅'],
                  ['detail', '精细'],
                ] as const
              ).map(([value, label]) => (
                <label
                  key={value}
                  className={quality === value ? 'active' : ''}
                >
                  <RadioGroupItem value={value} />
                  {label}
                </label>
              ))}
            </RadioGroup>
            <p className="quality-note">
              手机默认使用轻量模型。流畅模式减少渲染负担，精细模式保留更多树木和阴影。切换画质会重新加载地图。
            </p>
          </details>
          <details className="menu-disclosure">
            <summary>
              高度与视角 <ChevronDown size={15} />
            </summary>
            <div className="setting-row">
              <label htmlFor="height-scale">
                高度比例<small>同时拉高或压低山地和建筑</small>
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
              aria-label="高度比例"
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
                disabled={reducedMotion}
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
          </details>
        </TabsContent>
      </Tabs>
      <div className="panel-foot">
        <button onClick={openInfo}>
          <Info size={14} />
          地图说明与数据来源 <ArrowUpRight size={13} />
        </button>
        {active && (
          <button
            className="return-landmark"
            onClick={() => {
              setPanelMode('detail');
              setPanelExpanded(false);
              pendingFocus.current = 'detail';
            }}
          >
            继续查看 {active.name}
            <ChevronRight size={14} />
          </button>
        )}
      </div>
    </>
  );

  return (
    <main
      className={`atlas ${night ? 'is-night' : ''} ${active ? 'has-selection' : ''} ${collapsed ? 'panel-collapsed' : ''} ${panelExpanded ? 'panel-expanded' : ''}`}
    >
      <header className="app-header">
        <div className="identity">
          <div className="brand-mark">
            <Mountain strokeWidth={1.35} />
          </div>
          <h1 className="brand-word">
            邕城<span>NANNING ATLAS</span>
          </h1>
          <span className="brand-divider" />
          <p>
            南宁三维地图<span>山 · 水 · 城</span>
          </p>
        </div>
        <div className="header-center">
          <span className="live-dot" />
          广西壮族自治区 <span className="slash">/</span> 南宁
        </div>
        <div className="header-actions">
          <button className="text-button about-button" onClick={openInfo}>
            <Info size={16} />
            项目说明
          </button>
          <button
            className="export-button"
            aria-label="导出视图"
            title="导出视图"
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
          <a
            className="repo-link"
            href="https://github.com/wcqqq1214/nanning-city-atlas"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="在新标签页打开 GitHub 仓库"
          >
            GitHub <ArrowUpRight size={15} aria-hidden="true" />
          </a>
        </div>
      </header>

      <aside
        ref={dock}
        className={`panel-dock ${collapsed ? 'collapsed' : ''} ${panelExpanded ? 'expanded' : ''} ${panelMode === 'detail' ? 'detail-mode' : ''}`}
        aria-label="南宁浏览面板"
      >
        <div className="dock-heading">
          {panelMode === 'detail' && active && !collapsed ? (
            <button
              ref={detailBack}
              className="dock-back"
              onClick={returnToMenu}
            >
              <ChevronLeft size={16} />
              返回列表
            </button>
          ) : (
            <span className="dock-title">
              {collapsed && active ? active.name : '探索南宁'}
              <small>NANNING ATLAS</small>
            </span>
          )}
          <div className="dock-heading-actions">
            {!collapsed && (
              <button
                className="dock-expand"
                aria-expanded={panelExpanded}
                aria-controls="city-panel-body"
                onClick={() => setPanelExpanded((value) => !value)}
              >
                {panelExpanded ? '简要' : '展开'}
              </button>
            )}
            <button
              className="dock-toggle"
              aria-label={collapsed ? '展开浏览面板' : '收起浏览面板'}
              aria-expanded={!collapsed}
              aria-controls="city-panel-body"
              onClick={() => setCollapsed((value) => !value)}
            >
              <ChevronDown size={18} />
            </button>
          </div>
        </div>
        <div
          ref={dockBody}
          id="city-panel-body"
          className="dock-body"
          hidden={collapsed}
          onScroll={(event) => {
            if (panelMode === 'menu' && tab === 'explore')
              menuScroll.current = event.currentTarget.scrollTop;
          }}
        >
          {panelMode === 'detail' && active ? (
            <article className="place-detail" aria-label="地标详情">
              <span className="eyebrow">{active.category}</span>
              <h2>{active.name}</h2>
              <div className="detail-location">
                <MapPin size={13} />
                {active.lon.toFixed(4)}° E · {active.lat.toFixed(4)}° N
              </div>
              <p>{active.description}</p>
              {activeArea && (
                <span className="detail-area">
                  {activeArea.name} · 范围示意
                </span>
              )}
              <fieldset
                className="landmark-views"
                aria-label="地标观察视角"
                disabled={!ready}
              >
                <button
                  aria-pressed={
                    !topDown && !autoRotate && detailView === 'overview'
                  }
                  onClick={() => changeView('overview')}
                >
                  <Focus size={16} />
                  全貌
                </button>
                <button
                  aria-pressed={topDown && !autoRotate}
                  onClick={() => changeView('top')}
                >
                  <Grid2X2 size={16} />
                  俯视
                </button>
                <button
                  aria-pressed={autoRotate}
                  disabled={reducedMotion}
                  title={
                    reducedMotion ? '系统已启用减少动态效果' : '环绕当前地标'
                  }
                  onClick={() => {
                    setTour(false);
                    setTopDown(false);
                    setAutoRotate((value) => !value);
                  }}
                >
                  <Orbit size={16} />
                  {autoRotate ? '暂停环绕' : '环绕'}
                </button>
                {active.closeDistance && (
                  <button
                    aria-pressed={
                      detailView === 'close' && !topDown && !autoRotate
                    }
                    onClick={() => changeView('close')}
                  >
                    <Eye size={16} />
                    近景
                  </button>
                )}
              </fieldset>
              <button
                className="detail-overview"
                onClick={reset}
                disabled={!ready}
              >
                <Navigation size={15} />
                返回城市全景
                <ArrowUpRight size={15} />
              </button>
            </article>
          ) : (
            sidebar
          )}
        </div>
        <div className={`tour-bar ${tourStarted ? 'tour-active' : ''}`}>
          {tourStarted && !collapsed && (
            <div className="tour-heading">
              <span>
                <i className={tour ? 'live-dot' : ''} />
                {tour ? '正在漫游' : '漫游已暂停'}
                <small>
                  {ORDER.indexOf(selected ?? '') + 1} / {ORDER.length} ·{' '}
                  {active?.name}
                </small>
              </span>
              <button
                aria-label="结束城市漫游"
                onClick={() => {
                  setTour(false);
                  setTourStarted(false);
                }}
              >
                <X size={16} />
              </button>
            </div>
          )}
          <div className="tour-controls">
            {tourStarted && !collapsed && (
              <button
                className="tour-skip"
                aria-label="上一站"
                disabled={!ready}
                onClick={() => jump(-1)}
              >
                <ChevronLeft size={18} />
              </button>
            )}
            <button
              className="tour-button"
              disabled={!ready}
              onClick={startTour}
            >
              {tour ? (
                <Pause size={15} fill="currentColor" />
              ) : (
                <Play size={15} fill="currentColor" />
              )}
              <span>
                {tour ? '暂停漫游' : tourStarted ? '继续漫游' : '开始城市漫游'}
              </span>
              <small>
                {tourStarted
                  ? `${ORDER.indexOf(selected ?? '') + 1} / ${ORDER.length}`
                  : `${ORDER.length} 站`}
              </small>
            </button>
            {tourStarted && !collapsed && (
              <button
                className="tour-skip"
                aria-label="下一站"
                disabled={!ready}
                onClick={() => jump(1)}
              >
                <ChevronRight size={18} />
              </button>
            )}
          </div>
        </div>
      </aside>

      <section className="map-stage" aria-label="三维地理沙盘">
        <div className="scene-host" ref={host} />
        <div className="map-title">
          <div className="map-kicker">
            <span className="tiny-square" />
            广西 · 南宁<span className="map-version">3D ATLAS / 01</span>
          </div>
          <h2>{active ? active.name : '南宁城区 · 邕江两岸'}</h2>
          <p>
            {active
              ? `${active.lon.toFixed(4)}° E  /  ${active.lat.toFixed(4)}° N`
              : '石埠、相思湖、老城、青秀山及部分五象片区'}
          </p>
          {active && activeArea && ready && (
            <span className="area-hint">{activeArea.name} · 范围示意</span>
          )}
        </div>
        <div className="view-badges">
          <span className="view-chip">
            <span className="live-dot" />
            {ready ? '三维场景' : '载入中'}
          </span>
          <button
            className="view-chip time-chip"
            onClick={() => {
              pauseMotion();
              setTab('scene');
              setPanelMode('menu');
              setCollapsed(false);
              setPanelExpanded(false);
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
                <h3>正在加载地图</h3>
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
            className="north-button desktop-tool"
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
          <div className="tool-group zoom-tools">
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
          <div className="tool-group desktop-tool">
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
          <div className="tool-group mobile-tools">
            <button onClick={reset} disabled={!ready} aria-label="返回全景">
              <Focus size={19} />
            </button>
            <button
              aria-label="更多地图工具"
              aria-haspopup="dialog"
              onClick={() => {
                setTour(false);
                setAutoRotate(false);
                setToolsOpen(true);
              }}
            >
              <Ellipsis size={20} />
            </button>
          </div>
        </div>
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
          <div className="touch-hint">单指旋转 · 双指缩放 / 平移</div>
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
          <button onClick={openInfo}>
            简化三维地图 <span className="status-divider">·</span> ©
            OpenStreetMap / Copernicus DEM
          </button>
        </footer>
        {showStats && metrics && (
          <output className="performance-stats" aria-label="场景性能统计">
            {metrics.profile === 'smooth' ? '流畅' : '精细'} ·{' '}
            {metrics.fps ? `${metrics.fps} fps` : '静止省电'} ·{' '}
            {(metrics.modelBytes / 1e6).toFixed(2)} MB ·{' '}
            {(metrics.loadMs / 1000).toFixed(2)} s<br />
            {metrics.triangles.toLocaleString()} 三角形 · {metrics.calls} 次绘制
            · {metrics.pixelRatio.toFixed(2)} 像素比例
          </output>
        )}
        {toast && (
          <output className="toast">
            <Check size={16} />
            {toast}
          </output>
        )}
      </section>
      <Sheet open={toolsOpen} onOpenChange={setToolsOpen}>
        <SheetContent
          side="bottom"
          className="tools-sheet"
          showCloseButton={false}
        >
          <SheetClose className="tools-close" aria-label="关闭地图工具">
            <X size={18} />
          </SheetClose>
          <SheetHeader>
            <SheetTitle>地图工具</SheetTitle>
            <SheetDescription>调整视角，或查看操作说明。</SheetDescription>
          </SheetHeader>
          <div className="tools-grid">
            <button
              disabled={!ready}
              onClick={() => {
                setToolsOpen(false);
                controller.current?.zoom(0.78);
              }}
            >
              <Plus size={20} />
              放大
            </button>
            <button
              disabled={!ready}
              onClick={() => {
                setToolsOpen(false);
                controller.current?.zoom(1.28);
              }}
            >
              <Minus size={20} />
              缩小
            </button>
            <button
              disabled={!ready}
              onClick={() => {
                setToolsOpen(false);
                reset();
              }}
            >
              <Focus size={20} />
              返回全景
            </button>
            <button
              disabled={!ready}
              onClick={() => {
                setToolsOpen(false);
                controller.current?.north();
              }}
            >
              <Navigation size={20} />
              朝向正北
            </button>
            <button
              disabled={!ready}
              onClick={() => {
                setToolsOpen(false);
                setTopDown((value) => !value);
              }}
            >
              <Grid2X2 size={20} />
              {topDown ? '倾斜鸟瞰' : '俯视地图'}
            </button>
            <button
              onClick={() => {
                setToolsOpen(false);
                void fullScreen();
              }}
            >
              <Expand size={20} />
              全屏查看
            </button>
            <button
              disabled={!ready || exporting}
              onClick={() => {
                setToolsOpen(false);
                void screenshot();
              }}
            >
              <ArrowDownToLine size={20} />
              导出视图
            </button>
            <button
              onClick={() => {
                setToolsOpen(false);
                openInfo();
              }}
            >
              <Info size={20} />
              操作与数据说明
            </button>
          </div>
        </SheetContent>
      </Sheet>
      <Sheet open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent className="info-sheet">
          <SheetHeader>
            <span className="eyebrow">ABOUT THIS ATLAS</span>
            <SheetTitle>关于这张地图</SheetTitle>
            <SheetDescription>邕城 · 南宁三维地图</SheetDescription>
          </SheetHeader>
          <div className="info-content">
            <p>
              这是一张可以旋转、缩放的南宁三维地图，覆盖石埠、相思湖、老城、青秀和部分五象片区。河道、道路和建筑轮廓来自
              OpenStreetMap，地形来自公开高程数据，主要地标用 Blender 建模。
            </p>
            <h3>怎么操作</h3>
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
                    搜索地标，或点击地图标记与地点列表，地图会定位到那里。城市漫游每
                    6.5 秒切换一站，手动拖动会暂停。
                  </p>
                </div>
              </li>
              <li>
                <Layers3 size={18} />
                <div>
                  <strong>图层与环境</strong>
                  <p>
                    显示或隐藏建筑、水面、树木、道路和标注，也可以调整光照、建筑与山地的高度、地图角度。
                  </p>
                </div>
              </li>
              <li>
                <Eye size={18} />
                <div>
                  <strong>键盘操作</strong>
                  <p>
                    先选中地图，再用方向键平移，+ / − 缩放，Home 返回全景。Tab
                    可以切换菜单和地标。
                  </p>
                </div>
              </li>
            </ul>
            <h3>范围与精度</h3>
            <p>
              范围：{region.bbox[0]}°–{region.bbox[2]}° E，{region.bbox[1]}°–
              {region.bbox[3]}° N，约 37 × 28 km，并未覆盖整个南宁市。
            </p>
            <p>
              为了看清高低差，山地起伏放大了 1.35 倍，建筑高度放大了 1.55
              倍，水面也做了平整处理。缺少高度数据的建筑采用估算值，程序补充的建筑位置为示意，地标外形做了简化。
            </p>
            <p>
              这张地图供浏览使用，不能用于测绘、导航或洪水分析。光照是模拟效果，不代表实时天气或准确的日照情况。
            </p>
            <h3>数据来源与源码</h3>
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
                href="https://registry.opendata.aws/copernicus-dem/"
                target="_blank"
                rel="noreferrer"
              >
                Copernicus DEM GLO-30
                <span>
                  高程 · 30 米源数据，60 米显示网格
                  <ArrowUpRight size={14} />
                </span>
              </a>
              <a
                href={assetUrl('/data/terrain-attribution.txt')}
                target="_blank"
                rel="noreferrer"
              >
                地形数据版权与许可
                <span>
                  Copernicus WorldDEM-30 · 来源声明
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
