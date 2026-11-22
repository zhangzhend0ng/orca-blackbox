# macOS 参数面板寻址攻坚（任务 A2）：walls 目标 blocked 归因报告

本轮请求标签 `mac-author-20261122-02`（续 `codex/mac-author`）。目标：让壁环数（wall_loops 2→3）在 Mac 参数面板上闭环，或给出精确 blocked 归因。结论：**blocked**——缺口比上轮定位得更深也更精确：参数值通道本身完好（可读、可写、离屏字段也可写），卡点收敛到「wall_loops 所在的参数树 outline 硬虚拟化 + 该页所有滚动通道失效 + 预设编辑器入口在 Mac build 缺失」这一个组合上。判据链（`inspect_preserved_settings` 允许且仅允许 `wall_loops 2→3` + 三相位读回 + 68 层 + gcode 回显）无需改动，继续待用。

执行环境与任务 A 相同：Mac mini coilwin@172.18.6.213，测试登录 coilwin(502) 后台 Aqua 会话（console 由 coil 501 占用），SUT `/Applications/Snapmaker Orca.app` 2.4.1 只读。探针经一次性 LaunchAgent（gui/502，签名 Python.app）执行，驱动入口 `tools/mac_panel_probe.py <probe>.py <harvest>`，与 worker 同一信任通道。

## 对上轮（mac-author-port-2026-11-22.md）结论的两处修正

1. ~~「自绘控件标题全空、AX 值读不到」~~ → **修正**：控件 AXTitle 确实全空，但 **AXValue 与 AXHelp 完全可读**。AXHelp 即上游参数工具提示全文（例：层高字段 "This is the height for each layer. …"、行宽字段 "Line width of outer wall. …"）。24 个扁平字段已全部按 help+值指纹识别（见下）。
2. ~~「AXScrollBar 下箭头 AXPress 18 次字段集纹丝不动」~~ → **修正**：箭头按压**有效**（字段 y 每次位移 -80px，`scroll_results.json` 全程可验），上轮被"字段集合不变"误导——那 24 个字段就是扁平页的**全部**内容，滚动只是整列表平移。

## 参数面板结构地图（本轮实测，1200×800 窗口，origin (360,85)）

| 区域 | y（绝对） | 内容 | AX 可寻址性 |
| --- | --- | --- | --- |
| Process 头行 | 689 | 展开箭头(368)、标题、(453,686) 视图切换复选框、Advanced(673,689)、View all object's settings(730,689)、Compare presets(756,689) | 全部按钮带 AXHelp |
| 预设行 | 729 | (372,729) 无 help 按钮（按下无效果）、Save current Process(726,729)、Search in preset(752,729) | 有 help；**无 edit 图标**（对照：printer 行有 'Click to edit preset'(363,204)，filament 行有 (542,497)/(752,497)） |
| 页切换带 | 703 | x390-450=扁平页（默认）、x465 与 x525 切到 outline 页 | 自绘，无 AX 元素，坐标点击有效 |
| 扁平页列表 | 832-2320 | 24 常用参数（层高×2、行宽×8、seam 15%、slice_closing_radius 0.049、resolution 0.012、XY 补偿、象脚 0.15、桥接族…），跨滚动全量 AX 暴露 | 值+help 全可读写（含离屏，实测 y1444 写 101 读回后还原） |
| outline 页（(453,686) 勾选或 x465/x525 点击后） | 718 起 | 筛选 combobox(387,718) + 4 个自绘 chip(379/701,742/760) + **AXOutline/AXRow/AXDisclosureTriangle/AXScrollArea** | 仅暴露 2-3 行（AXRows=AXVisibleRows=2），三角可展（行数 2↔3），**一切滚动通道失效** |

24 扁平字段无一个值为 2：对照 3MF `project_settings.config`（578 键，wall_loops=2、line_width=0.82 等真值）可确认 wall_loops **不在扁平页**，位于 outline 页的未物化区域。

## 逐方向实证（按任务书四个方向）

**方向 1 System Events 枚举**：blocked（权限）。`osascript … tell process "Snapmaker Orca"` 返回 `execution error: Not authorized to send Apple events to System Events. (-1743)`（panel2 `result.json` sysevents 项）。签名 Python.app 无 Automation(TCC) 授权，后台会话无法弹授权框。

**方向 2 键盘/焦点直填**：机制成立、触达失败。
- 正面：AXFocused+AXValue+AXConfirm 对已暴露字段有效（含离屏虚拟化字段，panel2 offscreen_write：0.049→101→还原）；CGEvent 键盘事件可到达目标进程（搜索框真键入落了首字符 "w"）。
- 反面：`Search in preset` 暴露的是真 wx 搜索框（placeholder `Search in preset...`）但它是**预设名搜索**（结果在自绘 popup，AXUnknown 窗口仅 1 空元素）；程序化 AXValue 赋值 "wall" 不触发过滤（无 wxEVT_TEXT）；多字符 unicode 键入只落首字符。outline 页 AXRow 不接受 AXFocused（-25205），Down/PageDown 键 30 次行集纹丝不动（panel12 kb0-kb5），combobox AXPress -25206。
- 结论：焦点/赋值通道只对已物化控件有效，而 wall_loops 控件在任何可达状态下都未物化。

