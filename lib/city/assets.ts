/** Public assets share the app's prefix when hosted in a GitHub Pages subdirectory. */
export function assetUrl(path: `/${string}`): string {
  return `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}${path}`;
}
