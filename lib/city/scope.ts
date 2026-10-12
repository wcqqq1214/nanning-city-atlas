import type { Overview } from './types';

/** Local east/north coordinates; the render scene uses east/up/south. */
export function overviewCenter(overview: Overview | null): [number, number] {
  const bounds = overview?.bounds ?? [-103, -78, 103, 78];
  return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
}

export function constrainToScope(
  x: number,
  y: number,
  overview: Overview,
): [number, number] {
  return [
    Math.max(overview.bounds[0], Math.min(overview.bounds[2], x)),
    Math.max(overview.bounds[1], Math.min(overview.bounds[3], y)),
  ];
}
