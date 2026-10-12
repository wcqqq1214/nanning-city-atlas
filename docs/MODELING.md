# 模型重建与项目结构

## 文件职责与本地源场景

`blender/nanning-city.blend` 是本地可编辑源场景，不再纳入 Git，备份文件同样忽略。已有文件保留在原路径；新的克隆不包含它，也未提供独立下载包。网页运行使用版本化的 `public/models/` 和 `public/data/`，不依赖 `.blend`。

增量建模、截图和源场景校验可能需要本地 `.blend` 及对应的历史基准；缺失时先恢复可靠输入，不要把当前文件当成历史基准。完整生成脚本仍会写回本地 `.blend`。原始 OSM 缓存未分发，重新抓取不保证复现当前模型，详见 [数据分类与恢复限制](../data/README.md)。

2026-10-12 经授权重写 `dev` 历史，移除历史 Blender 场景、`docs/URBAN_STRUCTURE*.md`、`docs/urban-structure*/` 过程产物及已归档的旧打磨建议、菜单验收、清理清单和未引用场景图。当前正式文件树在过滤前后完全一致；原 Git 数据（含 reflog 与旧对象）和本地 `.blend` 已在仓库外备份并校验。

`main` 和旧任务分支未重写，仍可引用旧对象，因此 `dev` 历史大小不等于完整仓库或本地 `.git` 大小。旧提交号会变化，协作者应先保存未推送工作，再对齐新的 `origin/dev`，避免合并旧开发历史使过程产物重新进入分支。

城市可见性回归基准已固定在 `scripts/fixtures/legacy-city-visibility.py`，来源与提取规则见 [夹具说明](../scripts/fixtures/README.md)。测试不再运行 `git show` 读取固定旧提交；需要完整历史模型的检查仍须提供可靠基准。

## Blender 重建流程

使用 Blender 5.2.1；独立数据处理与 CI 使用 Python 3.12。铁路导出器按该 Blender 版本的 Draco 编码接口适配。

```bash
python3.12 -m venv work/venv
source work/venv/bin/activate
python -m pip install -r scripts/requirements.txt -c scripts/constraints-geodata.txt
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
- `work/full-city/`：全量建模中间导出，保留完整覆盖，供城区裁切重用。
- `public/models/nanning-city.glb`：长方形底座、城区精细模型和简化外围环境组成的 Draco 模型，大小以当前文件为准。
- `public/models/nanning-city-mobile.glb`：Draco 轻量模型，保留城区建筑、道路、水系及地标主体；大小以当前文件为准。
- `public/data/terrain.json`、`geography.json`：全量源覆盖的高程与地理数据库，保持校准计划的输入散列。
- `public/data/landmarks.json`、`overview.json`：网页加载的轻量元数据，后者使用城区展示范围。
- `public/data/urban-scope-models.json`：城区导出审计清单。

`models:build` 先保存全量场景与中间导出，再运行 `scripts/pack_city.py` 打包平面地形，最后调用 `models:scope` 验证并发布长方形城区模型。打包复用现有 `pack_flat_surfaces.py`，逐面验证顶点、三角面、材质和绕序不变；只将与面法线相差不超过 0.5° 的法线改为浏览器恢复，保留其他显式法线。原始导出留在 `work/full-city/raw-models/`，打包报告为 `work/full-city/data/packing.json`，可编辑 `.blend` 不受此步骤影响。只调整边界时可单独运行 `models:scope`；需要全量中间 GLB 和含几何依赖的 Python 环境，详见 [城区裁切](modeling/URBAN_SCOPE.md)。

铁路的源数据、站场衔接、桥隧和两档细节说明见 [城市铁路](modeling/RAILWAYS.md)。修改铁路计划后要重新准备林冠计划，确保铁路通道不被树木覆盖。

民族大道的道路替换、共享材质、两档细节与验证说明见 [民族大道](modeling/MINZU_AVENUE.md)。

主要跨江桥梁的来源、桥型、两档细节与重建流程见 [主要桥梁](modeling/BRIDGES.md)。

其余高架、立交匝道和短桥复用清厢快速路材质，包含箱梁、护栏、桥墩及地面接坡，详见 [剩余高架](modeling/ELEVATED_ROADS.md)。普通重建直接使用已保存的 `road-solids-*.npz`，无需联网。这些离线实体已统一处理并入口和接坡的相交面；修改道路、地形或高度算法后，需要按该文档重新捕获高度、合并实体，再运行 `models:build`。

坐标约定：准备阶段 X 向东、Y 向北，每单位 100 m；Blender Z 向上；glTF 导出后 Three.js X 向东、Y 向上、Z 向南。使用城区中心处的局部等距近似投影，输入坐标统一为 WGS84。

## 项目结构

```text
app/                        页面、响应式样式与检查视图
components/                 页面使用的界面组件与桥梁图标
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

## 正式模型与阶段记录

以下保留原首页的建模说明与 2026-09-13 阶段记录；不代表本轮重新验收，候选资源状态须通过正式资产核对。

香榭里住宅样板将 18 栋随机补楼替换为 13 栋按组团排列的板楼；地块边界来自 OSM，内部布局与层数为明确标注的估计。

畅游阁—邕江大桥北岸已加入约 641.59 m 连续护岸、步道和绿带，并校准邕江大桥与接桥道路的显示高度；岸线沿用现有 OSM 水域，断面尺寸明确标注为估计。

青秀山已加入约 4.152 km² 局部山体、76 条来源园路记录与 5 个独立推定湖面，并按公开尺寸校准龙象塔及周边植被比例。原始地理与高程数据保持不变。

广西文化艺术中心、镇宁炮台、地王大厦和南宁孔庙已完成比例与场地校准，包括台基落地、入口台阶和分级院落；尺寸依据公开来源，部分院落布局仍为估计。

### 2026-09-13 阶段状态

截至 **2026-09-13**，正式模型已完成固定视角基线、住宅街区、滨水、青秀山与代表性地标校准（P0–P4）。P5 正在推进建筑轮廓与院落、四类街区模板、水库岸线、场地接路及林冠衔接，候选模型尚未接入正式资源；资源预算与整城视觉、交互和性能验收仍待完成。

可以查看相思湖、三街两巷、南湖、青秀山、国际会展中心、会展航洋城、万象城、南宁大桥、广西文化艺术中心、两座铁路车站与清厢快速路高架等。已细化 14 座主要跨江桥梁，包含青山、五象、英华、良庆、永和等桥的塔索与拱肋结构，见 [主要桥梁](modeling/BRIDGES.md)。会展航洋城与万象城的外观细节、来源和重建方式见 [商业地标](modeling/MALLS.md)。龙象塔与广西民族博物馆、广西博物馆的外观细节及重建方式见 [文化地标](modeling/CULTURAL_LANDMARKS.md)。完整名单见 [地标目录](../data/landmarks.json)。清厢快速路已覆盖从清川大道至厢竹大道、凤岭北路的全线，按当前地图中心线约 14.25 km，包含 31 个主线连接点和 332 个桥墩，范围和近似说明见 [高架建模](modeling/VIADUCT.md)。
