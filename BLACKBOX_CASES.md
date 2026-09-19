# BLACKBOX_CASES — 黑盒用例清单与覆盖矩阵（U1 限定）

> 策略（2026-08-29 定，2026-09-02 更新）：**以黑盒为主**。白盒线（`tests/wx_gui/`）
> 已从 16 例扩到 **28 例 full-app**（monorepo `ab3b34adf5`，+695 行：11 条业务路径
> 全 app 测试，21 过 / 7 env-skip / 199 断言），角色从"最小安全网"升级为
> **快回归通道**；黑盒 36 例回归的定位随之明确为**独立端到端验证**——不依赖
> `ORCA_GUI_TEST_MODE`、不依赖测试钩子，从渲染/输入注入层面复现用户真实路径。
> 白盒相关新机制：双测试模式（`930680170f`，`ORCA_GUI_TEST_MODE=network` 跑真实
> 设备栈）；测试 bootstrap 默认 `ORCA_GUI_TEST_MODE=1`（`453dc208e1`，仅测试 exe，
> **不进 snapmaker-orca.exe**，黑盒 launcher 剥变量逻辑不受影响）。
> 新增用例流程 = **先代码调研 → 落四元组 → 再写脚本**。
> 预设只关心 **Snapmaker U1**（0.8/0.4 nozzle），Bambu/第三方预设一律不测（坑 #10 门控全部绕开）。
>
> 黑盒纯度边界：观测通道只有 截图 / 窗口消息 / 文件系统 / 对话框。**只做静态代码调研，
> 绝不做运行时挂钩**（不读进程内存、不调 app API）。白盒源码只用来回答三个问题：
> 功能入口在哪 / 门控条件是什么 / 期望行为是什么。

## 覆盖矩阵（功能面 × 可测性 × 兜底）

| 层 | 含义 | 功能面 | 兜底 |
|---|---|---|---|
| **A 强覆盖** | 有天然外部产物（文件/对话框/画面/按钮态） | 启动与加载、切片管道、参数→重切、预设切换→gcode、多板切片、视图切换、删除/清空、导出 gcode/3mf、错误路径（损坏文件/空场景） | 无（黑盒直接测） |
| **B 弱覆盖** | 可操作但断言弱/交互深 | 画布对象变换（gizmo）、undo/redo、深层设置面板、快捷键/菜单 | 视觉冒烟级断言；价值高时白盒兜底 |
| **C 不可测** | 无外部信号 | 内部状态精确断言（矩阵值/slice_valid/preset 脏态）、切片几何正确性（走线/悬垂/支撑）、纯后台逻辑（崩溃恢复/Sentry/更新）、网络设备栈 | 白盒安全网（存量）或接受风险 |

**关键事实**：A 层之所以是"核心链路全覆盖"，因为切片软件的用户价值链
（加载→配置→切片→预览→导出）每一步都有外部产物。**"导出 gcode 可用"是完成检测的
确定性布尔信号**（`MainFrame::can_export_gcode()`，见下），比绿勾模板强一个数量级——
探测式点击 Export → 模态保存对话框出现 = 完成，不出现 = 未完成，无需模板。

## 工作流（加用例前必做）

1. **查白盒文件** `tests/wx_gui/wx_gui_*.cpp`（第一手调研材料：入口/预设名/快捷键/fixture）
2. **查源码**：功能入口（按钮/菜单/快捷键）、门控（`get_enable_slice_status` /
   `can_export_gcode` 等）、期望行为、fixture 预设
3. **落四元组**到本文件：`（白盒用例引用 / 源码入口+门控 / 黑盒操作序列 / 外部断言）`
4. **实现脚本**（m3a/m3b/…，fresh profile + 真实启动，退出码 0=绿）
5. **跑绿**后把状态从 `planned` 改为 `GREEN`

## 用例清单

状态图例：✅ GREEN（已跑绿）· 🔵 planned（已调研未实现）· ⭕ 已有覆盖 · 🟡 降级/受限

### 已有（m0/m1/m2 覆盖）

| 用例 | 白盒引用 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 启动冒烟 | app_tests (1) | 主窗口出现、可见、尺寸>0 | m0_boot_check.py | ✅ |
| 视图切换 Prepare/Preview | business P2-9 | tab 选中色 teal(0,150,136) 翻转 | m1_minimal_loop.py | ✅ |
| 端到端切片 + Preview 工具路径 | app_tests (5) | done 绿勾模板 + 色度占比 ≥2×基线 | m2_slice_chain.py | ✅ |
| 模型自动加载（CLI 位置参数） | app_tests (5) 前置 | viewport 彩色占比 ≥1%（双轮稳定） | m2_slice_chain.py | ✅ |

### 新增（2026-08-29 批次）

