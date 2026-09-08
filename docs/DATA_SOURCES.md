# 数据来源与处理

## 输入

| 数据 | 来源 | 本项目使用方式 |
| --- | --- | --- |
| 河湖、道路、绿地、建设用地、建筑 | [OpenStreetMap](https://www.openstreetmap.org/copyright)，通过 [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) 取得 | 取 WGS84 范围内要素，拼接多边形关系，保留内环，裁剪并简化 |
| 高程 | [Mapzen / AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) | z12 Terrarium 瓦片，`R × 256 + G + B / 256 − 32768` 解码为米 |
| 地理背景 | [广西自然资源厅：南宁市土地利用总体规划](https://dnr.gxzf.gov.cn/zfxxgk/fdzdgknr/ghjh/ghjh/t16008000.shtml) | 核对邕江河谷、水系与青秀山、南湖等生态空间的组织关系 |
| 青秀山背景 | [青秀山景区介绍](https://www.qxsfjq.com/Introduction.html?bindStyle=list&columnId=2&type=2) | 核对邕江畔山林与龙象塔的景区特征；不把文字资料当作测量数据 |

访问日期：2026-09-08。OSM 实际快照时间保存在 `geography.json` 和 `overview.json` 的 `osmTimestamp`。

## 空间处理

1. 输入范围：经度 108.265–108.465，纬度 22.735–22.875。
2. 以范围中心为局部原点，采用 `x = (lon − lon₀) × 1113.2 × cos(lat₀)`、`y = (lat − lat₀) × 1113.2`；每单位约 100 m。
3. OSM 多段外环与内环通过 polygonize 组合；用 Shapely 修复与裁剪，并在 0.1 m 精度网格上统一拓扑，避免 JSON 舍入产生无效内环。水面通过 Earcut 保留凹边界和孔洞。
4. 道路按类型设置示意宽度，并按显示地形采样高度。桥梁抬升，隧道不在地表绘制。
5. OSM 建筑优先使用 `height`，其次使用 `building:levels × 3.2 m`；缺省采用 5 层，即 16 m。高度限制为 3–450 m。
6. 程序化建筑使用固定随机种子，只布置在建设用地剩余区域，排除水面、绿地、道路和 OSM 建筑缓冲区。其个体位置、高度和外形均不是实测结果。
7. 树木在绿地和滨水缓冲区示意分布，不代表真实树种和树位。
8. 原始高程保留为 `heights`；显示高程另存为 `sceneHeights`，水下采样设为 53 m，岸上显示地形最低取 62 m，水面统一绘制于显示高度。该处理仅用于可视化，不构成水文模型。
9. 初始地形高差比例为 3，初始建筑高度比例为 1.55。菜单中的竖向比例会进一步作用于整个模型。
10. 自建地标范围内不重复绘制常规建筑中心和树位，避免简化模型穿插。地理数据库保留原始要素；这是渲染替换，不代表原建筑被删除。4,700 个候选树位最终显示 4,670 个。

## 地标位置与造型

`data/landmarks.json` 是地标顺序、文字和镜头配置的唯一源目录；Blender 生成 `public/data/landmarks.json` 时补上场景坐标，前端按同一目录展示。

新增点位使用 OSM 的 WGS84 坐标：面要素取包围盒中心，孔庙使用场所节点，东站使用站区关系中心。因此它们是浏览用的代表点，不是建筑测量控制点。每条新增记录保留对应的 `sourceUrl`。

| 新增探索点 | 坐标来源 |
| --- | --- |
| 广西大学 · 汇学堂 | [OSM way 822812173](https://www.openstreetmap.org/way/822812173) |
| 人民公园 · 镇宁炮台 | [OSM way 991635905](https://www.openstreetmap.org/way/991635905) |
| 广西博物馆 | [OSM way 476559327](https://www.openstreetmap.org/way/476559327) |
| 南宁东站 | [OSM relation 11576286](https://www.openstreetmap.org/relation/11576286) |
| 广西民族博物馆 | [OSM way 1006681820](https://www.openstreetmap.org/way/1006681820) |
| 南宁孔庙 | [OSM node 9292176827](https://www.openstreetmap.org/node/9292176827) |
| 广西文化艺术中心 | [OSM way 819620330](https://www.openstreetmap.org/way/819620330) |
| 亭子码头 | [OSM way 1423783186](https://www.openstreetmap.org/way/1423783186) |

造型按公开建筑特征自行简化：艺术中心的山体与云棚参考 [gmp 项目介绍](https://www.gmp.de/en/projects/3231/guangxi-culture-arts-center)，汇学堂的坡屋顶与柱廊参考 [广西大学校园介绍](https://tmjz.gxu.edu.cn/info/1452/5053.htm)，镇宁炮台的环形堡垒参考 [南宁市融媒体中心报道](https://silkroadonthecloud.cn/f/view-A1002001002-2054792774516322304.html)。模型不包含测量尺寸、实景贴图或原建筑设计图，比例为沙盘展示做了调整。

## 范围限制

范围不包括完整南宁市、左/右江汇流点、完整五象新区或外围全部山系。局部坐标投影是城区展示近似，不可替代正规的测绘坐标系统。地标来自公开建筑位置与简化造型，不使用航拍贴图。

## 数据再分发

裁剪和处理后的 OSM 数据库随仓库公开提供于 `public/data/geography.json`，继续遵循 ODbL 1.0。下载脚本与缓存规则公开，允许重新取得原始要素。源码中的代码许可不替代数据许可。

Terrain Tiles 的完整上游说明见 [Tilezen attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)。本区域的全球陆地高程来源标注为：SRTM terrain data courtesy of the U.S. Geological Survey。Mapzen 数据汇编还可能使用其他全球源，完整来源清单以该上游说明为准。处理后数据未获 Mapzen 或 USGS 认证。
