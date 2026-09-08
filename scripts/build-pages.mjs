import { access, cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const repository =
  process.env.GITHUB_REPOSITORY?.split('/').at(-1) ?? 'nanning-city-atlas';
const basePath = (
  process.env.PAGES_BASE_PATH ??
  (repository.endsWith('.github.io') ? '' : `/${repository}`)
).replace(/\/$/, '');

if (
  !/^(\/[A-Za-z0-9._-]+)*$/.test(basePath) ||
  basePath.split('/').some((part) => part === '.' || part === '..')
) {
  throw new Error(
    'PAGES_BASE_PATH must be empty or a path such as /nanning-city-atlas.',
  );
}

const result = spawnSync(
  process.execPath,
  [path.join(root, 'node_modules/vinext/dist/cli.js'), 'build'],
  {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      GITHUB_PAGES: 'true',
      NEXT_PUBLIC_BASE_PATH: basePath,
    },
  },
);
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const client = path.join(root, 'dist/client');
const output = path.join(root, 'out');
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(client, output, { recursive: true });

// Vinext prefixes exported routes on disk. Pages already mounts the artifact at
// that prefix, so move route files to its root while keeping public assets there.
if (basePath) {
  await cp(path.join(client, basePath.slice(1)), output, { recursive: true });
  await rm(path.join(output, basePath.slice(1)), {
    recursive: true,
    force: true,
  });
}

const html = await readFile(path.join(output, 'index.html'), 'utf8');
if (!html.includes('南宁') || !html.includes(`${basePath}/_next/static/`)) {
  throw new Error(
    'Static export is missing the page or correctly prefixed JavaScript assets.',
  );
}
for (const [, url] of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
  if (!url.startsWith('/') || url.startsWith('//')) continue;
  if (!url.startsWith(`${basePath}/`))
    throw new Error(`Unprefixed asset: ${url}`);
  await access(path.join(output, url.slice(basePath.length + 1).split('?')[0]));
}
for (const asset of [
  'models/nanning-city.glb',
  'models/nanning-city-mobile.glb',
  'data/landmarks.json',
  'data/overview.json',
  'draco/draco_wasm_wrapper.js',
  'draco/draco_decoder.wasm',
]) {
  await access(path.join(output, asset));
}
await rm(path.join(output, '.vite'), { recursive: true, force: true });
await writeFile(path.join(output, '.nojekyll'), '');
console.log(`GitHub Pages artifact: ${output} (base path: ${basePath || '/'})`);