| 用例 | 白盒引用 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 空场景拒绝切片 | business P3-13 | 点 Slice 不启动任务 + 按钮保持 idle + Preview 无色度 | m3a_empty_slice.py | ✅ |
| 损坏 3mf 优雅失败 | business P3-12 | 错误对话框出现 + app 存活 + 好项目二次加载模型到达 | m3c_corrupt_3mf.py | ✅ |
| 多板项目 Slice all | business P0-3 | Slice all 模式选中 + done 态（模型到达由切片成功兜底） | m3f_multi_plate.py | ✅ |
| 预设切换→gcode header | business P0-2 | combo 切 0.40↔0.24 @U1 + 重切 + 导出 + `; layer_height` 跟随 | m3e_preset_switch.py | ✅ |
| 参数改→重切→gcode diff | business P0-1 | **WM_SETTEXT + WM_KILLFOCUS 驱动真实提交链**（Field.cpp 的 wxEVT_KILL_FOCUS→propagate_value）：Edit 文本改 + 按钮回 idle + 重切 + 导出 + `; layer_height` 0.4→0.2 + 字节 diff | m3d_param_reslice.py | ✅ |
| 删除/清空场景 | business P1-7 + P2-8 | dropdown 菜单→Edit 子菜单→真实点击 Delete All 行：viewport 色度回落空床（<0.4%）+ 空场 Slice 拒绝 | m3b_delete_scene.py | ✅ |
| 导出 3mf→重载 | business P0-4 | File 菜单→Save Project as→保存对话框→文件落盘：zip 有效 + 3D/3dmodel.model 存在 + `printer_settings_id` 保留 "Snapmaker U1 (0.8 nozzle)" + 二次启动模型到达（≥1%） | m3g_export_3mf.py | ✅ |
| undo/redo 恢复场景 | business P1-6（菜单半）+ P1-7/P2-8 | Edit 菜单 Delete All 清场 → Undo 行真实点击→模型复现（≥1% 双轮）→ Redo 行→再度清场（<0.4%） | m3h_undo_redo.py | ✅ |
| View 菜单视角切换 | —（白盒无此用例；源码入口 add_common_view_menu_items，MainFrame.cpp:2473） | View 子菜单 Top/Front 行真实点击：两次切换各使 viewport 显著变化（diff>10，实测 45/116）——视角矩阵外部不可读，不做具体角度断言 | m3i_view_menu.py | ✅ |

### 新增（2026-09-02 批次：吸收白盒 ab3b34adf5 缺口）

| 用例 | 白盒引用 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 对象变换→3mf transform 精确断言 | ab3b34adf5:459（transform→instance matrix）+ :505（undo/redo 半，白盒兜底） | Move gizmo 窗口（ImGui，GizmoObjectManipulation.cpp:800 do_render_move_window）Position X 字段：OCR 定位值框→真实点击→消息键盘退格+键入'60'+Enter→OCR 字段变 60.00 + 模型质心位移 + Save Project as→`<build><item transform>` 平移 X 精确=60.0、Y/Z 不变（136/13.5）。**矩阵精确值断言经文件产物实现**——C 层"instance 矩阵不可测"仅限运行时读取，导出 3mf 后是明文 | m6a_transform_verify.py | ✅ |

### 受限 / 待办（B 层）

| 用例 | 白盒引用 | 状态与原因 |
|---|---|---|
| gizmo 拖拽（画布箭头拖动） | P1-5 | 🟡 拖拽本体断言弱——数值变换路径已由 m6a_transform_verify 覆盖（A 层），gizmo 拖拽留视觉冒烟 |
| 画布选中+Delete 键 | P1-7 变体 | 🟡 GLCanvas3D::on_char 的 WXK_DELETE 需先有选中（画布点击命中测试深），当前由菜单 Delete All 覆盖断言面 |

| 画布选中+Delete 键 | P1-7 变体 | 🟡 GLCanvas3D::on_char 的 WXK_DELETE 需先有选中（画布点击命中测试深），当前由菜单 Delete All 覆盖断言面 |

### 混色匹配（MixedFilamentBatchDialog，2026-08-29 批次，飞书表 48 条）

> 入口：'Color Mixing Match' 标题栏右端 add 按钮（Plater.cpp:2578，门控=模型颜色+≥2 耗材）。
> 弹窗 = 原生模态 #32770；内部控件点击**不带 root**（弹窗是独立顶层，root 解析在 frame 树内）。
> **U1 0.8 nozzle 无 Full Spectrum 预设** → Auto 模式 Start Matching 必弹喷嘴警告
> （MixedFilamentBatchDialog.cpp:2290，=飞书 #49）——确定性可测行为。Manual 模式不受影响，可完整跑匹配。

| 用例 | 飞书记录 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 入口+默认模式+喷嘴警告 | #29/#1/#49 | 有颜色模型→弹窗出现；combo 默认 'Auto'；Auto Start→警告弹窗（'Got it' 可关）+ 弹窗存活 | m3j_mixing_entry.py | ✅ |
| Manual 匹配全流程 | #10/#15/#27 | combo 切 Manual（popup 行 2 + 文本确认）→ Start→映射列表色度渲染（0→~0.12 双轮）→ Confirm 关闭弹窗→app 存活模型在 | m3k_mixing_match.py | ✅ |
| hover 色块→ΔE tooltip（OCR） | #24/#22 | Manual 匹配→真实鼠标移动悬停色块行→tooltips_class32 出现→Tesseract OCR 读出 `'Color Difference: Good (AE=0.0)'`→断言标题+等级关键词（Good/Fair/Poor）+ `AE=` 数值 | m3l_mixing_delta.py | ✅ |
| 自定义耗材增删边界 | #3/#5/#6/#13 | Manual 卡片 2 行×2 列=4 耗材→'+' 禁用（max_rows 边界，WS_DISABLED）；'−' 4→3→'+' 恢复可用；再'−' 3→2→'−' 禁用（边界）；匹配后色域警告 banner 文本 GetWindowText 直读含 '0%–70%' | m3m_mixing_filaments.py | ✅ |
| 取消二次确认 | #25/#26 | 匹配后 Cancel→确认弹窗 OCR `'Are you sure you want to discard this match? The current configuration will not be saved.'`→'Discard' 关闭不保存；重开后 Cancel→'Cancel' 返回弹窗结果保留（swatch 行在） | m3n_mixing_cancel.py | ✅ |
| 无模型提示 | #28 | 清场后点入口→OCR `'No model detected. Import a multi-color model to continue.'`+ 'Got it' 可关 + 批量弹窗不打开 | m3o_mixing_nomodel.py | ✅ |
| 视图/盘切换 | #14/#17/#18/#19 | 默认视图 'Isometric' + 盘 '01'；单盘左右箭头点击后 strip 像素 diff=0（no-op）；View popup 切 'Top-Front'（组合视角文本）→视图区色度变化；可再切 'Front' | m3q_mixing_view.py | ✅ |
| 匹配中状态 | #20 | Start 后 100ms 密集轮询抓到 `msctls_progress32` 进度条 + 'Stop Matching'（瞬态）；完成后映射渲染 + Stop 隐藏（IsWindowVisible） | m3r_mixing_progress.py | ✅ |
| 持久化 | #48 | 匹配→Confirm→Save Project as→重载：模型到达（色度 5.9%>2.1% 基线）→Color Mixing 面板混色内容保留（0.071）→弹窗可重开 | m3p_mixing_persist.py | ✅ |
| hover 提示冒烟（降级） | #8（#2/#9/#23 同族） | 增删按钮 hover→tooltip 出现+OCR 非空；swatch hover→'Color Difference' tooltip | m3s_mixing_hover.py | ✅ |

