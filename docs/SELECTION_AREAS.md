# 地标选中范围

校园、公园和湖泊地标选中时显示金色轮廓和半透明填色，界面标注“范围示意”。普通定位会容纳整个范围，近景保留原有建筑视角；切换到其他地标或全景会清除高亮。

目前覆盖广西大学、广西民族大学相思湖校区、相思湖公园及湖面、南宁动物园、明月湖及沿岸、南湖公园、人民公园、青秀山周边林地。

## 数据

`data/landmark-areas.json` 保存 OSM 快照时间、每处来源链接和简化后的经纬度多边形。使用既有 OSM 外轮廓，约 10 米简化，内部湖面和道路纳入整体示意。明月湖取湖面外包轮廓并外扩约 20 米；青秀山取周边林地轮廓，不代表完整景区边界。

来源：© OpenStreetMap contributors，ODbL 1.0。范围只用于浏览定位，不作为行政、用地或测绘边界。

已有 `work/geodata/osm.json` 快照时，可安装 Shapely 后重新生成：

```sh
python3 scripts/prepare_landmark_areas.py
```

此步骤不修改城市模型或地标清单。

## 渲染与验证

高亮首次选中时生成并缓存，填色和轮廓采样当前模型的地形、水面高度，随高度缩放一起变化；桌面和移动模型共用范围数据。模型销毁时一并释放高亮资源。

```sh
node --experimental-strip-types --test scripts/test-area-highlight.mjs
npm run typecheck
npm run lint
npm run build:pages
```

几何测试验证八个区域的有限坐标、网格规模、斜坡贴合、高度缩放、切换清除和缓存复用。浏览器检查校园、湖泊、山地、近景以及移动端的实际显示。
