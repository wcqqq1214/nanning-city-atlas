# 剩余高架与短桥

覆盖当前城市 OSM 快照中清厢快速路、民族大道及精细跨江桥以外的 1,104 个桥梁路段、225 个连接节点和 164 处独立交叉。保留单行方向、原始节点与 `layer`，不把没有桥梁标签的街道架空。高度、桥宽及缺失层级的推断用于沙盘表达，不是工程测绘。

## 材质与结构

复用清厢快速路的路面、混凝土、梁底和标线材质，无新增图片纹理。两档均保留桥面、护栏和桥墩，流畅档减少标线。按空间合批，归属 `Bridges > ElevatedRoads`，随道路图层开关。

主干桥面约 13 m、次干 10 m、其他 8 m，普通匝道以 3.5 m 单车道表达。桥体厚度为 3.5 展示米。地形沿用现有夸张高度；纵坡一般限制在 18%，山地与桥头 150 m 范围最多放宽到 75%，避免地形或交叉约束将整段地面接坡抬成高墙。

## 穿模修复

旧模型分别生成路面和箱梁，平面裁剪后的路面不能代表完整桥体；并入口还会按不一致的路程插值高度。因此，只检查中心线净空会漏掉梁侧穿插、护栏侵入和桥头折面。

现在先生成完整三角柱桥体，再用 Manifold 离线合并相连桥面、箱梁和邻近地面接坡，删除内部相交面。保留不同高度的独立跨越层。新增几何数据只用于建模，不由网页下载。道路与接坡单独采用 22-bit Draco 位置精度，保留空间合批接缝的毫米级位置；其他模型沿用原精度。

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
work/venv/bin/python scripts/validate_assets.py
npm run build:pages
```

首次改变高架覆盖范围时，先按 `scripts/prepare_elevated_roads.py --capture` 的输入要求保留未替换的两档 GLB 到 `work/elevated-roads/before.glb`、`before-mobile.glb`，更新高架计划后再执行上述流程。地面计划依赖变化时先运行 `scripts/prepare_ground_roads.py`。

`road-solids-*.json` 保存输入哈希、产物哈希、实际面数、高度及建筑调整记录。输入改变时构建会拒绝旧数据。捕获过程只写 `work/road-repair/`，不覆盖可编辑场景或公开模型。

## 验证边界

`validate_road_solids.py` 解码实际导出的 Draco 三角面，检查桥面之间、桥面与地面、桥面与梁底、护栏/梁侧/桥墩与路面、桥面与地面挡墙、结构与建筑的非共面相交。要求交线进入两个三角面的内部；忽略 5 cm 的边缘包络、平面两侧穿入不足 5 cm 或交线不足 10 cm 的情况。这样不会把共享边的毫米级偏移、以及三角面范围外的平面延伸误判成大幅穿插。桥头埋入地形的下部实体不算错误；可见路面与地形、标线与路面的完整重叠净空另由道路专项脚本检查。

回归报告写入 `work/road-repair/collision-{detail,smooth}.json`，包含模型哈希与冲突面坐标。重点视觉复查玉洞大道建筑交叠、长虹路并入口和青山大桥地面接坡。数值检查通过不代表所有城市地标之间的碰撞都已覆盖。

## 当前产物

本次整合后的整城产物包含同步完成的竹溪立交车道、灯具与第一版绿化：

| 项目 | 精细档 | 流畅档 |
| --- | ---: | ---: |
| GLB 字节数 | 20,002,208 | 14,863,628 |
| 整城三角面 | 2,764,182 | 2,032,606 |
| 剩余高架结构与标线三角面 | 444,889 | 403,700 |
| 地面道路、接坡与标线三角面 | 382,680 | 273,640 |

可编辑源文件为 `blender/nanning-city.blend`。原始修复前文件保存在本地 `work/road-repair/before.blend`、`before.glb`、`before-mobile.glb`。本轮最终模型与每个 Draco primitive 的哈希记录在 `work/road-repair/final-primitives.json`，便于后续仅调整植被时确认道路几何完全没有变化。

两档实际导出模型的 8 类道路相交检查均为 0。桥面/地形最小净空为精细档 0.7491 m、流畅档 0.8392 m；高架标线/桥面为 0.1965 m、0.1976 m。地面道路覆盖、避让与标线净空检查通过，生产页面中的两档模型哈希与源产物一致，浏览器已实际加载两档模型。

验证记录：通用模型、铁路、民族大道、跨江桥梁及全部道路检查在 `work/road-repair/validation-final.log` 中通过；该长进程末尾仍使用已导入的旧竹溪树数下限而失败。修正测试后，最新竹溪专项独立复跑通过，见 `zhuxi-validation.log`；没有将旧全量进程记为成功。汇总及产物哈希见 `work/road-repair/final-verification.json`。
