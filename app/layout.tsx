import type { Metadata, Viewport } from 'next';
import { assetUrl } from '@/lib/city/assets';
import './globals.css';

export const metadata: Metadata = {
  title: '邕城 · 南宁三维地图',
  icons: { icon: assetUrl('/favicon.svg') },
  description:
    '在浏览器里查看南宁三维地图，游览邕江、南湖、青秀山和城市地标，支持旋转、缩放与光照切换。',
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
