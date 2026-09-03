# UIA 混合定位评估（2026-09-03）—— 结论：有限开放，三场景分级

> 对应 `STRUCTURING_PLAN.md` 第二期 #4（"UIA 混合定位：控件定位走结构层……
> 先评估 Orca 的 accessibility 树质量再定"）。本文是评估结论，不是承诺；
> 开口子仍需按计划文档要求过评审。
>
> 工具：`runner/uia_probe.py`（`5e2fa9f`+`e7dc5a8`）+ `runner/hv_uia_probe.ps1`，
> 客机 INTERACTIVE 计划任务 `uia_probe`（PITFALLS 18.7 通道），pywinauto
> 0.6.9 / Python 3.11 / win11-test @ 1920x1080 / Orca 2.3.6 dev build（08-24）。
> 探针产物：客机 `C:\coil\uia_probe_{out,compact}.json` + `_report.txt`。

## 一、结论

**有限开放（GO with scope）**：UIA 结构层只对**对话框/面板/命名按钮的粗粒度
定位**可用，参数级控件定位不可用。混合定位路线按三级场景推进（见 §四），
"视觉模板降级为渲染正确性断言"只在场景 ①② 的范围内成立；Prepare 侧栏
参数行、菜单、gizmo 工具条仍必须以视觉通道为主。

依据：全树仅 **103 个节点**（MAX_DEPTH=12 / 节点上限 4000 / cut_by_depth=0，
即穷尽），其中 Pane 70、Button 21、Text 7、**Edit 仅 2**——Orca 的参数行
由 OG_CustomCtrl 自绘（PITFALLS §6 / §17.9 互证：GetWindowText 为空的同一
批控件，UIA 同样看不见）。结构层存在天花板，且天花板正好落在测试最需要
的参数断言之下。

## 二、树质量数据（seeded datadir，idle-boot 就绪后最大化，走树 ~3s）

| 指标 | 值 | 备注 |
|---|---|---|
| 全树节点 | 103 | cut_by_depth=0，**全量非采样** |
| 命名率 | 61%（63/103） | 分区/按钮层命名良好 |
| automationId 覆盖 | **88%**（91/103） | 但全部是 **wx 窗口 id**（-31854 类负整数），**非语义 id** |
| 最大深度 | 9（上限 12 未触顶） | wx panel/sizer 层级链 |
| 控件类型分布 | Pane 70 / Button 21 / Text 7 / Edit 2 / ScrollBar 1 / … | 参数行缺失即自绘证据 |
| 原生 MenuBar | **无** | Orca 顶栏自绘，`menu_bar(0)`，菜单级混合定位无门 |
| 主窗类名 | `wxWindowNR`（framework=Win32） | 顶层单窗 |

**可见的东西**（示例，名字 + 非零 rect + wxId）：
`Color Mixing Match` / `Multimaterial` / `Filament Management` / `Filaments`
（左下混色分区，x≈33-387）、`Export G-code file` / `Slice plate`（右上动作区，
d3）、`Close`。分区头 Text/Pane 在深度 6-9。

**不可见的东西**：侧栏参数行（层高/填充等 OG_CustomCtrl 行）、组合框当前值、
gizmo 工具条与 tooltip、（自绘）菜单条。

## 三、探针迭代教训（工具自身的坑，已修）

1. **v1 裸启 exe = 走到启动闪屏**：`snapmaker-orca.exe` 5 秒内最大面积窗口
   是 boot 链上的窗，27 节点全是 Pane。v2 改走用例同款
   `profile.seed_profile()` + `launcher.launch()`（`find_main_window` 90s
   等真窗 + datadir 隔离——顺带修掉 v1 误用真实 datadir 的问题）。
2. **拿到 hwnd ≠ 框架建完**：`find_main_window` 返回后 wx 还在铺子控件，
   立即走树只得 80 节点。v2.1 以 `anchors.wait_for("tab_prepare_active")`
   为就绪门（2s 内 score=1.000）再最大化 + 走树。
3. **深度截断恰好切掉目标**：v2.1 的 MAX_DEPTH=9 与侧栏采样 `depth<=6`
   正好把混色分区（d6-9）切掉，制造了"侧栏盲"的假阴性；v2.2 全深度
   穷走 + 空间采样去深度条件后数据才自洽。

## 四、场景分级（若开口子，按此顺序）

| 级 | 场景 | 可行性 | 价值 |
|---|---|---|---|
| ① | **启动拦截窗检测与确定性处置**（更新包弹窗、首启向导类） | **高**：wxDialog 的 OK/Cancel 是原生 wx 按钮，结构层可见可点（InvokePattern） | **今天 22 RED 事故的直接对策**（PITFALLS §19）；弹窗属环境噪声，本就不该由视觉断言吸收 |
| ② | **面板/对话框区域锚定**：用命名 Pane/Text 的 rect 圈定区域，视觉断言只在区域内做 | 高（分区层命名 + rect 可靠） | 直击 §12/§13 坐标带漂移、§17.8 黑盒坐标类痛点；模板仍保留在区域内部做状态判定 |
| ③ | 参数行控件定位与取值 | **不可行**（自绘，结构层无信号） | —— 继续走视觉 + OCR / WM 通道（现状） |

## 五、后续验证清单（开口子前补）

1. **更新弹窗实弹采样**：下次弹窗出现时跑探针，确认 wxDialog 按钮的
   UIA 可见性与 InvokePattern 可点性（场景 ① 的最后一环）。
2. **RawViewWalker 对照**：pywinauto 走 ControlView；raw view 是否暴露
   更多自绘结构，一次探针即可定论（预期：否，但值得 5 分钟实锤）。
3. **语言切换稳定性**：本探针在 `en_US` datadir 下测得；zh_CN 下名字
   全变（探针关键词已是双语）。若 ①② 落地，定位词表必须入 anchors
   注册表统一维护（结构层资产 = anchors 的新 kind）。
4. **UIA 查询对渲染帧率的干扰**：走树期间截图帧是否有副作用（预期无，
   UIA 是读查询；按黑盒纯度边界记录在案）。

## 六、纯度边界说明

BLACKBOX_CASES 的观测通道约定为 截图/窗口消息/文件系统/对话框。UIA 查询
本质是窗口消息家族的只读 accessibility 查询（WM_GETOBJECT），不读进程内存、
不挂运行时钩子——与现有 WM_* 通道同族；但"结构化控件树"确实超出既有四通道
的字面范围，这正是 STRUCTURING_PLAN 要求"先评估再开口子"的原因。本评估
工具（uia_probe）仅为探针，未注册 cases.py，未进入任何回归路径。