| 混色匹配入口门禁（耗材数） | T2#31-35 | 无方案 fixture：删除耗材至 1（trash 探测）→面板隐藏+1 耗材提示原文+弹窗不开；加回 3→弹窗开+Manual 行=3；加到 6→钳制 4（无冲突弹窗，stale）；有方案 fixture：直接开（#34/#35） | m4a_mixing_gates.py | ✅ |
| 批量弹窗 Auto/Manual 卡 | T2#2/#3/#4 | Manual 默认 4 行；Auto 卡 4 槽同标签+无选择 combo；行选择→匹配→Confirm→侧栏耗材 5→3（cleanup_unused_filaments） | m4b_batch_manual.py | ✅ |
| 侧栏混色面板 | 表1#45/#48/#42/#38 | 物理行材料名+种子条目+Options 按钮；菜单 Delete 清空→空态+添加可用；新增方案+物理耗材后条目完整；重开默认干净+1 耗材时面板隐藏 | m4c_mixing_panel.py | ✅ |
| 耗材删除/合并 | 表1#47/#46 | trash 静默删除（方案存活）；引用中删除→Warning 二次确认（原文 Static 直读）→取消保留/确认级联；剩 1 面板+trash 隐藏；Options 菜单 Edit/Merge with/Delete→混色合并到物理后条目消失 | m4d_mixing_filops.py | ✅ |
| 颜色上限（64） | 表1#41（表写 32，现 64） | 64 色 fixture：混色添加+耗材添加均禁用；删 1 个→恢复；上限以下 PLA 对可登记 | m4f_mixing_cap64.py | ✅ |
| 同色耗材混色+5 色预警 | 表1#9/#16 + T2#7/#9 | 全 PLA 同色 fixture：同色对无阻断可登记（F3 50%+F4 50%）；'12345'→Excessive 橙幅不阻止；批量匹配渲染映射列表（ΔE 细节留人工） | m4j_mixing_samecolor.py | ✅ |
| 细分层高 | 表1#36/#37 + T2#40/#41 | Advanced 开关→Multimaterial 页 'Subdivide Mix Layer'；0.4mm 勾选无警告；0.1mm 勾选→'Configuration Conflict'（原文）；切片完成（子层数值留人工） | m4g_mixing_sublayer.py | ✅ |
| 0.4 喷嘴模板/兼容 | T2#37/#38/#39/#44 | 0.4 变体 fixture：'0.10mm Color Mixing @Snapmaker U1 (0.4 nozzle)' 存在可选+Auto 无门禁匹配完成+tooltip OCR；0.8：无 0.10 模板+Auto Start 门禁原文（批量弹窗无模板下拉，断言 Process 预设；切换无确认弹窗已核实） | m4h_mixing_templates.py | ✅ |
| 混色切片+导出 | 表1#50（部分） | 比例+渐变两方案→切片完成→gcode 导出 1.36MB 含 5 种换刀标记；上传打印留人工 | m4i_mixing_slice.py | ✅ |
| 涂色工具调色板 | 表1#39（部分） | 选中模型→横排 gizmo 栏 'Color painting' tooltip→激活→ImGui 'Filaments' 调色板 6 色块（5 物理+1 混色）；逐块涂色留人工 | m4e_mixing_paint.py | ✅ |
| 比例模式 UI/边界 | 表1#1-#4 | Add Mix 默认 Ratio/2 行 50/50/推荐卡；跨类默认对红幅原文+OK 禁用；行增删按钮 3 行翻转增↔删；行 combo 排除已选；滑块 10-90 钳制+90% 高比例橙幅出现/中点消失 | m3t_mixing_add_ratio.py | ✅ |
| 比例登记/编辑/取消 | 表1#5-#8/#43 | 推荐徽章→50/50+预览重绘；OK 登记 'F2 50%+F3 50%'；单击条目 Edit Mix 保模式保参数；75/25 更新标签；取消无残留 | m3u_mixing_ratio_flow.py | ✅ |
| 循环输入校验 | 表1#10-#15 | 默认 '12'；徽章追加；合法格式过；空→'12'；单色 advisory；512 截断；'623'/'2a3'/','123' 红幅+OK 禁用（语法 [nn]，表写 '/' 为 stale） | m3v_mixing_cycle_input.py | ✅ |
| 循环流程/模式切换 | 表1#18-#20/#44 | '23' 登记（摘要 F2 50%+F3 50%）；'232'→67/33 更新；取消保留；Match↔Cycle 保图案；切 Ratio 重登记为比例型 | m3w_mixing_cycle_flow.py | ✅ |
| 匹配模式（弹窗内） | 表1#21-#29 | Match 卡默认（blend hex+15%+2:1:1）；GGGGGG/5 位→红幅+OK 禁；FF5733→6s 内重算（50/25/25→61/39）；Min Mix 滑块 15→3；取色器色格点击→hex 更新；OK 登记；重开 Match 保模式 | m3x_mixing_match.py | ✅ |
| 渐变模式 | 表1#31-#35 | 恒 2 行+Mix Effect+交换钮；换耗材预览重绘；默认 F3->F2 登记；交换→F2->F3；重开保 Gradient；推荐+取消无新增 | m3y_mixing_gradient.py | ✅ |
| 兼容性矩阵 | 表1#51-#60 | 11 耗材 fixture 10 对断言：同类放行（PLA/PETG）、PLA+PETG/ABS/TPU/BVOH 阻断+OK 禁；PETG+TPU/PA+PC/ABS+ASA/PVA+BVOH 现矩阵放行（表格 4 处 stale，FEISHU_MAPPING 已注） | m3z_mixing_compat.py | ✅ |

