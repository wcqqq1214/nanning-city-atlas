# 剩余高架与短桥

覆盖当前城市 OSM 快照中清厢快速路、民族大道及精细跨江桥以外的 1,104 个桥梁路段、225 个连接节点和 164 处独立交叉。保留单行方向、原始节点与 `layer`，不把没有桥梁标签的街道架空。高度、桥宽及缺失层级的推断用于沙盘表达，不是工程测绘。

## 材质与结构

复用清厢快速路的路面、混凝土、梁底和标线材质，无新增图片纹理。两档均保留桥面、护栏和桥墩，流畅档减少标线。按空间合批，归属 `Bridges > ElevatedRoads`，随道路图层开关。

主干桥面约 13 m、次干 10 m、其他 8 m，普通匝道以 3.5 m 单车道表达。桥体厚度为 3.5 展示米。地形沿用现有夸张高度；纵坡一般限制在 18%，山地与桥头 150 m 范围最多放宽到 75%，避免地形或交叉约束将整段地面接坡抬成高墙。

## 穿模修复

旧模型分别生成路面和箱梁，平面裁剪后的路面不能代表完整桥体；并入口还会按不一致的路程插值高度。因此，只检查中心线净空会漏掉梁侧穿插、护栏侵入和桥头折面。

现在先生成完整三角柱桥体，再用 Manifold 离线合并相连桥面、箱梁和邻近地面接坡，删除内部相交面。保留不同高度的独立跨越层。新增几何数据只用于建模，不由网页下载。道路与接坡单独采用 22-bit Draco 位置精度，保留空间合批接缝的毫米级位置；其他模型沿用原精度。

竹溪立交接入民族大道的两处接口也参与同一实体合并：西侧连接路 OSM `959178351`、东侧匝道 `392546680`。`road_interfaces.py` 选择接口附近完整的民族大道桥面分段，沿用原生高度和宽度；合并结果保留所属道路材质并从外边界生成护栏。接入前 80 展示米内采用普通高架的 18% 纵坡上限，取消这两处固定主路接口误用的 75% 地面接坡放宽。两档分别使用各自的接口网格，民族大道同步采用 22-bit 位置精度。标线裁到合并后的可见路面，再检查接入匝道梁底，避免抬高的标线重新穿进桥体。竹溪灯杆安装在实际护栏顶面，选址同时避让梁体与护栏。

- 桥头采用满足地形、固定桥端和交叉约束的最低可行高度；地面过渡取消半平面截断，避免高度突跳。
- 桥面跨过的完整地形三角形参与高度约束，覆盖端点之间的山脊；既有精细桥端高度保持固定。
- 护栏从合并后的外边界生成，并入口和地面连接处留口。完整护栏三角面再次检查相邻路面，有冲突的短段省略。
- 桥墩同时避让道路、铁路、水面、建筑与精细地标，并按实际合并后的桥面高度重新检查净空。
- 标线裁到最终可见路面，再按所属三角面的平面计算高度；陡边保留退让空间，每个支撑面边缘另退让 1.5 cm，并省略无法稳定压缩的极窄碎片。
- 精细地标避让区域裁掉完整桥体。少量与桥梁冲突、没有实测高度的普通建筑体块按桥下空间降低；不足 4 展示米的残块省略。原始地理数据保留。

## 重建

已有 `data/road-solids-*.npz` 和配套 JSON 可直接运行 `npm run models:build`，无需联网、无需在 Blender 中安装 Manifold。输出包括可编辑的 `blender/nanning-city.blend` 和两档 GLB。

修改道路计划、地形或高度算法后，重新生成离线桥体：

```sh
work/venv/bin/pip install -r scripts/requirements.txt
blender --background --python-exit-code 1 --python blender/build_city.py -- --capture-road-inputs
work/venv/bin/python scripts/prepare_road_solids.py detail
work/venv/bin/python scripts/prepare_road_solids.py smooth
work/venv/bin/python scripts/finish_road_solids.py detail
work/venv/bin/python scripts/finish_road_solids.py smooth
work/venv/bin/python scripts/prepare_zhuxi_details.py
npm run models:build
work/venv/bin/python scripts/test_road_terrain.py
work/venv/bin/python scripts/test_road_interfaces.py
work/venv/bin/python scripts/validate_zhuxi.py
work/venv/bin/python scripts/validate_assets.py
npm run build:pages
```

