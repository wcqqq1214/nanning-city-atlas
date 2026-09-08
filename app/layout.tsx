import type { Metadata, Viewport } from 'next';
import { assetUrl } from '@/lib/city/assets';
import './globals.css';

export const metadata: Metadata = {
  title: '邕城 · 南宁地理图景',
  icons: { icon: assetUrl('/favicon.svg') },
  description:
    '用 Three.js 与 Blender 探索南宁的邕江、青秀山、南湖与城市地标。真实公开地理数据构成的青绿城市沙盘。',
};
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