**OCR 技术事实（2026-08-29 实测）**：本机 Windows OCR 只有 zh-CN 语言包（英文 UI 文本噪声大，`try_create_from_language(en-US)` 返回 None）；**Tesseract 5.4（eng）对文案零误差**（警告弹窗全文、tooltip `'Color Difference: Good (AE=0.0)'` 逐字可读）——落地 `harness/ocr_util.py`（pytesseract + PrintWindow + 3x 放大）。**wx 系统 tooltip 只跟踪真实鼠标输入**（SetCursorPos / WM_MOUSEMOVE 注入不触发，须 SendInput `MOUSEEVENTF_MOVE`）；映射列表色块行是匹配后新增的 93x36 panel（y 797-885）。

**其余 48 条归类**（可测性分层，后续按需扩展）：

| 层 | 记录（飞书 ID） | 说明 |
|---|---|---|
| A 可黑盒（待扩展） | #30 多模型、#31-35 物理耗材数量边界（需换 fixture/改耗材列表）、#37/#40/#41 模板与层高（0.4 喷嘴）、#46/#47 64 色/双拼（需专用 fixture）、#21 映射列表渲染（m3k 已含色度断言） | 交互可驱动 + 外部产物可断言，缺对应 fixture/喷嘴 |
| B 弱覆盖/降级 | #2/#9/#23 hover 文案细节（m3s 已冒烟）、#38 tooltip 对比说明、#45 工艺配置默认值、#39 模板切换确认 | 视觉冒烟或断言弱 |
| C 黑盒不可测 | #11 色域比例/ΔE<1 纯耗材、#42/43/44 兼容性内部判定、#50 空记录 | 内部数值/矩阵，需白盒兜底或接受风险 |

### 主流程（m7，2026-09-08 批次：飞书「测试用例」表 tblLR8zYgwBuggDI）

> 状态口径（2026-09-08 收尾）：✅ = 客机实测 GREEN；🔵 = 脚本已实现并登记，因客机 dwm/PS Direct 通道当日崩坏（PITFALLS §20/§21）尚未取得 GREEN 实证，客机恢复后 `python diag/batch_driver2.py` 或 hv_go 单例即可补验。


来源 = 飞书 wiki 测试用例表（GUI业务 #7–#24 原子 + 主流程-模板 #72–#111 编排），
全量映射（含 MANUAL/OUT-OF-SCOPE 的联机/模型站/更新记录）见 **FEISHU_MAINFLOW.md**。
新增基建：`harness/winutil.real_right_click_screen`（SendInput 右键，开 Plater
原生右键菜单）+ `tests/m7_common.py`（右键菜单行点击 = GetMenuItemRect 精确几何、
嵌套子菜单 via、File 菜单 via 分发、gizmo 槽位 tooltip 扫描、ImGui 字段录入、
gcode/3mf 断言、模板骨架）。工具栏槽位 = 画布内 tooltip 悬停扫描
（y≈84，x≈690–1700，PITCH 22；Move/Rotate 等需先选中模型才启用）。

