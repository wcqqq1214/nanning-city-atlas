import data from '@/data/landmark-areas.json';

export type LandmarkArea = {
  name: string;
  sourceUrls: string[];
  polygons: number[][][][];
};

export function landmarkArea(id: string | null): LandmarkArea | undefined {
  return id ? (data.areas as Record<string, LandmarkArea>)[id] : undefined;
}
