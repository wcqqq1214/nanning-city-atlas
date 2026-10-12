# 模型重建与项目结构

## 文件职责与本地源场景

`blender/nanning-city.blend` 是本地可编辑源场景，不再纳入 Git，备份文件同样忽略。已有文件保留在原路径；新的克隆不包含它，也未提供独立下载包。网页运行使用版本化的 `public/models/` 和 `public/data/`，不依赖 `.blend`。

增量建模、截图和源场景校验可能需要本地 `.blend` 及对应的历史基准；缺失时先恢复可靠输入，不要把当前文件当成历史基准。完整生成脚本仍会写回本地 `.blend`。原始 OSM 缓存未分发，重新抓取不保证复现当前模型，详见 [数据分类与恢复限制](../data/README.md)。

本轮只让源场景退出后续版本跟踪，没有重写 Git 历史；旧提交仍可能包含 `.blend`。

## Blender 重建流程

使用 Blender 5.2.1 与 Python 3.9+。铁路导出器按该 Blender 版本的 Draco 编码接口适配。

```bash
python3 -m venv work/venv
source work/venv/bin/activate
pip install -r scripts/requirements.txt
python3 scripts/fetch_geodata.py
python3 scripts/prepare_geodata.py
python3 scripts/prepare_stations.py
python3 scripts/prepare_viaduct.py
python3 scripts/prepare_minzu.py
python3 scripts/prepare_bridges.py
python3 scripts/fetch_railways.py
python3 scripts/prepare_railways.py
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
- `public/models/nanning-city.glb`：Draco 精细模型，大小以当前文件为准。
- `public/models/nanning-city-mobile.glb`：Draco 轻量模型，保留完整建筑、道路、水系及地标主体；大小以当前文件为准。
- `public/data/terrain.json`、`geography.json`：高程与裁剪后的地理数据库。
- `public/data/landmarks.json`、`overview.json`：网页加载的轻量元数据。

铁路的源数据、站场衔接、桥隧和两档细节说明见 [城市铁路](modeling/RAILWAYS.md)。修改铁路计划后要重新准备林冠计划，确保铁路通道不被树木覆盖。

民族大道的道路替换、共享材质、两档细节与验证说明见 [民族大道](modeling/MINZU_AVENUE.md)。

主要跨江桥梁的来源、桥型、两档细节与重建流程见 [主要桥梁](modeling/BRIDGES.md)。

其余高架、立交匝道和短桥复用清厢快速路材质，包含箱梁、护栏、桥墩及地面接坡，详见 [剩余高架](modeling/ELEVATED_ROADS.md)。普通重建直接使用已保存的 `road-solids-*.npz`，无需联网。这些离线实体已统一处理并入口和接坡的相交面；修改道路、地形或高度算法后，需要按该文档重新捕获高度、合并实体，再运行 `models:build`。

坐标约定：准备阶段 X 向东、Y 向北，每单位 100 m；Blender Z 向上；glTF 导出后 Three.js X 向东、Y 向上、Z 向南。使用城区中心处的局部等距近似投影，输入坐标统一为 WGS84。

## 项目结构

```text
app/                        页面、响应式样式与检查视图
components/                 界面组件
hooks/                      React hooks
lib/city/                   Three.js 场景与交互逻辑
blender/                    场景生成、地标建模与校验；.blend 仅在本地
scripts/                    数据处理、构建、测试与预览工具
data/                       范围、来源、建模参数及必要的离线输入
public/data/                网页数据与高程署名
public/models/              正式 GLB
public/draco/               本地解码器与随站点分发的许可
licenses/                   第三方许可与署名说明
docs/modeling/              道路、地形与地标专题
docs/design/                手机体验与交互专题
docs/screenshots/readme/    README 选用图片
docs/screenshots/modeling/  专题选用图片
work/                       本地缓存、候选、渲染、报告与归档
out/、dist/                 忽略的构建产物
```

全图普通地面道路采用分级材质和两档地形贴合网格，详见 [地面道路](modeling/GROUND_ROADS.md)。修改地面道路计划时先运行 `work/venv/bin/python scripts/prepare_ground_roads.py`，随后重新生成上述高架与接坡实体。

## 工具入口与输出约定

- `npm test`：运行 `scripts/test-*.mjs` 中全部 JavaScript 测试；CI 使用同一入口。
- `npm run test:data`：使用当前环境的 `python3` 运行 `scripts/test_*.py`；先激活装好依赖的虚拟环境。
- `npm run preview`：预览已有 `out/`，自动识别构建子路径，默认端口 4300。
- `scripts/prepare_*.py`、`fetch_*.py`：准备或抓取数据，可能覆盖建模输入或正式数据；按专题流程执行。
- `scripts/check_*.py`、`audit_*.py` 与 `blender/check_*.py`：模型和数据检查；按各脚本要求提供候选或基准输入。
- `blender/render_malls.py` 与 `render_cultural.py`：分别输出到 `work/renders/malls/` 和 `work/renders/cultural/`，选图后再人工更新文档图片。

脚本与 Blender 模块本轮保留原层级，以维持 Python 同目录导入和根目录定位。新的临时输出统一放在 `work/`；正式数据、GLB、解码器及其署名继续版本化，不按“生成文件”一概忽略。`.env.example` 与 `.env.*.example` 可以提交，但只能包含示例值。

长期文档可直接加入 `docs/` 的对应分类，不设少数文件白名单。完整索引见 [文档导航](README.md)，检查边界见 [检查与验证](VALIDATION.md)。