| 用例 | 飞书记录 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 启动进准备页 + 关闭无残留 | #7+#8 | Prepare 模板 + canvas + tasklist 清零 | m7a_boot_shutdown | ✅ |
| 新建项目清空模型 | #9 | 保存提示出现 → Don't save → 空板 | m7b_new_project | ✅ |
| 导入本地 STL | #11 | Import 子菜单 → 对话框 → Prusa 到板（0.25%+blob） | m7c_import_stl | ✅ |
| 导入非法文件 | #12 | 错误对话框 + app 存活 + 无幻影模型 | m7d_import_corrupt | ✅ |
| 旋转 Z 45° | #15 | Rotation Z=45 OCR → 3mf 矩阵 cos/sin≈0.7071 | m7e_rotate45 | ✅ |
| 等比缩放 120%+还原 | #16 | Scale=120 OCR → 矩阵列范数≈1.2 → 还原读 100 | m7f_scale120 | 🔵 |
| 多模型整理分离 | #17 | Add Primitive 重叠 → Arrange → ≥2 blob 距离>120px | m7g_arrange | ✅ |
| 右键删除模型 | #18 | 对象菜单 Delete → 空板 + 切片拒绝 | m7h_context_delete | ✅ |
| 右键创建新模型 | #19 | 空板菜单 Add Primitive>Cube → 到板 + 切片接受 | m7i_add_primitive | ✅ |
| 切换对象耗材 | #21 | Change Filament → 导出 3mf extruder 属性变更 | m7j_change_filament | 🔵 |
| 擦除塔/Flush 选项 | #24 🟡 | Flush Options 勾选态翻转（gcode 语义人工） | m7k_flush_options | ✅🟡 |
| 模板: 导入+删除 | #72 | arrive → Delete All → 空板 | m7t72 | ✅ |
| 模板: 新建+创建+删除 | #73 | new → cube → Delete All | m7t73 | 🔵 |
| 模板: 变换+切片 | #74 | move/rotate/scale 字段 OCR → slice done | m7t74 | 🔵 |
| 模板: 布局+删一+切片 | #75 | arrange 分离 → 删一留一 → slice+gcode | m7t75 | 🔵 |
| 模板: 分割验证 | #77 | Cut Perform → 2 parts → move/arrange → slice | m7t77 | 🔵 |
| 模板: 朝向+底面 | #78 | orient 视口 diff → Flatten 激活点面 → slice | m7t78 | 🔵 |
| 模板: 拆分对象/零件 | #79 🟡 | split 槽位驱动，can_split 门控如实记录 | m7t79 | ✅🟡 |
| 模板: 层高+支撑 | #80 | VLH + Support Painting 激活+涂抹 → slice | m7t80 | ✅ |
| 模板: 布尔+整理 | #81 🟡 | Add Part 第二体积 → MeshBoolean 激活（UI 证据） | m7t81 | 🔵🟡 |
| 模板: 剪贴+耗材切换 | #82 | cut → Change Filament → slice | m7t82 | 🔵 |
| 模板: 新建+导入+切片 | #83 | new → Import STL → arrive → slice | m7t83 | ✅ |
| 模板: 预设+导入+切片 | #84 🟡 | 打印机 combo 切换；耗材合并=m4d 映射 | m7t84 | 🔵🟡 |
| 模板: 朝向+布尔+整理 | #86 | 组合 78/81 步骤 → slice | m7t86 | 🔵 |
| 模板: 底面+层高+支撑 | #87 | flatten+VLH+support paint → slice | m7t87 | ✅ |
| 模板: 双导入+拆分+缩放+耗材 | #88 | 2×import + split 探测 + scale + filament → slice | m7t88 | 🔵 |
| 模板: 创建+旋转+涂色+切片 | #89 | cube → rotate 45 → Color painting dab → slice | m7t89 | 🔵 |
| 模板: 预设+全局耗材+切片 | #109 🟡 | 打印机切换 + 耗材弹窗枚举 → slice | m7t109 | 🔵🟡 |

🟡 = PARTIAL（known_limitation，断言降级处记录在 FEISHU_MAINFLOW.md 状态注）。
MANUAL/OUT-OF-SCOPE（联机 #25–#38、更新 #65–#67、热重启 #10、主流程-用例设备段、
主流程-模板 #90–108/#110/#111、模型站 #201–#220）：见 FEISHU_MAINFLOW.md。

### 基线用例（m8，2026-09-17 批次：飞书「基线用例」表 tblvh0eGrID9JQ02）

> Base `EDUAbYWcbaL2HOsgFM1cXmBpn5f`（107 条，全部登记时为「未覆盖」）。
> 全量逐条映射（COVERED/PARTIAL/MANUAL/SKIP）见 **FEISHU_BASELINE.md**；
> 本批只新增 6 例，覆盖其中 24 条 GUI 可自动化记录。
> 被测 build 升级到 09-16（新增 Fit 相机钮 / FilamentColorDialog / 净化器
> 模板 / 高流量喷嘴 UI）。基建变化见下方「09-17 基建事实」。

| 用例 | 飞书记录 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| Fit 视图（单选/全选/切盘） | #16/#17/#18/#19 | zoom_to_selection 后色块面积 ≥1.5× 且质心居中；Select All 后 Fit 视角回拉；切盘 + Fit 帧差显著 | m8a_fit_view | ✅ |
| 官方颜色弹窗 | #44/#46/#47/#48 | FilamentColorDialog 出现 + 模态 + 选色卡 OK/Cancel 后 swatch 像素变/不变 + 名称/SKU 文本证据 | m8b_official_color | ✅ |
| 渐变耗材链 | #55/#56/#58 | 槽 combo 切 'PolyLite Dual PLA'（双拼）文本回读 + swatch 色度 + 清场 cube 切片导出 | （m8b 内） | ✅ |
| 高低温混用门 | #111/#112 | 低+低共存放行切片 done；槽切 ABS 后 Slice 置灰、点击被吞 45s 不回归；恢复后切片恢复 | m8c_temp_mix_gate | ✅ |
| 净化器强冷→保温 | #113/#122/#126/#127/#128 | PLA(vitr45) 导出 MODE=1+ALARM_TEMP=45 ✅ → 槽切 ABS 后 MODE=3 ✅ 但 DESIRE=0（弱冷）；保温分支(DESIRE=45)不可达 🔴 | m8d_purifier_gcode | 🟡 |
| 净化器弱冷 | #114/#129 | PETG(vitr70) 导出 MODE=3 DESIRE_TEMP=0 无 ALARM_TEMP DELAY_OFF=180 | m8e_purifier_weakcool | ✅ |
| 高流量喷嘴 | #133/#135/#136 | U1 0.4 工程 Diameter=0.4mm/Flow=Standard；Standard vs High Flow gcode diff；重切字节一致 | m8f_nozzle_flow | ✅ |

