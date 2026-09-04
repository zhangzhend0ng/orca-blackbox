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

> 追加修正（2026-09-03 夜实弹采样后，详见 §五.1）：场景①的"按钮可见可点"
> 需**分族**——MsgDialog 族（如混色对话框）成立；MsgUpdateConfig（预设包
> 更新弹窗）检测可见（Window@depth1 + 全文案）但动作按钮不暴露，处置走
> win32 WM_CLOSE（sweep，PITFALLS §19）。owned 对话框挂主窗子树下、不在
> 桌面顶层——顶层枚举会漏（wizard 先例同）。

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
| ① | **启动拦截窗检测与确定性处置**（更新包弹窗、首启向导类） | **检测高、按钮驱动分族**：MsgUpdateConfig 实测在树内可见（Window @depth1 + 全文案 Text），但**动作行按钮不暴露**（子树内只有滚动条按钮）——InvokePattern 驱动该弹窗不可行，处置继续走 win32 WM_CLOSE（sweep 已盖戳：3 相合成检查 + 真弹窗 close_test）；MsgDialog 族（混色对话框实测）OK/Cancel 原生可见可点 | **今天 22 RED 事故的直接对策**（PITFALLS §19）；弹窗属环境噪声，本就不该由视觉断言吸收 |
| ② | **面板/对话框区域锚定**：用命名 Pane/Text 的 rect 圈定区域，视觉断言只在区域内做 | 高（分区层命名 + rect 可靠） | 直击 §12/§13 坐标带漂移、§17.8 黑盒坐标类痛点；模板仍保留在区域内部做状态判定 |
| ③ | 参数行控件定位与取值 | **不可行**（自绘，结构层无信号——raw view 同样无，见 §五.2） | —— 继续走视觉 + OCR / WM 通道（现状） |

## 五、后续验证清单（开口子前补）

> 状态更新（2026-09-03 夜，`runner/uia_probe.py` 增 --raw/--zh/--dialog-sample
> 模式 + `hv_uia_probe.ps1` 模式透传，客机实跑）——①②③ 已闭环：

1. **更新弹窗实弹采样**：✅ **已完成**（--dialog-sample，20:14 实跑；前置 = census v2
   发现 Setup Wizard 模态阻塞启动链、8s 宽限后 WM_CLOSE 放行，真 feed 仍在推
   2.2.56.2 → 弹窗按需复现，PITFALLS §19.1）。结论：MsgUpdateConfig 在 UIA 树内
   以 **Window @depth1 'Configuration update'** 可见，正文 Text 全暴露
   （"A new configuration package is available…"）；但**子树内动作按钮不暴露**
   （只有 Line up/Page down/Line down 滚动条钮）→ 场景①按分族修正：检测可行，
   InvokePattern 驱动该弹窗**不可行**，处置一律走 win32 sweep（WM_CLOSE，3 相
   blocker_sweep_check + 真弹窗 close_test 双证）；MsgDialog 族（混色对话框）仍
   保持"原生按钮可见可点"结论。owned-window 教训：主框 owned 对话框在 UIA 里挂
   在**主窗子树下**而非桌面顶层（wizard 先例同），顶层扫描会漏。
2. **RawViewWalker 对照**：✅ **已完成**（--raw，comtypes `iuia.RawViewWalker`
   ——注意 walker 是 [propget] 属性不是方法）。全树 103（pywinauto）vs 114
   （raw），named 63 vs 69；差值 11 节点/6 named **全部是 Setup Wizard 的
   wxWebView HTML 子树**（Chrome_RenderWidgetHostHWND、"Welcome to Snapmaker
   Orca"/"Get Started" @depth12）；app 自身结构逐类相同（Button 21=21、Edit
   2=2、Text 7 vs 9 的 +2 也是 webview）→ **自绘参数行在 raw view 同样不存在**，
   §三 天花板结论不变。
3. **语言切换稳定性**：✅ **已完成**（--zh，conf app.language=zh_CN）。结构完全
   同形（103 节点/63 named/91 automationId）；名字集合 en∩zh 仅 **11/63（17%）**
   相同且全是技术名（Close/Default Setting/GLCanvas/panel/mm/wxWebView/引导_P1…），
   用户可见文案全量翻译（导出G-code文件↔Export G-code file、混色匹配↔Color
   Mixing Match、层高↔Layer height…）→ 定位词表**必须按 locale 注册**；①②落地时
   词表入 anchors 注册表（双语条目），纯技术名可跨 locale 复用。
