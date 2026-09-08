import { useSyncExternalStore } from 'react';

export const COMPACT_LAYOUT =
  '(max-width: 767px), (max-width: 1000px) and (max-height: 520px)';

const subscribe = (onChange: () => void) => {
  const media = window.matchMedia(COMPACT_LAYOUT);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
};
const snapshot = () => window.matchMedia(COMPACT_LAYOUT).matches;
const serverSnapshot = () => false;

export const useCompactLayout = () =>
  useSyncExternalStore(subscribe, snapshot, serverSnapshot);
