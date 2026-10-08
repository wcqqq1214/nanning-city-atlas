import type { Landmark } from './types';

const ALIASES: Record<string, string[]> = {
  gxu: ['西大', '广西大学', '汇学堂'],
  gxmzu: ['民大', '广西民族大学'],
  'east-station': ['东站', '高铁站'],
  'nanning-station': ['火车站', '南宁火车站'],
  expo: ['会展', '会展中心'],
  'arts-center': ['艺术中心', '大剧院'],
  'sports-center': ['体育中心', '体育场'],
  'gx-museum': ['广西壮族自治区博物馆', '区博'],
  changyou: ['三街两巷', '畅游阁', '老城'],
  qingxiu: ['青秀山', '龙象塔'],
};

export function searchLandmarks<T extends Pick<Landmark, 'id' | 'name'>>(
  places: T[],
  query: string,
): T[] {
  const term = query.trim().toLocaleLowerCase();
  return places.filter((place) =>
    [place.name, ...(ALIASES[place.id] ?? [])].some((name) =>
      name.toLocaleLowerCase().includes(term),
    ),
  );
}