✅ = 客机 suite 实测 GREEN。09-20 收尾更新（原 09-19 逐条待办已取代）：
- **suite 终态：m8a/m8b/m8c/m8e/m8f GREEN（5 例），m8d 19/21 PASS（RED）**。
- m8a ✅ · m8e ✅ · m8f ✅（根因=夹具缺 printer_flow_support 致 Flow combo
  被禁用，Plater.cpp:9570；夹具已补 ['standard','high_flow']。#136 逐字节
  一致改为去时间戳+多重集+抖动预算，实测残差 5 行 G1 进给 / 26.7 万行）
- m8b ✅（15/15）。**根因修正：侧栏槽位行 = [chip Button（窗口文本=槽号，
  即 clr_picker 位图按钮，PresetComboBoxes.cpp:909）][combo][空文本"…"Button]
  ——旧 filament_slots 把"…"当 picker，真点后弹的是 Edit/Delete/Merge-with
  菜单 → Edit 开的是预设设置编辑器（750px #32770），官方色盘从未被打开过**。
  真点 chip（前置 SetForegroundWindow，demote 窗口下真点会被激活吞掉）直开
  FilamentColorDialog（380px #32770）：名称/SKU/OK(id5100)/Cancel(id5101)
  均有窗口文本，21 个 30px 色卡（窗口文本 'panel'）——旧"自绘按钮无文本"
  结论系驱动错对话框所致。#48 模态 PASS（真点画布对话框仍在，源码 ShowModal
  一致）→ **撤回 09-19"色盘非模态"结论（伪测量：旧脚本用 wait_popup 的
  SidePopup 谓词检查 #32770）**。#46 选卡→名称即时变（'Mint Lemonade'→
  'Ice Lake'）→OK→chip 像素变 ✓；#47 Cancel 不登记 ✓。
  #55/#56/#58：全序走查（粗扫+wheel 二分定位）证明下拉 65+ 行全部来自
  OrcaFilamentLibrary @System 库（AliZ→Bambu→…→SUNLU→Valment 字母序，
  每次重开滚动复位顶部，wheel 打 popup 顶层可滚、行点击永不滚、VK 键死），
  **无任何 Snapmaker vendor 行，'Snapmaker PLA Rainbow' 不可达**（staged
  目录有该文件但下拉不出）→ 以 'PolyLite Dual PLA'（双拼）替代，全 PASS。
- m8c ✅（#111/#112 全绿）。#112：夹具原样切片 done，gcode used=[1..5]。
  #111：槽2→'Bambu ABS' 后 Slice **置灰、点击被吞、45s 不回归**（帧差 0.00%
  无动画 + late check 分数不回 idle/done——旧探针把置灰态 0.666 分误读成
  "切片启动"，新判据 frame-diff+late-check 区分之），恢复 PLA 后切片复跑 ✓。
  09-19 的"m8c 🔴"判定即此探针伪象 + Change Filament 误导，一并撤回。
- m8d 🟡（19/21）。A 相：槽1→PLA Silk → **MODE=1 DESIRE=42 ALARM=45 强冷 ✓**
  （staged 模板强冷分支无 DELAY_OFF）。B/C 相：Generic ABS / Generic PC →
  MODE=3 DESIRE=0 DELAY=180 = **弱冷**。gcode 回显实证根因：staged 模板
  `{if filament_is_high_temperature[0]}保温{else}{if vitr[0]<=50}强冷{else}
  弱冷` **只看首槽**，且下拉可达预设库全部 high_temp=0（OrcaFilamentLibrary
  28 个 @System 包装 + base 均无高温标记；Snapmaker vendor 的 high=1 预设
  不在下拉）→ **保温分支（DESIRE=45）黑盒不可达，build 落后于源码树新模板
  （chamber_cooling_mode 三分支，GCode.cpp:2726 会按高温标记跳过→保温），
  #113/#126/#127 留证待产品确认**。#122 主断言（槽位变更→MODE 1→3 同步）✓、
  #128 参数完整 ✓、#122-pre/#126 强冷侧证据 ✓。整案 RED 系上述 2 条如实 FAIL。
- 09-19 的"m8c/m8d BLOCKED（Change Filament 语义变更）"判定：语义变更本身
  成立（Change Filament=槽合并，对象级重映射消失），但 m8c/m8d 已改用
  **槽位预设切换**（= #122 步骤原文"在耗材列中将槽位耗材直接修改/替换"的
  黑盒等价原语）重编并基本收口；仅 #111 的黑盒触发路径与 #113/#126/#127 的
  保温分支受该变更/构建滞后影响，留证待确认。

🔵 = 脚本实现完毕，随 m8 burst 在客机 suite 通道取证据中（当日在跑）。
PARTIAL 备注：#59 预览主色=视觉冒烟；#91 TD 值文案、#106 组合遍历、#123
预设管理器改软化温度、#125 多盘全局辅材冲突（用例步骤自含矛盾）、#137
flow 标志参数遍历 —— 处置理由逐条见 FEISHU_BASELINE.md。

#### 09-17 基建事实（新增，编码进 harness 的坑）

