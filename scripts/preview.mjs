import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../out/', import.meta.url));
const html = await readFile(path.join(root, 'index.html'), 'utf8').catch(() => {
  throw new Error('缺少 out/index.html，请先运行 npm run build:pages。');
});
// Read the prefix from the actual export, including root-path and fork builds.
const match = html.match(/(?:src|href)="([^"\s]*?)\/_next\/static\//);
if (!match) throw new Error('无法识别静态构建的资源路径，请重新构建。');
const basePath = match[1];
const port = Number(process.env.PORT ?? 4300);
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.glb': 'model/gltf-binary',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
};

http
  .createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const pathname = decodeURIComponent(url.pathname);
      if (basePath && (pathname === '/' || pathname === basePath)) {
        res.writeHead(302, { Location: `${basePath}/${url.search}` });
        res.end();
        return;
      }
      if (!pathname.startsWith(`${basePath}/`)) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const relative = pathname.slice(basePath.length);
      let file = path.resolve(root, `.${relative}`);
      if (file !== path.resolve(root) && !file.startsWith(root)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
      }
      if ((await stat(file)).isDirectory()) {
        if (!pathname.endsWith('/')) {
          res.writeHead(302, { Location: `${url.pathname}/${url.search}` });
          res.end();
          return;
        }
        file = path.join(file, 'index.html');
      }
      const data = await readFile(file);
      res.writeHead(200, {
        'Content-Type': types[path.extname(file)] ?? 'application/octet-stream',
        'Content-Length': data.byteLength,
        'Cache-Control': 'no-cache',
      });
      res.end(req.method === 'HEAD' ? undefined : data);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  })
  .listen(port, '127.0.0.1', () => {
    console.log(`Local: http://127.0.0.1:${port}${basePath}/`);
  });
