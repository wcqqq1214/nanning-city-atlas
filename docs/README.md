# 文档导航

长期维护的说明与精选插图纳入 Git；运行报告、候选模型和过程截图放在本地 `work/`。专题中的历史数据与验证结果只代表文中对应阶段，不能代替当前资产验收。

## 项目说明

- [数据来源与精度](DATA_SOURCES.md)
- [界面与交互设计](DESIGN.md)
- [模型重建、项目结构与维护约定](MODELING.md)
- [检查命令与验证边界](VALIDATION.md)
- [建模输入分类与恢复限制](../data/README.md)
- [第三方许可与署名](../licenses/THIRD_PARTY.md)

## 界面专题

- [手机体验](design/MOBILE.md)
- [地标选中范围](design/SELECTION_AREAS.md)

## 建模专题

| 分类 | 说明 |
| --- | --- |
| 道路与桥梁 | [主要桥梁](modeling/BRIDGES.md)、[地面道路](modeling/GROUND_ROADS.md)、[高架与短桥](modeling/ELEVATED_ROADS.md)、[清厢快速路](modeling/VIADUCT.md)、[民族大道](modeling/MINZU_AVENUE.md)、[竹溪立交](modeling/ZHUXI_INTERCHANGE.md) |
| 铁路与车站 | [城市铁路](modeling/RAILWAYS.md)、[南宁站与南宁东站](modeling/STATIONS.md) |
| 地形与植被 | [地形重采样](modeling/TERRAIN_RESAMPLING.md)、[城市树木与郊区树林](modeling/FOREST_CANOPY.md) |
| 地标与滨水 | [艺术中心](modeling/ARTS_REMODEL.md)、[会展中心](modeling/EXPO_REMODEL.md)、[体育中心](modeling/SPORTS_CENTER.md)、[文化地标](modeling/CULTURAL_LANDMARKS.md)、[商业地标](modeling/MALLS.md)、[镇宁炮台](modeling/ZHENNING_MODEL.md)、[畅游阁与南湖](modeling/LAKE_OLDTOWN_REMODEL.md)、[亭子码头与南宁大桥](modeling/WATERFRONT_REMODEL.md) |

## 图片与本地记录

- `screenshots/readme/`：项目首页使用的图片。
- `screenshots/modeling/`：专题说明仍在引用的建模图片；历史对比图保留其阶段含义。
- `work/renders/`：新生成的渲染图，经检查并选用后再复制到上述文档目录。
- `work/archive/docs/`：本轮迁出的旧验收记录、打磨建议、菜单改版验收、Blender 清理清单和未引用的场景图，仅本地保留。

原有被忽略的 `docs/URBAN_STRUCTURE*.md` 与 `docs/urban-structure*/` 暂留原位，以免破坏历史候选的路径引用；新的过程材料统一进入 `work/`。本地记录不属于新克隆仓库的依赖，必要的可复用输入应放入 `data/` 或明确的测试夹具目录。
