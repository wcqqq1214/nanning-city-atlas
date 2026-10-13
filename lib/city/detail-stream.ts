import { nearbyChunks, ResourceQueue, type StreamAsset } from './streaming.ts';

export type DetailAsset = StreamAsset & {
  id: string;
  geometryBytes: number;
  layer: 'roads' | 'buildings';
  layers?: ('roads' | 'railways')[];
};
export type StreamManifest = {
  version: 1;
  profiles: Record<
    'detail' | 'smooth',
    {
      sourceSha256: string;
      sourceBytes: number;
      base: DetailAsset;
      details: DetailAsset[];
    }
  >;
};
export type DetailView = {
  x: number;
  y: number;
  radius: number;
  selected: string | null;
  budget: number;
  layers: { roads: boolean; railways: boolean; buildings: boolean };
};

/** Reserve decoded memory before starting downloads; never overbook by chunk count. */
export function selectDetails(
  assets: DetailAsset[],
  view: DetailView,
  costs: ReadonlyMap<string, number>,
) {
  const candidates = nearbyChunks(assets, view.x, view.y, view.radius).map(
    ({ asset }) => asset as DetailAsset,
  );
  const foreground = assets.find((a) => a.id === `landmark-${view.selected}`);
  if (foreground) candidates.unshift(foreground);
  const selected = new Map<string, DetailAsset>();
  let bytes = 0;
  for (const asset of candidates) {
    if (
      selected.has(asset.id) ||
      !(asset.layers ?? [asset.layer]).some((l) => view.layers[l])
    )
      continue;
    // Include per-chunk lighting buffers and small bookkeeping allocations.
    const cost =
      costs.get(asset.id) ?? Math.ceil(asset.geometryBytes * 1.2) + 65536;
    if (bytes + cost > view.budget) continue;
    selected.set(asset.id, asset);
    bytes += cost;
  }
  return selected;
}

/** Owns only additive details. Failures and cancellation leave the base usable. */
export class DetailStream<T> {
  private queue = new ResourceQueue<T>(2);
  private loaded = new Map<string, T>();
  private costs = new Map<string, number>();
  private failed = new Set<string>();
  private wanted = new Map<string, DetailAsset>();
  private view: DetailView | null = null;
  private disposed = false;
  private assets: DetailAsset[];
  private hooks: {
    load: (asset: DetailAsset, signal: AbortSignal) => Promise<T>;
    attach: (value: T) => number;
    release: (value: T, attached: boolean) => void;
    status: (message: string, retry: boolean) => void;
  };
  constructor(assets: DetailAsset[], hooks: DetailStream<T>['hooks']) {
    this.assets = assets;
    this.hooks = hooks;
  }
  update(view: DetailView) {
    if (this.disposed) return;
    this.view = view;
    this.wanted = selectDetails(this.assets, view, this.costs);
    for (const key of this.queue.tasks.keys())
      if (!this.wanted.has(key)) this.queue.cancel(key);
    for (const [key, value] of this.loaded)
      if (!this.wanted.has(key)) {
        this.hooks.release(value, true);
        this.loaded.delete(key);
      }
    for (const key of this.failed)
      if (!this.wanted.has(key)) this.failed.delete(key);
    let priority = 0;
    for (const [key, asset] of this.wanted) {
      const rank = priority++;
      const pending = this.queue.tasks.get(key);
      if (pending) pending.priority = rank;
      if (this.loaded.has(key) || pending || this.failed.has(key)) continue;
      void this.queue
        .enqueue(key, rank, (signal) => this.hooks.load(asset, signal))
        .then((value) => {
          if (this.disposed || !this.wanted.has(key)) {
            this.hooks.release(value, false);
            return;
          }
          this.costs.set(key, this.hooks.attach(value));
          this.loaded.set(key, value);
          // Reconcile actual allocation, including newly created night lights.
          if (this.view) this.update(this.view);
        })
        .catch((error: unknown) => {
          if (
            !this.disposed &&
            !(error instanceof Error && error.name === 'AbortError')
          )
            this.failed.add(key);
        })
        .finally(() => {
          if (!this.disposed) this.report();
        });
    }
    this.report();
  }
  retry() {
    this.failed.clear();
    if (this.view) this.update(this.view);
  }
  get geometryBytes() {
    return [...this.loaded.keys()].reduce(
      (sum, key) => sum + (this.costs.get(key) ?? 0),
      0,
    );
  }
  get loadedCount() {
    return this.loaded.size;
  }
  private report() {
    const failed = [...this.failed].some((key) => this.wanted.has(key));
    const loading = [...this.wanted.keys()].some(
      (key) => !this.loaded.has(key) && !this.failed.has(key),
    );
    this.hooks.status(
      failed
        ? '部分近景暂未加载，城市仍可浏览'
        : loading
          ? '正在补充附近细节'
          : '',
      failed,
    );
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.queue.dispose();
    for (const value of this.loaded.values()) this.hooks.release(value, true);
    this.loaded.clear();
  }
}
