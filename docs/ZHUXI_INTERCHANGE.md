# 竹溪立交细化

会展中心西北侧为竹溪立交，连接民族大道与竹溪大道／厢竹大道。[会展中心交通说明](https://www.nicec.cn/html/gz/jtlx/)用于确认位置；[竹溪立交航拍](https://pikbest.com/video/4k-aerial-photography-of-urban-traffic-flow-at-zhuxi-interchange-in-nanning-city%2C-guangxi_10078811.html)用于观察回旋匝道、桥面与环内绿化；[2016 年道路施工报道](https://m.cnr.cn/news/df/20160510/t20160510_522105895.html)提供各方向匝道名称。图片仅作观察参考，未复制进网站资源。

## 表达范围

- 按保存的 OSM ID 识别 19 段道路，保留原始中心线、单行方向、端点与 layer。
- 7 段南北主桥按单向三车道绘制；其中缺少 lanes 标签的短段沿用连接主路的车道数。
- 11 段主要匝道以 6.5 m 宽的双车道表现；另一个短连接保留单车道。匝道宽度及缺失车道信息依据航拍做沙盘概化，不是逐段实测数据。
- 顺行箭头沿 OSM 方向，按真实可见桥面裁切并投影；分合流附近留空，避免标线越界。
- 沿道路边缘布置简化路灯；低矮乔灌木只填在现有匝道围合的安全区域内，避开道路、水面与建筑。树木位置与灯具为景观表达，不对应实测设施清单。
- 路灯归属道路图层，绿化归属植被图层；两种画质均保留，流畅档减少灯具密度与树冠面数。

## 重建与检查

宽度或车道规则位于 `blender/zhuxi_interchange.py`。修改规则后先运行 `scripts/prepare_elevated_roads.py`，然后按 [高架重建流程](ELEVATED_ROADS.md) 重新捕获道路高度并生成两档实体。

生成完两档 `road-solids-*.npz` 后、整城构建之前，运行：

```sh
work/venv/bin/python scripts/prepare_zhuxi_details.py
npm run models:build
work/venv/bin/python scripts/validate_zhuxi.py
```

专项检查读取两档实际导出的 Draco 网格，验证路灯、树冠与路面不相交、模型分组遵循图层开关，并检查 19 段道路的车道数及宽度。整城的桥面层级、桥墩、护栏、建筑碰撞仍由既有道路验证脚本覆盖。

## 本轮结果

最终两档均保留 105 株低矮乔灌木；精细档 62 盏路灯，流畅档 42 盏。绿化加密后，除 `Vegetation_zhuxi` 外，精细档 247 个、流畅档 244 个网格的 Draco 数据与已完成道路检查的版本逐项一致，因此沿用该版本的整城道路碰撞结果。加密后的植被、灯具另通过 `validate_zhuxi.py`，两档与局部路面相交均为 0；浏览器近景检查了匝道和车道标线。
