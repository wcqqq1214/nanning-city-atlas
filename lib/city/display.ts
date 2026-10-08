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

const subscribeMotion = (onChange: () => void) => {
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
};
const motionSnapshot = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export const useReducedMotion = () =>
  useSyncExternalStore(subscribeMotion, motionSnapshot, serverSnapshot);
