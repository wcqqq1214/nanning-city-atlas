# 建模输入与数据恢复

本目录保存模型制作所需的配置、来源和离线输入；`public/data/` 保存网页数据及部分建模源输入。城区裁切保留完整地理源数据，展示边界由 `urban-core-boundary-source.json` 单独控制。

| 文件或目录 | 用途与管理方式 |
| --- | --- |
| `region.json`、`landmarks.json`、`landmark-areas.json` | 范围、地标和选中区域配置，随代码管理。 |
| `urban-core-boundary-source.json`、`urban-core-boundary.geojson` | 已确认的城区精细范围、原地形及江岸衔接区、1.8 km 山林渐退范围和长方形外框。线外采用低模淡色环境；导出限制在现有数据覆盖内，并避让完整建筑；见 [范围说明](../docs/modeling/URBAN_SCOPE.md)。 |
| `*-source.json`、`*-sources/`、`block-sources/` | 来源摘录、轮廓和人工校准参数；具体精度边界见对应专题。 |
| `*-plan.json`、`*-plan.json.gz` | 数据准备生成的建模计划，包含现有模型所需输入，继续跟踪。不能仅按文件名判断可删除。 |
| `road-solids-*.npz` 及同名 JSON | 道路合并实体及元数据，是普通离线建模的输入；重算依赖高度捕获和道路处理流程，继续跟踪。 |
| `road-building-levels.json` | 道路原生捕获生成的建筑底面和屋顶高度；与道路实体共同保存和校验，普通建模不依赖 `work/` 中的临时高度文件。 |
| `terrain-source.json` | 当前高程来源、处理参数与来源文件信息。 |
| `../public/data/` | 浏览器数据和署名文件，随正式 GLB 成套提交。 |
| `../work/geodata/` | 原始 OSM、范围缓存及高程下载文件，只在本地保存。 |

## 可复现性边界

网页开发、静态构建和预览使用仓库内的 `public/` 资产，无需下载地理数据或安装 Blender。

完整数据准备中的 `scripts/prepare_geodata.py` 读取 `work/geodata/osm.json`；该原始快照没有随仓库分发。缺少缓存时，`data:fetch` 会请求网络，取得的数据可能与当前正式资产使用的历史版本不同，因此“重新下载”不能视为恢复同一版本。`fetch_geodata.py` 也会写入公共高程数据，不能把它当成无副作用的环境检查。

现有计划文件与正式模型继续保留。需要完全恢复旧底图时，先取得对应原始缓存及范围元数据，并核对来源日期、范围和散列；不要用最新 OSM 数据冒充旧快照。后续可选择将核验后的压缩快照纳入 `data/snapshots/`，或提供带散列的独立下载包。本轮未新增快照、下载入口或自动恢复命令。

离线道路实体的重建入口见 [高架与短桥](../docs/modeling/ELEVATED_ROADS.md)，高程处理见 [地形重采样](../docs/modeling/TERRAIN_RESAMPLING.md)，完整流程见 [建模说明](../docs/MODELING.md)。
