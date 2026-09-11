import type { Landmark } from './types';

export const LANDMARK_CATEGORIES = [
  { id: 'bridges', name: '大桥', shortName: '大桥' },
  { id: 'nature', name: '山水公园', shortName: '山水' },
  { id: 'culture', name: '文化古迹', shortName: '人文' },
  { id: 'architecture', name: '城市建筑', shortName: '建筑' },
  { id: 'campus', name: '校园', shortName: '校园' },
  { id: 'transport', name: '交通地标', shortName: '交通' },
] as const;

export type LandmarkCategory = (typeof LANDMARK_CATEGORIES)[number]['id'];

// Presentation groups reuse the catalogue's descriptions without changing model inputs.
export function landmarkCategory(
  place: Pick<Landmark, 'id' | 'category'>,
): LandmarkCategory {
  if (
    place.category === '邕江桥梁' ||
    place.id === 'bridge' ||
    place.id.endsWith('-bridge')
  )
    return 'bridges';
  if (place.category.includes('校园')) return 'campus';
  if (place.category.includes('交通') || place.category === '城市高架')
    return 'transport';
  if (['文化场馆', '历史建筑', '老城'].includes(place.category))
    return 'culture';
  if (/田园|湖泊|林地|山林|滨江/.test(place.category)) return 'nature';
  return 'architecture';
}
