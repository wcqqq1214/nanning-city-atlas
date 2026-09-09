# 模型重建与项目结构

## Blender 重建流程

需要 Blender 4.5+（本项目使用 Blender 5.2.1）与 Python 3.9+。

```bash
python3 -m venv work/venv
source work/venv/bin/activate
pip install -r scripts/requirements.txt
python3 scripts/fetch_geodata.py
python3 scripts/prepare_geodata.py
python3 scripts/prepare_stations.py
python3 scripts/prepare_viaduct.py
python3 scripts/prepare_forest_canopy.py --stage all
npm run models:build
```

`data/region.json` 统一定义范围。`fetch_geodata.py` 按范围检查 OSM 缓存，范围变化后自动重新获取；高程瓦片按编号复用。重新获取 OSM 时请在 `work/geodata/` 中有针对性地删除对应缓存，勿在调试时高频请求公共 Overpass 服务。

数据与模型检查：

```bash
python3 scripts/validate_assets.py
```

输出：

- `blender/nanning-city.blend`：可编辑场景，包含具名地形、建筑、树木、水面、桥梁、地标、相机与灯光。
- `public/models/nanning-city.glb`：8.65 MB 的 Draco 精细模型。
- `public/models/nanning-city-mobile.glb`：6.11 MB 的 Draco 轻量模型，保留完整建筑、道路、水系及地标主体。
- `public/data/terrain.json`、`geography.json`：高程与裁剪后的地理数据库。
- `public/data/landmarks.json`、`overview.json`：网页加载的轻量元数据。

坐标约定：准备阶段 X 向东、Y 向北，每单位 100 m；Blender Z 向上；glTF 导出后 Three.js X 向东、Y 向上、Z 向南。使用城区中心处的局部等距近似投影，输入坐标统一为 WGS84。

## 项目结构

```text
app/                 中文地图界面与响应式样式
data/region.json      范围配置
data/landmarks.json   地标目录、来源与镜头配置
lib/city/scene.ts     Three.js 渲染、光照、镜头、标记与资源清理
lib/city/webmcp.ts    可选 WebMCP 地标与环境工具
blender/             可编辑 .blend、场景生成与地标造型脚本
scripts/             数据下载、裁剪、补充建筑与模型检查
public/data/         可再利用的地理数据与地图元数据
public/models/       压缩 GLB
public/draco/        随项目提供的 Draco 解码器，无第三方运行时请求
docs/               设计、数据与验证说明
```
