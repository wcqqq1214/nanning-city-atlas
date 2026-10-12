# 检查与验证

本页维护可重复执行的检查入口，不记录某次运行已经通过。原阶段验收记录在本地 `work/archive/docs/VALIDATION.md`；`dev` 的过程产物历史已清理，旧记录需查阅本地归档或仓库外历史备份。

## 网页代码与静态构建

在仓库根目录使用 Node.js 24：

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build:pages
npm run preview
```

`npm test` 运行 `scripts/test-*.mjs`，覆盖资源版本、选中高亮、平面法线、检查视图与点触交互。静态构建检查首页、资源路径、模型和解码器，但不能替代浏览器交互与性能验收。

默认预览地址为 `http://127.0.0.1:4300/nanning-city-atlas/`，检查页为同一路径下的 `inspect/`。用 `PORT=4301 npm run preview` 更换端口；根路径构建使用 `PAGES_BASE_PATH='' npm run build:pages`，预览命令不变。Fork 的默认路径按仓库名生成，以终端输出为准。

## 可复现的数据测试

使用 Python 3.12，并安装与 CI 相同的几何依赖约束：

```sh
python3.12 -m venv work/venv
source work/venv/bin/activate
python -m pip install -r scripts/requirements.txt -c scripts/constraints-geodata.txt
npm run test:data
```

`test:data` 发现 `scripts/test_*.py`，只使用仓库文件和测试创建的临时输入；不需要历史 `work/`、原始 OSM 下载或 `.blend`。保留的测试覆盖当前正式数据、几何规则、导出处理和固定夹具。约束版本来自已验证的模型处理环境，升级时应重新验证几何结果。

## 历史基准与候选比较

原有历史断言保留在 `scripts/baseline_test_*.py`，通过独立入口运行：

```sh
npm run test:data:baseline -- --input-root /absolute/path/to/preserved-work
```

`--input-root` 指向原 `work/` 内容所在目录。必须显式提供；缺少输入时检查失败，不使用当前模型替代，也不按成功跳过。需要的输入如下：

| 检查 | 输入根目录内的文件 |
| --- | --- |
| 住宅街区试点 | `urban-structure/baseline-73edbb7/public/data/geography.json` |
| 街区推广 | `urban-structure/p5/quality-candidate.json`、`urban-structure/p5/rollout/candidate.json` |
| 场地整平 | `urban-structure/p5/grading/candidate.json` |
| 滨水原始数组 | `urban-structure/baseline-p1/public/data/{geography,terrain}.json` |
| 青秀山原始数组与高程 | `urban-structure/baseline-p2/public/data/{geography,terrain}.json`、`geodata/` 下由 `data/qingxiu-terrain-plan.json` 指定的原始栅格 |
| 山地林冠范围外对比 | `urban-structure/p3/p2-forest-plan.json` |

这些历史检查与默认测试互补，不进入无本地基准的 CI。离线快照恢复尚未提供，见 [建模输入与恢复限制](../data/README.md)。

## 浏览器检查

以下命令从仓库根目录运行。先静态构建并启动预览，再安装独立的浏览器检查环境：

```sh
npm install --prefix work/browser --no-audit --no-fund playwright
work/browser/node_modules/.bin/playwright install chromium
export PLAYWRIGHT_MODULE_PATH="$PWD/work/browser/node_modules/playwright"
node scripts/check-inspection.mjs
node scripts/check-landmark-interaction.mjs
node scripts/check-qingxiu-interaction.mjs
```

共用配置由 `scripts/browser-check-helpers.mjs` 管理：

| 环境变量 | 默认值或作用 |
| --- | --- |
| `CITY_BASE_URL` | `http://127.0.0.1:4300/nanning-city-atlas`；保留项目子路径，末尾斜线可省略 |
| `PLAYWRIGHT_MODULE_PATH` | `playwright`；可指定独立安装的绝对模块路径 |
| `BROWSER_EXECUTABLE` | 不设置时使用 Playwright Chromium；可指定系统 Chrome 的可执行文件 |
| `CITY_CHECK_OUTPUT` | `work/checks/<脚本名称>/`；所有脚本统一使用该变量 |
| `PYTHON_EXECUTABLE` | `python3`；青秀山像素检查需要已安装上述 Python 依赖的解释器 |