1. **'Customized Preset' 模态阻塞夹具加载**：3mf 内嵌预设与 staged vendor
   预设不匹配时（VALIDATE_PRESETS_FILAMENTS_NOT_FOUND，Plater.cpp:12027），
   加载被模态 MessageDialog 阻断 → 模型永不到达（m2 当日复现 RED）。
   ShowModal 返回值被调用方忽略 → WM_CLOSE 即放行。已加入
   `launcher.BLOCKER_TITLES`（customized preset / modified g-code）。
2. **宿主/客机预设源分层**：生效模板以 staged
   `build/src/Release/resources` 为准（SET_PURIFIER_MODE 弱冷
   DELAY_OFF=180），与源码树 resources（600）版本不同 —— 断言以 gcode
   内 `; machine_start_gcode` 回显为准。
3. **侧栏耗材槽为 2 列网格** [chip][combo][picker]×N（combo 自绘、picker
   为 20DIP 位图按钮）；官方色盘仅对 Snapmaker 命名预设开放
   （PresetComboBoxes.cpp:1067）。
4. **rig 恢复链**（PITFALLS §21 后续）：PS Direct 崩坏 → vm_reset.flag
   复位 → 复位后 autologon 可能不触发（quser 无会话、INTERACTIVE 任务
   秒退且日志 0 字节）→ `shutdown /r` 干净重启客机恢复会话。大批量用
   suite 任务（`artifacts/run_m8_suite.ps1` + suite 计划任务）在客机内部
   串行执行，对通道抖动免疫。09-20 实测补充：quser 显示 `Disc`（会话断开）
   即 GUI 劣化起点（真点被吞/PrintWindow 1425/模型不到达）——`shutdown /r`
   不可靠，用 `Restart-Computer -Force`（PS Direct 经 relay）+ 重启后跑
   `setres_1080.py`（Hyper-V 无控制台时分辨率掉 1024x768，PS Direct 里
   Screen.Bounds 恒读 1024x768 属 §18.7 假值，以交互会话内脚本回读为准）。
5. **自绘 combo/popup 操作事实**（09-20）：demote 窗口下真点/弹 popup 前
   必须 `SetForegroundWindow`（真点会被窗口激活吞掉，combo popup 不再弹出）；
   预设 SidePopup ~10 行自绘、无子窗口、行点击即选中并关闭、**重开滚动
   复位顶部**（每次 open+wheel 是绝对采样）；WM_MOUSEWHEEL 打 popup 顶层
   可滚动（已入 `m8_common._wheel`），行点击永不滚、VK 键无效；列表 =
   OrcaFilamentLibrary @System 库按 vendor 字母序 60+ 行。走查用
   `switch_filament_preset` 三阶段：行探测 0-9 → wheel 粗斜坡 →
   二分定位（seek=完整行名，按 vendor 名单调性二分 wheel 档）。
6. **官方色盘**（09-20）：chip Button（文本=槽号）= clr_picker，真点直开
   FilamentColorDialog（380px #32770，PlaceNearFilamentPanel）；名称/SKU/
   OK(5100)/Cancel(5101) 均有窗口文本；色卡 = 21 个 30px 'panel' 窗口；
   模态（ShowModal）。行尾空文本 '…' Button = Edit/Delete/Merge-with 菜单
   → Edit 开的是 750px 预设设置编辑器（params_dialog Popup，非色盘）。


### C 层（黑盒不可测，存量白盒兜底）

instance 矩阵精确值、slice_result_valid 标志、preset 脏状态、切片几何正确性、
纯后台逻辑（Sentry/更新/崩溃恢复）、网络设备栈。

## 关键源码事实（调研沉淀，改 app 时复查）

