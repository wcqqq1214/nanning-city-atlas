/** Content-derived revision supplied by Vite for the geographic data and models. */
declare const __CITY_ASSET_VERSION__: string;

/** Preserve Pages prefixes and avoid mixing new app code with an old city cache. */
export function assetUrl(path: `/${string}`): string {
  const revision =
    path.startsWith('/data/') || path.startsWith('/models/')
      ? `?v=${__CITY_ASSET_VERSION__}`
      : '';
  return `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}${path}${revision}`;
}
