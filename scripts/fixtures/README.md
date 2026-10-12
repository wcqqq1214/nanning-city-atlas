# 城市可见性历史基准

`legacy-city-visibility.py` 供 `test_city_visibility.py` 比较重构前后的排除规则，不参与网页或 Blender 正式构建。

- 原始提交（历史重写前）：`73edbb75e671e5ee1e9b7567ecb40652fe86290c`。
- 原始文件：`blender/build_city.py`。
- 原始文件 SHA-256：`9f7df8266e619cdb44151d594c1b35da7ac40940d55620c32123d871dfd0ae7e`。
- 提取 `inside_landmark` 函数，以及主建筑循环中首次 `z = ...` 赋值之前的排除条件；按原测试的转换，将 `continue` 改为 `return False`，末尾添加 `return True`，封装为 `old_visible(b, building_index)`。
- 提取后 AST 与原测试执行的两段 AST 完全一致。测试继续提供原有运行环境和 P4 额外边界处理，不执行 Blender 场景构建。

原始提交号用于记录来源，不再作为运行测试的前置条件。历史重写前的源码保存在仓库外备份及未重写的主分支历史中。不要用当前实现覆盖这份比较基准。