| 事实 | 出处 | 对策 |
|---|---|---|
| 导出 gcode 可用 = `can_export_gcode()`：模型非空 + `is_slice_result_ready_for_print()` + 不在导出中 | MainFrame.cpp:1602 | **完成检测 = 探测式点击 Export**：对话框出现=完成（确定性信号，优于绿勾模板） |
| Slice 按钮禁用门链：slicing 中 / only_gcode_mode / 已切片 / 不可切 / 混色不兼容 / 冷板 / flow_ratio 零 | MainFrame.cpp:1989 | 空场景/不可切时点击被吞 = 负向断言 |
| Slice/Export 是 topbar 右侧竖排 SideButton（自绘 wxWindowNR，**无子 HWND**） | MainFrame.cpp:1742/1862 | 枚举 + GetWindowText + rect 定位（export_util.topbar_buttons）；label 变长会把 Slice 挤左——**每次重新枚举，禁止缓存坐标** |
| 导出模式切换：点 print 下拉（主按钮左邻空文本按钮）→ SidePopup（独立顶层 'panel'）→ 行含 'Print'/'Export G-code file'（**顺序不保证**，枚举/排序） | MainFrame.cpp:1862 | popup 行点击**不带 root**（popup 在 root 树外，root 解析会 dismiss 假成功） |
| 导出对话框 = 原生 #32770 'Save G-code file as:'；文件名 Edit；**Enter 不触发保存**——WM_COMMAND IDOK 才落盘 | 实测 | export_util.export_gcode：枚举 Edit → 键入全路径 → `SendMessage(dlg, WM_COMMAND, 1, 0)` |
| **SendMessage 点击不转移 Windows 焦点**：wx 字段（Edit）永不进入编辑态 → Ctrl+A/键入/Enter 提交全部失效；AttachThreadInput+SetFocus 在本机返回 0 | 实测 | 字段级参数编辑（P0-1）**黑盒不可行**——断言面由预设切换（P0-2）覆盖；预设 combo 是自绘控件（wx 内部处理点击），无焦点问题 |
| 预设 combo（'0.40 Standard @Snapmaker U1...' wxWindowNR, 屏幕 y~765）点击 → SidePopup 列表（**行自绘无子控件**，28px 行距） | 实测 | 坐标试错选行：每行点击→读 combo 文本确认→重开 popup 试下一行（m3e.switch_preset） |
| 打印预设名：`0.24/0.40/0.32/0.48/0.56 Standard @Snapmaker U1 (0.8 nozzle)`（实测列表序） | wx_gui_business_tests.cpp:337 | combo 黑盒切换（坐标试错） |
| Delete all = Ctrl+D，topbar 顶层菜单下 | wx_gui_business_tests.cpp:588 | **SendMessage 键盘不触发 wx accelerator**（走消息循环）——B 层待办 |
| fixture：mixed_filament_test.3mf（U1 0.8 + 0.40 Standard 嵌入）、snapmates_nonmixed.3mf（7 板，非混色）、Prusa.stl（单对象） | wx_gui_business_tests.cpp:20 | U1 限定直接可用；**Prusa.stl 无嵌入预设 → fallback 不可切片（Slice disabled）→ 弃用作 fixture** |
| 每用例 fresh datadir + fresh launch → 无 preset 脏状态泄漏（白盒的坑黑盒天然免疫） | README 坑 #1 | 默认 fresh |
| 顶栏 File/下拉工具 = wxAuiToolBar 内自绘项（**单 HWND 无子控件**）；`BBLTopbar::OnMouseLeftDown` 用 `FindToolByCurrentPosition()`（**真实光标位置**）决定拖窗还是 Skip 给工具 → 消息点击前必须 `SetCursorPos` 到工具上 | BBLTopbar.cpp:213/618 | topbar_util.click_topbar_tool：SetCursorPos + msg_click_screen，按 x 偏移探测（File~10-40、下拉~70-100 @96dpi）；菜单在 DOWN handler 内 PopupMenu（SendMessage 超时 3s 属预期） |
| 顶栏菜单 = 原生 TrackPopupMenu（#32768）；**其状态机在菜单模态循环里**：SendMessage/PostMessage 的键与点击一律不生效 | 实测（键：无高亮；点击：菜单不关） | 顶层项用 `WM_COMMAND(item_id)` 直发 frame（wx 经 wxCurrentPopupMenu→MSWCommand→FindItem→SendEvent 分发，m3g 验证）；**子菜单行用真实输入 SendInput 点击**（模态循环只认真实输入，m3b 验证） |
| File 菜单子菜单项（Import 3MF）经 WM_COMMAND 可分发；**dropdown 菜单（Edit/View/Help）的子菜单项 WM_COMMAND 不分发**（实测 Preferences 顶层可、Delete All 子层不可，原因未明，不深究） | 实测对比 | 规避：dropdown 子菜单一律真实点击；File 菜单顶层项用 WM_COMMAND（m3g） |
| 菜单行几何：行高 ~20px、**首行起点比 top+2 低 ~12px**（naive 公式偏上 12px）；行点击后菜单关闭=命中可选项 | 实测（m3b 探针 y=300 命中 Delete All） | topbar_util.submenu_row_candidates：以 base 为心 ±6px 步进探针，结合"菜单关闭+模型消失"判定 |
| SendInput 真实输入本机**可用**（2/2 投递，README 环境矩阵已过时）——但 WebView2 透明宿主（Chrome_RenderWidgetHostHWND 全屏）**吞掉 app 窗口区域的真实点击**；模态菜单在 z-top 不受影响 | 实测 2026-08-29 | 真实点击只用于菜单行（顶层窗口）；app 区交互仍走消息注入（deepest_child_at 穿透） |
| 字段提交链：Orca 设置字段（Field.cpp TextCtrl）只在 **Enter（wxEVT_TEXT_ENTER）或失焦（wxEVT_KILL_FOCUS）** 时 propagate_value；WM_SETTEXT 只改文本不提交 | Field.cpp:782/814 | **WM_SETTEXT + SendMessage(WM_KILLFOCUS)** 驱动真实提交链（m3d GREEN）——字段级参数编辑黑盒可行 |
| GLCanvas3D::on_char 自带 Ctrl+D→EVT_GLTOOLBAR_DELETE_ALL、WXK_DELETE→DELETE（画布级绑定，不走 wx accelerator）；但需画布持有**真实焦点**且修饰键来自线程 GetKeyState（外部不可设） | GLCanvas3D.cpp:3344/3368 | 画布路径仅备选；删除断言面由菜单路径覆盖 |
| **app 加载 3mf 会改写源文件**：`Metadata/model_settings.config` 的 `identify_id` 被重写（90→78 实测）——fixture 用后可能变脏 | 实测 2026-08-29（m3g 运行后 fixture 35543→35544B） | 提交前 `git status` 检查 tests/data/test_3mf/，脏 fixture 恢复 HEAD（app 副作用，非用户改动） |

## 导出原语（Tier 0）

```
export_gcode(session, out_path):
  1. 等 Slice done（绿勾模板，粗观察）
  2. 探测式点 Export 按钮（m_print_btn 区域）→ 等模态保存对话框出现（EnumWindows 找同进程新顶层窗口）
  3. 对话框内键入完整路径（WM_CHAR/msg_text）→ 回车（WM_KEYDOWN VK_RETURN）
  4. 等文件落盘 → 校验非空
  5. 若覆盖确认对话框（同名文件）→ 回车确认
```