4. **UIA 查询对渲染帧率的干扰**：记录在案——本日 6+ 次探针运行（含深度走树）
   期间应用保持响应、其后 OCR 锚点仍 score=1.000；UIA 为只读 WM_GETOBJECT 查询，
   按黑盒纯度边界记录为无副作用迹象（未做帧率基准测量；如开口子后在真实用例中
   观察异常再补基准）。

## 六、纯度边界说明

BLACKBOX_CASES 的观测通道约定为 截图/窗口消息/文件系统/对话框。UIA 查询
本质是窗口消息家族的只读 accessibility 查询（WM_GETOBJECT），不读进程内存、
不挂运行时钩子——与现有 WM_* 通道同族；但"结构化控件树"确实超出既有四通道
的字面范围，这正是 STRUCTURING_PLAN 要求"先评估再开口子"的原因。本评估
工具（uia_probe）仅为探针，未注册 cases.py，未进入任何回归路径。

## 七、向导 HTML 子树分级结论（2026-09-04，--wizard 实弹 5 轮）

> 方案与对抗记录：`docs/UIA_WIZARD_PROBE_PLAN.md`（独立 REFUTE: APPROVE）；
> 工具 `runner/uia_probe.py --wizard`（commits 60297a2..2658b1d）。客机
> win11-test @1920x1080，en_US，11:10–11:32 五轮实弹。

**分级结论：L0 检测 ✅；L1 定位 ✅（有激活前提）；L2 驱动 ✅ 但仅经
LegacyIAccessible.DoDefaultAction（InvokePattern 不可得）。**

- **L0**：win32 `#32770 'Setup Wizard'`（toplevel 枚举）与 UIA 子树
  （comtypes RawViewWalker 重根 `ElementFromHandle(wizard_hwnd)`）双通道可见。
- **L1**：激活后（判据 = Document 子树内命名节点 >0；实测 rewalk 1–5 次 ×4s
  内达成）24 节点/12 命名/交互 2：`Get Started`（**Hyperlink**）+ `Close`
  （Button），均 invoke=False / toggle=False / **legacy=True**。
- **L2**：`DoDefaultAction('Get Started')` 真实翻页：named +9/−6（移除
  "Welcome to Snapmaker Orca"/"…Let's start!"/引导_P1，加入 "Please select
  your login region"+区域五选项+"Next"+引导_P21），nodes 24→35，向导未关闭
  → **W4 定案：Get Started = 前进（登录区域页），非取消**。同法驱动原生
  Close 亦真关（run 4，wizard_closed）。前后 PrintWindow 截图字节级有差异
  （171,894 bytes / 454 行，集中于页面内容区）。
- **W2 激活时序（关键坑）**：Chromium web a11y 树懒激活——boot 后首次 UIA
  查询只见浏览器 chrome 结构（RootView/ClientView/Chrome_RenderWidgetHostHWND
  + 空 Document + 原生 Close），与 §五.2 的 --raw 先例（主窗走树前已查询数
  分钟）不矛盾。**任何"web 不可见/无按钮"结论必须先过激活重试**。三次假阳
  性/阴性教训：单查过早下结论（run 1）；`DoDefault` 属性名不存在（真名
  `DoDefaultAction`，客机 comtypes introspection 一手源裁决）且属性查找失败
  被误标 invoked=True、重走撞上激活噪声出假 page_advanced（run 3）；Document
  有空壳 child 的弱激活门放行 15 节点 stub 树导致点了 Close（run 4）。
- **zh 采样（W3 新数据点）**：zh_CN 种子 boot 2/2 二十秒内无向导
  （not_present）。上游门 `GUI_App.cpp:7374 config_wizard_startup` =
  `!m_app_conf_exists || only_default_printers() || privacy empty`，与
  language 无关（conf 预写、种子同源）；en 5/5 弹 vs zh 2/2 不弹的分叉机制
  **未定，存疑待查**。zh L1 采样在本配置下不可得。
- **场景①处置建议**：向导检测可结构化（win32+UIA 双通道）；驱动通道 =
  LegacyIAccessible（非 Invoke）；现有 WM_CLOSE 处置维持有效，如需可升级为
  "结构化识别 + 确定性翻页/关闭"。回归用例仍不碰 HTML（PITFALLS §3 0904
  修订）。
