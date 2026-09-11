# 民族大道模型

民族大道按简洁的双向六车道主路展示，每个方向三车道。保留 67 段主路，省略 44 段辅路及非机动车道的独立道路表达；所有 111 段旧道路仍列入替换清单，避免旧条带重新出现。

## 参考与简化

- [广西新闻网 2016 年整治报道](https://v.gxnews.com.cn/a/15296652?pageno=2&remains=1)记载竹溪立交以西双向六车道、以东双向八车道，并有辅道和路口渠化。模型依照本次展示要求统一简化为六车道，不代表全线实际车道数。
- [南宁晚报 2024 年实拍](https://v.gxnews.com.cn/a/21635450)提供民族大道南湖大桥段的照片参考。跨湖主路表现为笔直、平顺的道路。
- `data/minzu-source.json` 保留原始 OSM 标签；`data/minzu-plan.json` 分别保存原始线位、简化线位、主路和省略的辅路。中心线在 2.5 米容差内拉直，保留真实的大方向变化与两端连接。
- 每方向以 10 米路幅示意，用两条虚线划分三个机动车道。移除额外绿化分车条带和路口转向箭头，保留机动车标线、路缘及稀疏路灯。
- 南湖约 650 米跨湖及接坡范围共用一个水平高程，按两档实际显示地形所需净空确定。取消该范围原有统一桥面最低高度造成的隆起；两方向共同约束，不再各自沿湖岸起伏。
- 其他路段仍贴合既有地形，保留桥梁与下穿隧道标记。两段下穿隧道在地表留空。

上述宽度、高程与平直程度属于沙盘表达，原始地理数据保持独立，不作为测绘或工程参数。

## 材质与两档模型

模型位于 `Roads > MinzuAvenue`，随道路桥梁图层开关。复用清厢快速路的沥青、标线、混凝土、梁底与金属材质，不新增贴图。两档共用道路主体；流畅档减少标线密度并省略路灯。网格继续使用 18 位 Draco 位置量化。

## 重建

```sh
work/venv/bin/python scripts/prepare_minzu.py
# 先从真实构建逻辑输出新主路高程，供连接道路重算。
# 此模式允许旧连接道路计划尚未刷新，不保存或覆盖完整模型。
blender --background --python-exit-code 1 --python blender/build_city.py -- --minzu-context
work/venv/bin/python scripts/prepare_ground_roads.py --capture --minzu-context work/minzu-avenue/road-context.json
npm run models:build
```

主路预计算写入本地 `work/minzu-avenue/road-context.json`，地面道路准备脚本检查其输入哈希，替换旧模型里的民族大道边界和高程，其余地标仍从已有 GLB 捕获。完整构建仍严格校验全部计划输入。

正常构建复用版本化计划即可，不需要本地快照。可编辑场景保存为 `blender/nanning-city.blend`。

## 验证

```sh
work/venv/bin/python scripts/test_minzu_profile.py
work/venv/bin/python scripts/validate_minzu.py
work/venv/bin/python scripts/validate_assets.py
npm run build:pages
```

回归测试用两岸不等高的地形验证南湖路面保持水平。导出验证直接解码两档 GLB，检查六车道主路、辅路省略、南湖路面高差、标线、材质复用、建筑避让及原始数据完整性。

本次修改前的完整模型备份在本地 `work/minzu-simplify/`，地面道路实现见 [地面道路](GROUND_ROADS.md)。

本次两档解码检查的南湖路面高差均为 0.0077 米（生成时为零，差值来自量化），每档 132 个辅路排除检查点通过。精细档民族大道为 11,576 个主体三角面、19,056 个细节三角面；流畅档主体相同、细节为 6,848 个三角面。

同一南湖范围的修改前 GLB 路面高差为 21.1512 展示米，修改后为 0.0077 展示米；这组比较直接针对原有桥头隆起，不是实际地理高程测量。

本次回归测试、民族大道专项验证、整城 `validate_assets.py` 和发布构建均通过。浏览器检查覆盖南湖全段、侧视、六车道俯视、老城、东段及两档模型，地图页面定位与加载正常，未见控制台错误。
