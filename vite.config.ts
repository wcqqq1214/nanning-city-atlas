import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig } from 'vite';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === 'seatbelt';

export default defineConfig(() => {
  // Keep the geographic catalog and both models on the same cache revision.
  // Pages caches stable public URLs even when a newer app bundle is loaded.
  const cityHash = createHash('sha256');
  for (const file of [
    './public/data/landmarks.json',
    './public/data/overview.json',
    './public/data/city-streaming.json',
    './public/models/nanning-city.glb',
    './public/models/nanning-city-mobile.glb',
  ]) {
    cityHash.update(readFileSync(new URL(file, import.meta.url)));
  }
  return {
    plugins: [vinext()],
    define: {
      __CITY_ASSET_VERSION__: JSON.stringify(
        cityHash.digest('hex').slice(0, 16),
      ),
    },
    css: { postcss: { plugins: [tailwindcss()] } },
    server: {
      host: '127.0.0.1',
      watch: isCodexSeatbeltSandbox
        ? { useFsEvents: false, usePolling: true }
        : undefined,
    },
  };
});
