# 地形重采样

2026-09-11 将 Mapzen z12 Terrarium 替换为 Copernicus GLO-30 2021 版 DSM。源数据约 30 m（1 arc-second），显示网格约 60 m，617 × 465 个点；流畅版通常每两格取样。原始高程范围从旧数据的 −169–385 m 改为 53.83–387.34 m。源 COG 缓存在 `work/geodata`，下载地址、SHA-256、采样与显示参数写入 `data/terrain-source.json`。

`heights` 保留对原始 DSM 的双线性采样。`sceneHeights` 单独进行抗混叠、平滑，以及建设用地内的低分位滤波；林地原始轮廓受保护，不应用城区去突起滤波。DSM 本身包含房屋和植被，这些显示处理不能替代裸地测量。地形高差放大从 3 倍改为 1.35 倍，建筑保持 1.55 倍。

航洋与万象城按地块周边低分位高度设置平整场地。地块外 175 m 覆盖精细版与流畅版网格角点，再用 125 m 平滑过渡衔接周边地面，避免旧模型按最高地面点托起整块基座。显示水下高程统一为 61.3 m，陆地最低 68.3 m；这只是展示水位。

同一城区位置、同一 60 m 采样网格的比较：相邻点显示高差第 95 百分位由 0.24315 降到 0.05998 场景单位，下降约 75.3%。比较包含新旧各自的高差倍率，不代表源 DSM 测量精度提升 75%。

## 重建顺序

使用装好 `scripts/requirements.txt` 的 Python 环境（本项目为 `work/venv/bin/python`），Blender 5.2.1。不能只替换 DEM 后直接导出旧道路网格：高架净空、桥头、铁路和林冠都依赖地形。

先保存 `data/ground-roads-context.json` 到 `work/terrain-resample/old-ground-context.json`，以保留不随高程变化的地标水平轮廓。以下命令按顺序运行：

```sh
mkdir -p work/terrain-resample
cp data/ground-roads-context.json work/terrain-resample/old-ground-context.json
work/venv/bin/python scripts/resample_terrain.py
work/venv/bin/python scripts/prepare_nanhu_landmark.py
work/venv/bin/python scripts/prepare_railways.py
work/venv/bin/python scripts/prepare_viaduct.py
work/venv/bin/python scripts/prepare_minzu.py
work/venv/bin/python scripts/prepare_forest_canopy.py --stage all
blender -b --python-exit-code 1 --python blender/build_city.py -- --terrain-context
work/venv/bin/python scripts/prepare_ground_roads.py --capture --context-model work/terrain-resample/context/detail.glb --obstacles-context work/terrain-resample/old-ground-context.json
blender -b --python-exit-code 1 --python blender/build_city.py -- --terrain-context --context-ground
work/venv/bin/python scripts/prepare_elevated_roads.py --context-directory work/terrain-resample/context
blender -b --python-exit-code 1 --python blender/build_city.py -- --capture-road-inputs
work/venv/bin/python scripts/prepare_road_solids.py detail
work/venv/bin/python scripts/finish_road_solids.py detail
work/venv/bin/python scripts/prepare_road_solids.py smooth
work/venv/bin/python scripts/finish_road_solids.py smooth
work/venv/bin/python scripts/prepare_zhuxi_details.py
blender -b --python-exit-code 1 --python blender/build_city.py -- --check-road-interfaces
work/venv/bin/python scripts/validate_road_interfaces.py
npm run models:build
work/venv/bin/python scripts/validate_terrain.py
```

两次中间上下文导出只写入 `work/terrain-resample/context`，地形及道路支承面均重新生成，不从旧 GLB 复制高度。地标水平轮廓快照仅适用于未改动地标平面范围的地形更新。完整数据更新的 `data:fetch` / `data:prepare` 也使用新源与相同显示处理，避免下次准备数据退回旧地形。

版权和许可见 [数据来源](DATA_SOURCES.md) 与站点提供的 `public/data/terrain-attribution.txt`。

## 导出结果

精细版 25,236,380 字节、3,462,527 个三角面；流畅版 17,270,232 字节、2,350,419 个三角面。网格变细同时增加了贴地道路的切分数量，因此更新了对应文件与三角面预算，流畅版仍保留更粗地形和植被减量。两个商场的最终 GLB 裁切测量均为占地内零高差，地板比地面高约 0.025 场景单位；旧基座低侧的大段挡土墙已消除。

竹溪立交的实体合并涵盖整个立交范围内的民族大道车行道及地面引道，地面段保留真实显示支承底面。只按桥头节点和 `bridge` 标签选取少数桥面，会在地形改变后漏掉引道与匝道的侧墙交叉。覆盖校验同时计入实际导出的民族大道沥青面，避免把由合并路面承接的区域误报为空洞。

## 已执行的验证

- 原始高程抽样与源 COG 对比、输入哈希、水面一致性、两档最终地形下的商场场地及基座间隙校验通过。
- 资产主检查中的城市覆盖、森林贴地、铁路、跨江桥梁及地标检查通过。修复竹溪接缝后，165 / 163 个不受道路调整影响的节点，其 Draco 几何与已验证版本逐字节一致。
- 最终 GLB 的地面道路、民族大道、高架、道路实体交叉及竹溪立交分项检查全部通过；导出前的原生侧墙、桥台、路灯检查也通过。
- 镇宁炮台在最终 `.blend` 中通过门洞、庭院、连桥和局部地形接缝检查。
- TypeScript、oxlint、GitHub Pages 构建通过，输出包中的模型、高程、地标目录与声明文件均与最终公开资产一致。
- 浏览器检查航洋、万象城近景、青秀山起伏和精细 / 流畅画质切换，未检出控制台错误。
