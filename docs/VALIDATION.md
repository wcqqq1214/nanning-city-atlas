# 检查与验证

本页维护可重复执行的检查入口，不记录某次运行已经通过。原阶段验收记录已在本地移至 `work/archive/docs/VALIDATION.md`；Git 历史未清理，可从目录整理前的提交追溯。

## 网页代码与构建

在仓库根目录使用 Node.js 24：

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build:pages
npm run preview
```

`npm test` 运行全部 `scripts/test-*.mjs`，覆盖资源版本、选中高亮、平面法线、检查视图与点触交互。GitHub Pages CI 使用同一个入口。静态构建会检查首页、资源路径与必要的模型和解码器；它不等同于浏览器实际加载、交互和性能验收。

预览默认地址为 `http://127.0.0.1:4300/nanning-city-atlas/`；根路径构建与 Fork 的项目路径以终端实际输出为准。检查视图在同一项目路径下的 `inspect/`。

## Python 数据测试

首次设置环境：

```sh
python3 -m venv work/venv
source work/venv/bin/activate
pip install -r scripts/requirements.txt
npm run test:data
```

后续运行先激活该环境即可。入口为 `python3 -m unittest discover -s scripts -p 'test_*.py'`，包含各专题的数学、几何及数据规则测试；个别检查可能依赖已有数据或本地基准，跳过项不能解释为验收通过。Python 数据测试不自动加入当前仅安装 Node.js 的 Pages CI。

## 模型与浏览器检查

- 模型综合检查：`python3 scripts/validate_assets.py`；需要对应 Python 依赖和正式资产。
- 源模型检查、局部模型验收和导出比较：按 [建模专题](README.md#建模专题) 执行，需要 `.blend` 的检查须先具备本地源文件。
- 浏览器脚本：`scripts/check-*.mjs`，阅读脚本中的运行地址和浏览器依赖要求后执行，不混入普通单元测试。
- 人工检查：地图加载、地标定位、漫游、图层、光照、画质切换、截图和 `inspect/` 页面。
- 手机性能与弱网：参见 [手机体验](design/MOBILE.md)，桌面模拟不替代真机测量。

报告与截图写入 `work/`，文档只保留选用的插图。部分历史脚本仍引用被忽略的旧实验目录；缺失输入时应说明限制，不能把当前资产冒充历史候选或基准。
