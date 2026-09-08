# 邕城 · Nanning City Atlas

以真实公开地理数据为骨架，用 **Three.js + Blender** 复现广西南宁中心城区的山、水与城市空间。青绿色邕江贯穿浅色城市体块，保留南湖、青秀山、路网、滨江绿地与主要地标的地理关系。

项目范围约 **20.5 × 15.6 km**：`108.265°–108.465° E / 22.735°–22.875° N`。这是中心城区的艺术化地理重建，不是全市行政区域的精密数字孪生。

![Blender 场景概览](docs/scene-overview.png)

*Blender 离线场景渲染；网页另含交互菜单与地图标注。*

## 本地运行

需要 Node.js 22.13+，已提交预生成模型，浏览项目无需安装 Blender，也无需地图 API key。

```bash
npm ci
npm run dev
```

打开终端打印的本地地址，默认是 `http://localhost:3000`。

```bash
npm run typecheck
npm run lint
npm run build
npm start
```

生产构建使用 Vinext / Vite，服务端适配 Cloudflare Workers。GitHub 中保留完整项目、锁文件、地图数据、Blender 源文件与生成脚本。

## 可以做什么

| 菜单 | 行为 |
| --- | --- |
| 探索 | 全景鸟瞰；飞往三街两巷/畅游阁、南湖、地王大厦、国际会展中心、华润大厦、青秀山/龙象塔、南宁大桥 |
| 图层 | 独立开关建筑、树木、道路桥梁、水面、地名标注 |
| 环境 | 06:00–22:00 模拟光照、晨光/日间/日落/夜色预设、0.5–2.0 倍整体竖向调整 |
| 视角 | 俯视/倾斜视角、缓慢环绕、正北朝向、放大缩小、全景复位、全屏 |
| 城市漫游 | 每 6.5 秒切换一站；手动操作地图或选择地标会暂停 |
| 导出视图 | 导出当前 WebGL 城市画面为 PNG（不含页面菜单与 HTML 标注） |
| 项目说明 | 操作指南、范围、精度说明、来源及许可 |

鼠标左键旋转、右键平移、滚轮缩放；触屏单指旋转、双指平移/缩放。聚焦地图后可用方向键平移、`+` / `−` 缩放、`Home` 复位。菜单与地标支持键盘访问；系统减少动态效果偏好会关闭环绕和水面动画。

## 视觉风格

**青绿城市沙盘**：纸瓷白建筑、青玉色水面、深浅绿色低面数山林，黄铜色屋顶与朱红色桥拱作为局部识别色。镜头采用可旋转的倾斜鸟瞰，底座以切片方式呈现地形，界面保持清晰、安静的地图工作台结构。

详细设计与功能说明见 [设计说明](docs/DESIGN.md)。

## 数据与精度

- 4,295 个 OSM 建筑轮廓；缺少建筑高度时采用估算值。
- 2,402 栋程序化补充建筑，只在公开地图的建设用地区域内生成，并避让水面、公园、道路和已有建筑。
- 6,665 个道路片段与 4,700 棵示意树木。
- 225 × 173 的显示高程网格，来自 12 张 z12 Mapzen Terrarium 瓦片；源瓦片采样尺度约 35 m，最终显示网格约 90 m。
- 地形初始高差放大 3 倍，建筑高度初始放大 1.55 倍。环境面板的高度滑杆在此基础上缩放整个场景的竖向比例。
- 水面被统一到显示高度，水下地形与低位岸线做了可视化处理。模拟光照不对应实时天气或严格天文日照。
- 地标轮廓由 Blender 简化建模；部分地标相对于真实尺寸适当放大，便于沙盘辨识。

不能用于测绘、导航、洪水模拟或建筑尺寸量测。完整数据说明与归属见 [数据来源](docs/DATA_SOURCES.md) 和 [ATTRIBUTION.md](ATTRIBUTION.md)。

## Blender 重建流程

需要 Blender 4.5+（本项目使用 Blender 5.2.1）与 Python 3.9+。

```bash
python3 -m venv work/venv
source work/venv/bin/activate
pip install -r scripts/requirements.txt
python3 scripts/fetch_geodata.py
python3 scripts/prepare_geodata.py
npm run models:build
```

`fetch_geodata.py` 会缓存原始下载；只要缓存未清除就复用同一份原始数据。重新获取 OSM 时请在 `work/geodata/` 中有针对性地删除对应缓存，勿在调试时高频请求公共 Overpass 服务。

数据与模型检查：

```bash
python3 scripts/validate_assets.py
```

输出：

- `blender/nanning-city.blend`：可编辑场景，包含具名地形、建筑、树木、水面、桥梁、地标、相机与灯光。
- `public/models/nanning-city.glb`：使用 Draco 压缩的网页模型。
- `public/data/terrain.json`、`geography.json`：高程与裁剪后的地理数据库。
- `public/data/landmarks.json`、`overview.json`：网页加载的轻量元数据。

坐标约定：准备阶段 X 向东、Y 向北，每单位 100 m；Blender Z 向上；glTF 导出后 Three.js X 向东、Y 向上、Z 向南。使用城区中心处的局部等距近似投影，输入坐标为 WGS84，不混用 GCJ-02 / BD-09。

## 项目结构

```text
app/                 中文地图界面与响应式样式
lib/city/scene.ts     Three.js 渲染、光照、镜头、标记与资源清理
lib/city/webmcp.ts    可选 WebMCP 地标与环境工具
blender/             可编辑 .blend 与生成脚本
scripts/             数据下载、裁剪、补充建筑与模型检查
public/data/         可再利用的地理数据与地图元数据
public/models/       压缩 GLB
public/draco/        随项目提供的 Draco 解码器，无第三方运行时请求
docs/               设计、数据与验证说明
```

网页运行时只向自己的站点请求数据和模型。地图数据来源服务只在离线重建时使用。

## 许可

代码采用 [MIT](LICENSE)。地图数据库为 © OpenStreetMap contributors，遵循 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。高程数据与衍生模型保留上游归属要求；代码许可不覆盖第三方地理数据。Draco 解码器采用 Apache 2.0，见 `public/draco/LICENSE.txt`。