首次改变高架覆盖范围时，先按 `scripts/prepare_elevated_roads.py --capture` 的输入要求保留未替换的两档 GLB 到 `work/elevated-roads/before.glb`、`before-mobile.glb`，更新高架计划后再执行上述流程。地面计划依赖变化时先运行 `scripts/prepare_ground_roads.py`。

`road-solids-*.json` 保存输入哈希、产物哈希、实际面数、高度及建筑调整记录。输入改变时构建会拒绝旧数据。捕获过程只写 `work/road-repair/`，不覆盖可编辑场景或公开模型。

## 验证边界

`validate_road_solids.py` 解码实际导出的 Draco 三角面，检查桥面之间、桥面与地面、桥面与梁底、护栏/梁侧/桥墩与路面、桥面与地面挡墙、结构与建筑的非共面相交。要求交线进入两个三角面的内部；忽略 5 cm 的边缘包络、平面两侧穿入不足 5 cm 或交线不足 10 cm 的情况。这样不会把共享边的毫米级偏移、以及三角面范围外的平面延伸误判成大幅穿插。桥头埋入地形的下部实体不算错误；可见路面与地形、标线与路面的完整重叠净空另由道路专项脚本检查。

回归报告写入 `work/road-repair/collision-{detail,smooth}.json`，包含模型哈希与冲突面坐标。重点视觉复查玉洞大道建筑交叠、长虹路并入口和青山大桥地面接坡。数值检查通过不代表所有城市地标之间的碰撞都已覆盖。

`validate_zhuxi.py` 另外检查竹溪范围内 `MinzuAvenue_*`、`ElevatedRoads_*` 和 `GroundRoads_*` 的路面、梁体、护栏与灯具。此项覆盖通用道路解码未纳入的民族大道接口；旧版仅检查竹溪灯具与路面，无法检测灯杆穿入护栏。

## 当前产物

本轮修复竹溪立交与民族大道两处接口，并同步整城最新地标产物：

| 项目 | 精细档 | 流畅档 |
| --- | ---: | ---: |
| GLB 字节数 | 20,308,760 | 15,101,496 |
| 整城三角面 | 2,795,140 | 2,061,744 |
| 剩余高架结构与标线三角面 | 444,866 | 403,678 |
| 地面道路、接坡与标线三角面 | 382,638 | 273,632 |
| 竹溪灯具 | 63 | 44 |

可编辑源文件为 `blender/nanning-city.blend`。本轮修复前文件保存在本地 `work/zhuxi-repair/before.blend`、`before.glb`、`before-mobile.glb`。最终产物哈希、验证结果和范围见 `work/zhuxi-repair/final-verification.json`。

两档实际导出模型的通用道路 8 类相交检查与竹溪专项 6 类相交检查均为 0（采用上文所述容差）。竹溪范围全部道路顶面与地形的连续重叠净空最小值均为 0.7863 展示米；全城高架桥面/地形最小净空为精细档 0.7491 m、流畅档 0.8392 m，高架标线/桥面为 0.1965 m、0.1976 m。

本轮通过 `test_road_terrain.py`、`test_road_interfaces.py`、`validate_road_interfaces.py`、`validate_zhuxi.py`、`validate_minzu.py`、`validate_elevated_roads.py`、`validate_road_solids.py`、`validate_malls.py` 和 `npm run build:pages`。实际建模预检包含原生桥台与接口附近完整地面接坡，随后再复核压缩后的最终 GLB。浏览器目视检查两档东西接口。全量 `validate_ground_roads.py` 曾因内存压力中止，本轮不记为通过；补充检查覆盖竹溪区域最终道路顶面与地形。

最终专项日志保存在 `work/zhuxi-repair/validate-*-final.log`，局部地形净空记录为 `terrain-final.log`，页面构建记录为 `build-pages-final.log`。旧修复记录仍保留在 `work/road-repair/`，不代表本轮重新运行的结果。