脚本保留各自的画质、图层、镜头与渲染断言，共用页面异常、控制台错误和 HTTP 错误收集。失败写入输出目录的 `failure.json` 并退出非零；浏览器在成功和失败时都会关闭。重复执行会覆盖同名记录，需要保留一次运行时请指定独立输出目录。

`check-inspection.mjs` 默认检查全部预设；可用 `CITY_CHECK_VIEW=residential` 缩小范围。`CITY_CHECK_BASELINE_PATH` 可显式提供包含 `public/` 的历史资源目录；该模式只检查历史资源的检查视图，不代替当前首页验收。

历史运动比较与候选水体检查需要额外输入：

```sh
CITY_BASELINE_PATH=/absolute/path/to/before-assets node scripts/check-city-motion.mjs
CITY_WATER_MODELS=/absolute/path/to/candidate/models.json node scripts/check-reservoir-water.mjs
```

运动比较的基准目录须包含两档 GLB、`overview.json` 和 `landmarks.json`，均位于 `public/` 内；可用 `CITY_CANDIDATE_PATH` 指定另一候选，否则与当前仓库正式资产比较。原 `CITY_MOTION_OUTPUT` 改用统一的 `CITY_CHECK_OUTPUT`。

水体清单保留 `detail`、`smooth` 下的 `path` 和 `bytes` 格式，模型路径按清单中的绝对路径（或仓库根目录相对路径）读取。它必须指向对应的双水面候选模型，不能用普通正式模型冒充。原先从输出目录隐式读取 `models.json`，现改为显式 `CITY_WATER_MODELS`。

## CI 与模型验收边界

工作流与 gxu 保持相同触发方式：面向 `main` 的 PR、`main` 的 push，以及手动运行；dev 推送不触发 CI。检查依次执行类型检查、lint、前端测试、可复现的数据测试和静态构建。PR 使用 `/nanning-city-atlas` 基础路径构建，不配置 Pages、不上传发布产物、不部署；主分支推送或手动运行会完成 Pages 发布。日常 dev 开发使用上方本地检查命令。

- 模型综合检查：`python3 scripts/validate_assets.py`，需要对应 Python 依赖和正式资产。城区版本保留源地理输入及各项几何检查，不因裁切提前成功退出；仅将外围数量和道路覆盖预期调整为实际保留范围，固定体积、三角面预算与来源散列检查继续执行。
- 模型独立检查：`python3 scripts/validate_runtime_assets.py`，可在完整源检查被历史计划失配阻塞时运行；依次执行铁路、道路、桥梁、地标及地形检查，汇总失败并返回非零状态，不能代替完整源检查。
- 裁切专项：`python3 scripts/check_urban_scope_exports.py`；加 `--baseline work/full-city` 可逐字节比较未改动的压缩块及材质。还检查主要水系原地形连续性、外围地形接缝、林冠面内净空、渐退末端贴地、外围道路净空和森林底色来源；带基准时还比较林地覆盖。详见 [城区范围](modeling/URBAN_SCOPE.md)。
- Blender 源模型、局部导出与候选比较：按 [建模专题](README.md#建模专题) 执行，需要 `.blend` 的检查须先具备源文件。
- 人工检查：地图加载、地标定位、漫游、图层、光照、画质切换、截图和 `inspect/` 页面。
- 手机性能与弱网：参见 [手机体验](design/MOBILE.md)，桌面模拟不替代真机测量。

新的报告与截图写入 `work/`。其他历史建模脚本仍可能依赖旧实验目录；缺少输入时应说明限制，不能用当前资源冒充历史基准。
