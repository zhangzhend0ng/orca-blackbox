# orca-blackbox 结构化方案（第一期落地 + 第二期路线）

> 定稿于 2026-09-02 会话。本文是唯一决策记录：为什么这么改、改什么、不改什么。
> 第二期（anchors / pytest 壳）动手前先读本文的"决策记录"一节。

## 三层结构

```
┌─ 编排层（可替换，本期落地的就是这层的地基） ─────────────┐
│ cases.py registry → run_regression.sh / hv_go.ps1 / mcp   │
│ (第二期) tests/ pytest subprocess 壳 + conftest 硬门禁    │
├─ 用例层（脚本骨架）────────────────────────────────────┤
│ m*.py 用例脚本 + m3_common.verdict()（exit code = 判定）  │
├─ 驱动层（永不改动）────────────────────────────────────┤
│ harness/ — winutil/launcher/profile/shot_archive/...      │
└──────────────────────────────────────────────────────────┘
```

## 决策记录（对号入座结论）

**白盒线扩容后的双通道定位（2026-09-02 吸收 monorepo `ab3b34adf5`/`930680170f`/
`453dc208e1` 后补充）**：白盒 full-app 套件已达 28 例（11 条业务路径全 app 测试，
21 过 / 7 env-skip），m3a-m3i 的业务路径白盒侧现也有强覆盖。据此明确双通道分工：
**白盒 28 例 = 快回归**（ORCA_GUI_TEST_MODE 隐藏窗口 + 测试钩子内驱动）；
**黑盒 35 例 = 独立端到端验证**（不依赖测试钩子，从渲染/输入注入层面复现用户路径）。
registry 中 m3a-m3i `suite: None` 的定位依据即此。另核实：`453dc208e1` 把
ORCA_GUI_TEST_MODE 默认为 1 只发生在测试 exe 的 bootstrap（不进 snapmaker-orca.exe），
黑盒 launcher 剥变量逻辑不受影响；BLACKBOX_CASES.md 的源码行号引用已按新 HEAD
复核（3 处漂移已修正：MainFrame 1600→1602 / 2470→2473，BBLTopbar 663→618）。

**为什么不 in-process 接 pytest：**

- **2d 进程隔离是最硬约束（成立）**：驱动是 ctypes + GUI 子进程 + watchdog，
  挂起方式包括 app 启动挂起 / 消息注入死锁 / GL 崩溃带崩驱动。挂起用例必须能被
  外部超时**单独处决且不连坐**；`run_case` 的不变量是"超时只杀驱动
  （mcp_server.py 注释 *the DRIVER, not the app*）、app 用 WM_CLOSE 清扫"——
  这是跨进程语义，in-process 的 pytest 没有"杀测试保会话"这个操作。
- **2a "pytest 缓存污染黑盒纯净性"不成立**：纯净性在 datadir/resources 层解决
  （seed_profile 只用仓内 resources，profile.py 注释），与 pytest 的仓库级缓存
  正交。**任何人以 2a 为由反对接 pytest，视为编造的理由。**
- **2c "单文件可拷走"半真**：真实载荷是三个按用例名索引的机制——
  push_verify.py 单文件推送、run_suite 每例独立日志、zlog.ps1 按名拉日志。
  subprocess 壳下全部保留。
- **"不用 pytest"是从 m0/m1 引擎实验演进出来的未发生决策**，不是做过的决策。
  今天接 = subprocess 壳（pytest 用例体 = subprocess.run 原脚本），
  原脚本保留独立入口、挂起可外部处决、JUnit/marks/--lf 白拿。

**为什么 case registry 比接 pytest 紧迫**：用例清单曾维护在三处
（hv_go.ps1 默认列表 / run_regression.sh 的 CASES / mcp run_case 扫描），
27→35 时被迫手工同步过一次。registry 是 mark 分层的前置。

**为什么自研只到 JUnit emitter 为止**：在 ps1/bash/mcp 三处重造 `-m smoke`
就是劣化重造 pytest。mark 分层的需求交给（未来的）pytest 壳，不自研第三层。

## 第一期（本仓库本次改动）

1. **cases.py 唯一事实源**（纯数据）：name → file/milestone/tier/suite/summary/enabled。
   - name = 脚本 stem，**永不重命名**（push_verify / zlog / 飞书表历史链路依赖名字）。
   - 增删改查 = 改一条数据；停跑用 `enabled: False`（软删，不物理删）。
2. **三入口改读 registry**：run_regression.sh、runner/hv_go.ps1、mcp_server.py。
3. **verdict 层 JUnit XML**：harness/junit_report.py（标准库，无新依赖），
   由跑批入口在用例结束后解析日志 verdict 块生成（复用 mcp 已有解析逻辑，
   抽到 harness/case_runner.py 共享）。单用例直跑零开销，verdict 输出格式不变。
4. **only-failed**：跑批失败用例写 artifacts/failed_cases.txt；
   hv_go 空参时若该文件非空则优先以其为列表。

验收：tools/check_registry.py 一致性自检 PASS；dry-run 展开列表与旧 35 例
逐一相等；构造数据验证 emitter；git status 确认无用例脚本 / harness 驱动被改。

## 第二期（未实施，按痛感知否推进）

1. **anchors.py 定位资产集中**：模板/锚点/色值/OCR 语料收进命名锚点表，
   用例脚本禁止散写阈值与坐标。UI 改版时打击面收敛到 anchors.py + 换图。
   配套 `m0_anchor_health.py` 冒烟：app 起来后全量匹配锚点，报失效清单
   ——UI 升级后 5 分钟知道打击面，不用跑 35 例被红淹没。
2. **tests/ pytest subprocess 壳**：parametrize 从 cases.py 生成；
   conftest 做 session 级硬门禁（分辨率/远控层/DPI 不过直接 fail-fast）；
   marks 从 tier / known_limitation 映射（xfail strict=False 替代手工 ⏸）；
   `-p no:cacheprovider`；`--junitxml` + pytest-html。
3. **ui_runner.py 接 registry**（现状只有 m1/m2 按钮，收益低，随壳一起做）。
4. （中期评估，非承诺）UIA 混合定位：控件定位走结构层（对主题/DPI 免疫），
   视觉模板降级为渲染正确性断言。需开"纯视觉黑盒"原则的口子，先评估
   Orca 的 accessibility 树质量再定。

## 业界对照（结论摘要）

- 编排/报告层可直接拿来用：pytest + pytest-html + pytest-rerunfailures
  （套在 subprocess 壳外，2d 不变量完好）；allure 要 dashboard 时再上。
- 驱动层无现成可用：Playwright/Selenium 只管 Web；WinAppDriver 走 UIA 且
  真输入会被远控层吞（PITFALLS #4）；TestComplete/Squish 商业且整体换血；
  MaaFramework m0 已实测排除。**自研驱动层是正确选择，坑册就是证据。**
- 断言层：OpenCV/Tesseract 已是业界事实标准。Applitools 类视觉基线管理
  解决的正是"UI 改版迁移"，但商业 + 截图上云有顾虑，只评估不决定；
  anchors.py + anchor_health 自检是约束下没有现成替代品的自研路线。