**方向 3 预设文件路线（对照诊断）**：文件层已核实，GUI 层未测（预算，见下）。预设 `0.40mm Standard @Snapmaker U1 (0.8 nozzle)`（34 键）继承 `fdm_process_U1_0.40_nozzle_0.8`，有效值全量在 3MF config；datadir 每次由 worker 播种、可写，改预设+重载在文件层可行，但因不属业务路径且 GUI 预算耗尽，未跑 GUI 级对照。

**方向 4 截图 OCR**：blocked（权限）。`screencapture -x` 6s 超时（panel2、与上轮一致），后台会话代理无屏幕录制 TCC。

## 补充通道（任务书之外，均留证）

- **右键上下文菜单**：预设行 (500/726/752,729) 三处右键后 AX 无任何菜单元素暴露（panel12 rc*_menus 均空）。
- **对话框入口扫描**：AXPress 图标全扫——Note(730,174)、Sync Filament(698,457)、Compare presets(756,689) 弹真对话框（AX 内容完好）；"Object/part setting"(730,689 触发，1345×480) 与预设下拉 popup 均为自绘（分别仅 6/1 个 AX 元素）；`Save current Process`(726,729) 与 printer 'settings'(756,174) 的 AXPress 返回 -25204（模态阻塞超时）。**工艺预设行不存在 edit 图标**——这是与 Windows 侧（diag_137：预设行三图标含「编辑」，侧边栏五 tab Quality/Strength/Support/Multimaterial/Others）的关键差异，Mac 2.4.1 把 tab 行换成了 y703 页切换带 + outline 视图。
- **outline 页滚动通道全灭**：滚动条箭头 AXPress（该页 inert）、CGEventCreateScrollWheelEvent（未聚焦/已聚焦两种投递均无效）、滚动条 AXValue（空串；CFNumber 设置无效果）、AXScrollToVisible（报错）、键盘 Down/PageDown（无效）。AXDisclosureTriangle 展开只让行数 2↔3 摆动（视口容不下更多物化行）。
- **菜单栏**：File/Edit/View/Calibration/Help/Window 全枚举，无工艺参数设置入口。

## blocked 归因（精确版）

壁环数控件位于参数树 outline 未物化区域；该 build 的 outline 硬虚拟化（仅物化视口内 2-3 行）且上列全部滚动/推进通道在该页失效；绕道完整编辑器对话框的入口（预设行 edit 图标）在 Mac build 不存在；两个可解锁的外部通道（屏幕录制→OCR 坐标点击、Automation→System Events）均卡在 TCC 授权，需管理员在系统设置为签名 Python.app 开启。上游若把工艺面板参数树完整暴露为 AX（如同扁平页那样全量暴露），缺口即消失。

## 纪律与预算

全程后台 Aqua 会话，未触碰前台 coil；每轮探针 LaunchAgent 均 bootout 验证、Orca 进程清零（各 result `orca_left: []`）。**墙钟超预算**：11 轮 GUI 探针累计约 48 分钟（上限 30 分钟），超出部分如实申报；其中 probe8 因模态阻塞悬挂耗掉约 15 分钟驱动超时，属本轮执行失误，后续应维持每探针硬保险丝（probe9-11 已带 330-420s fuse）。

## 产物与复跑

- 探针证据（本机，git 惯例不入库）：`artifacts/mac_probes/2026-11-22/panel2 … panel12/`（`result.json` + `tree_*.json` + `inventory.json` + `worker.log`；panel2=全属性 dump+图标扫+tab 带、panel4=搜索框键入、panel6=mystery 复选框+树页首dump、panel7=tab_map+滚动箭头、panel8=滚轮走行、panel9=三角展开+AXRows、panel10=焦点滚轮+scrollto、panel11/12=右键/下拉/键盘）。
- 工具链入库：`tools/mac_panel_probe.py`（LaunchAgent 驱动，任意 `runner/macos/panel_probe*.py` 可换）+ `runner/macos/panel_probe.py … panel_probe11.py`（11 个可独立复跑的探针）。
- 复跑示例：`.venv/bin/python -B tools/mac_panel_probe.py panel_probe5.py panel6`。
- worker（`runner/macos/project_copy.py`）walls 相位未动——失败点仍是 `baseline.wall` 的 `No Strength tab candidate`，与 blocked 归因一致；判据链保持待用。

## 推送状态

与上轮相同：本机无 GitHub 推送凭据，提交落本地分支 `codex/mac-author`，push 待凭据后 `git push origin codex/mac-author`。
