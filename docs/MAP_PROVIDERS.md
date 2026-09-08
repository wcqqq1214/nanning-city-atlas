# 地图数据方案：开放数据与高德

评估日期：2026-09-08。当前项目使用 OSM 地理要素、Mapzen Terrarium 高程和自建 Blender 模型，尚未接入高德。

## 项目选择

建议保留当前可下载、可编辑的城市沙盘，并把高德作为未来可选的在线地图模式。这个建议基于接口用途与分发条件，不代表已经对南宁两种数据源的覆盖率、定位精度或更新速度做过实测。

| 需求 | 更适合的方向 | 原因 |
| --- | --- | --- |
| 国内在线地图、地点检索、路线规划 | 高德 JS API | 可直接使用官方地图和服务插件，不必在本项目重建检索与导航服务 |
| 把 Blender 地标放到在线地图中 | 高德自定义 WebGL 图层 | 官方提供 `GLCustomLayer` 结合 Three.js 的示例，可同步地图相机并叠加自有模型 |
| 下载完整城市数据、离线建模、公开发布 `.blend` / GLB | 当前开放数据流程 | 已保留数据许可和生成脚本；高德 SDK 的展示能力不等于获得其底层数据的再分发授权 |
| 更准确的建筑外形、高度和丘陵 | 取得适当授权的建筑与高程数据 | 切换地图 SDK 本身不会把示意建筑变成实测模型，需要单独评估数据覆盖、精度和授权 |

高德的地点检索和路线能力见官方 [搜索地点](https://lbs.amap.com/api/javascript-api-v2/tutorails/search-poi) 与 [路线规划](https://lbs.amap.com/api/javascript-api-v2/guide/services/navigation)。Three.js 叠加方式见 [GLCustomLayer 官方示例](https://developer.amap.com/demo/javascript-api-v2/example/selflayer/glcustom-layer)。

## 接入时的边界

高德[服务协议](https://lbs.amap.com/pages/terms/)第 4.12 条和第 7.3 条对未经许可的数据提取、下载、缓存和再分发等行为设有限制。普通 API 使用权限不能直接视为把地图底层数据导出到 Blender 或提交进公开 GitHub 仓库的授权；如要分发此类数据或模型，应先确认对应产品的授权范围。

当前源数据为 WGS84，而高德使用高德坐标系。叠加前需要统一坐标，高德提供 [`AMap.convertFrom`](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom)；不能直接把当前 WGS84 经纬度当成高德坐标使用。模型的局部坐标还需匹配地图的投影、原点和比例。

后续在线模式应独立加载高德 SDK，把自建地标作为自有数据叠加，并保留官方地图标识。不要通过批量抓取底图几何来填充本仓库的开放数据包。
