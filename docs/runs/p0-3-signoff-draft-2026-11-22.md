# P0-3 旧判据逐项签核表 · 初稿（DRAFT — 供宿主审查，非最终签核）

> **DRAFT 水印**：本表为 2026-11-22 签核初稿。逐 ID 给出签核**建议**，最终判定以宿主审查为准。
> 对应台账任务：`docs/V3_MIGRATION_LEDGER.md` 后续任务表 P0「独立重算 89 条迁移覆盖」。
>
> 输入源（只读引用，未改动）：
> 1. `BLACKBOX_CASES.md`（89 条判定标准原文，唯一权威）；
> 2. `docs/V3_MIGRATION_LEDGER.md`（六族状态表 + 「历史证据指针」run ID 清单）；
> 3. `docs/runs/` 各运行记录（源 SHA 与证据位置）。
>
> 分支说明：任务指定的 `origin/codex/glm-flash-expansion-20261121-0217` 在 origin 上不存在
> （远端仅 `origin/main`），该批次内容已并入当前检出；台账与 glm-flash 运行记录均以工作树版本为准。
>
> 落盘状态：提交在本机 `codex/mac-author` 分支。本机无 GitHub 推送凭据（无 gh CLI、keychain 无
> github.com 条目、无对 GitHub 的有效 SSH 公钥，与 `mac-author-port-2026-11-22.md` 记载一致），
> **push 阻塞、如实记录**；待凭据后 `git push origin codex/mac-author` 即可。

## 口径

- **判据源**：旧必验断言优先摘自 `BLACKBOX_CASES.md` 对应表行。m5 族（m5a–m5h）、
  `m8g_flow_single`、`m8x_123/125/137` 在 BLACKBOX_CASES.md 无表行，按台账纪律
  （「旧业务判据以 BLACKBOX_CASES.md 与各用例脚本头为准」）取自脚本头，行内标注（脚本头）。
- **证据类型**：沿用台账状态词汇——`SHADOW`（本批/复验独立通过）、`replay`（无模型回放通过）、
  `hist`（历史独立通过，旧源、需本 HEAD 复验转正）、`scripted-probe`（回放探针/部分链）、
  `adapted`（已登记映射未跑）、`gap-cap/gap-neg`（缺 UI 能力/负例拒绝合同）、`blocked`、`off`、`n/a`。
- **签核四档**：
  - **完整覆盖** = 旧必验断言判据面在 V3 有等价或更强证据（SHADOW/replay/hist·隐含）；
  - **部分覆盖** = V3 证据只覆盖旧断言子面，其余判据未证；
  - **未覆盖** = gap / blocked / adapted 未跑——**无 V3 通过证据，不因登记态写成已覆盖**；
  - **不适用** = off / 路线差异 / 降级保留（n/a）。
- **run ID**：优先取台账「历史证据指针」小节；该节未列时，从 `docs/runs/` 运行记录补（标注记录名）。
- **源 SHA**：运行记录可查的填；六源区间 `bf108f7..0b4b919` 指 11-21 script 轨道 31 场景的六个源提交，
  `a501339` 为 11-22 P0-2 单源整套复验（31/31 SHADOW）。
- 「例 ×××」表示该判据隐含于每个 run 的收据，所引为代表性 run，非唯一证据。

---

## F1 启动/页签/工程基本操作（9 行）

| ID | 旧必验断言（BLACKBOX_CASES.md） | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m0_boot_check | 主窗口出现、可见、尺寸>0（m0 表行） | 每 run 准备段 ready 收据：hwnd/pid/窗口矩形 + teardown 清理 | hist·隐含（每个 SHADOW run 均含） | 例 d7299035（收据含窗口链） | fcffb0f2 | **完整覆盖**——ready 收据矩形覆盖出现/可见/尺寸>0，判据等价；31/31 复验兜底 |
| m0_anchor_health | 锚点模板健康自检（harness 基建；BLACKBOX 无表行，`tests/engine/m0_anchor_health.py`） | 模板层属旧视觉路线；UIA 路线无模板依赖 | n/a（路线差异） | — | — | **不适用**——模板锚点自检在 UIA 路线无对应物，登记不改 |
| m1_minimal_loop | Prepare/Preview tab 选中色 teal(0,150,136) 翻转（m1 表行） | tab=自绘；页签 UIA 切换合同未登记 | gap-cap | — | — | **未覆盖**——页签自绘 + UIA 切换合同双缺，无 V3 证据 |
| m1b_maa | MaaFw 引擎实验（登记保留） | 无原生映射（引擎路线已弃） | off（禁用） | — | — | **不适用**——引擎实验已判死，保留分母不计启用 |
| m7a_boot_shutdown | Prepare 模板 + canvas + tasklist 清零（#7/#8） | 原生 run 启动 + 停输 + 自然退出即全链 | hist·隐含 | 例 d74f73f4（自然退出 + 清理确认） | edcaa13 | **完整覆盖**——启动/退出/进程清零由每 run 启动链 + 清理回据覆盖 |
| m7b_new_project | 保存提示出现 → Don't save → 空板（#9） | fixture_cold（fresh profile 工程） | adapted（映射场景已跑，旧分支判据未入） | 72cfda6b（fixture_cold SHADOW 11-21） | bf108f7..0b4b919；a501339 复验 | **部分覆盖**——fresh 工程冷启链已证；Don't save 提示分支未入 V3 判据 |
| m7t73 | new → cube → Delete All（主流程模板 #73） | fixture_cold 同上 | adapted | 72cfda6b | 同上 | **部分覆盖**——fresh 工程链已证；新建后 Delete All 清场断言未入 |
| m7t83 | new → Import STL → arrive → slice（#83） | bound_model_move（STL 输入）准备链 | SHADOW（hist 4 模型试点 11-19）+ 11-21 复验 | 9def6142（bound_model_move Prusa.stl SHADOW） | bf108f7..0b4b919；a501339 | **完整覆盖**——STL 导入→U1 工程→平移→保存重开全链 SHADOW，强于到达+切片断言 |
| m3i_view_menu | View 子菜单 Top/Front 真实点击，两次 viewport diff>10 | 菜单栏 UIA Invoke + 视角判据未登记 | gap-cap | — | — | **未覆盖**——视角判据与菜单合同双缺 |

## F2 导入、预设、工艺与切片（16 行）

| ID | 旧必验断言 | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m2_slice_chain | done 绿勾模板 + 色度占比≥2×基线（m2 表行） | 每 run 独立重开 + 重切段（层数/参数/G-code oracle） | hist·隐含（31/31 script 复验） | 例 d7299035（独立重开切出 68 层） | fcffb0f2 | **完整覆盖**——独立重切 oracle 强于绿勾模板 + 色度断言 |
| m7c_import_stl | Import 子菜单 → 对话框 → Prusa 到板（0.25%+blob）（#11） | bound_model_move（STL 输入） | SHADOW + 复验 | 9def6142 | bf108f7..0b4b919；a501339 | **部分覆盖**——模型到达/几何保持已证更强；Import 菜单 + 文件对话框路径未证 |
| m7d_import_corrupt | 错误对话框 + app 存活 + 无幻影模型（#12） | 错误弹窗读回合同未登记 | gap-neg | — | — | **未覆盖**——负例拒绝合同缺口（候选清单 #5） |
| m3c_corrupt_3mf | 错误对话框出现 + app 存活 + 好项目二次加载模型到达 | 同上 | gap-neg | — | — | **未覆盖**——错误弹窗读回未登记 |
| m3e_preset_switch | combo 切 0.40↔0.24 @U1 + 重切 + 导出 + `; layer_height` 跟随 | 预设下拉自绘 + 预设名读回未登记 | gap-cap | — | — | **未覆盖**——预设读回合同缺口（候选 #1，解锁 6+ 条） |
| m5a_preset_cycle | 预设级主流程：切 '0.24 Standard' 后 gcode 头跟随（脚本头） | 同上 | gap-cap | — | — | **未覆盖**——依赖预设切换读回合同 |
| m5b_quality_params | Wall loops 2→4 + Seam position 改 → 双 gcode echo + app 存活（脚本头） | uia_hybrid_layer / uia_replay_layer | SHADOW + replay + 复验 | f65ba49e（壁环 goal-only）/ 4ab5b246（replay_layer）/ 42a45554（enums 复验） | 0169551f；bf108f7..0b4b919 | **完整覆盖**——两参数均有 SHADOW + 无模型回放，gcode echo 由重切 oracle 等价替代 |
| m5c_strength_infill | sparse infill density↑ + pattern 改 → echo + 填充量变化（脚本头） | uia_hybrid_layer_strength / 壁环数 | SHADOW（Strength 页编辑链）；infill 目标未过 | 4aab2728（底层数）/ a47e895f（手写基线）；pilot_infill 0b338e3f NON_GREEN | 077ea7a7；bf108f7..0b4b919；b6b15eb5 | **部分覆盖**——Strength 页编辑 + 保存重开已证；infill 密度/图案目标两轮未过（0b338e3f/7a6170d7） |
| m5d_support_enable | Enable support 勾选 → `; enable_support` echo + app 存活（脚本头） | Support 页 UIA 合同未登记 | gap-cap | — | — | **未覆盖**——Support 页合同缺口 |
| m5e_combo_params | 跨 3 页 3 参数同切一次 → 多 gcode echo（脚本头） | pair_*（7/7）+ cfg_value 01/04/06/07 | replay-ok + SHADOW（Quality 域） | 批 c32661e9（pair 7/7）；2a6b9643/c96a3498/a38b163f/d13fa858（cfg） | 810e6fd；eaa0d4bf / 755dff6d | **部分覆盖**——组合机制 + Quality 域已证；Support/Strength 参数未入组合域 |
| m5f_negative_params | 越界层高 → MessageDialog 原文 + 恢复（脚本头） | 负参数拒绝读回未登记 | gap-neg | — | — | **未覆盖**——负例合同缺口 |
| m5g_preset_manage | 用户预设保存 → 重启存活 → 再选 → 删除 → 干净回落（脚本头） | 预设名保存被 oracle 拒（v3-project 第三批） | blocked（预设名判据待修） | d07534e7（批3 业务拒）/ 26a5db13（批4 修复后首槽 SHADOW） | 1432fcef；6cf2b1bf | **未覆盖**——用户预设管理链未跑；预设名判据批4 已修但 m5g 判据未重登 |
| m5h_ironing_combos | Ironing Type + Seam Position 双 combo → 双 echo（脚本头） | uia_quality_enums | SHADOW + replay + 复验 | a4f5926d（带提示）/ dc56b293（回放）/ 42a45554（11-21 复验） | 9c99497；92320ff；bf108f7..0b4b919 | **完整覆盖**——双 enum 读回 + 独立重开验出 topmost/random，判据等价 |
| m7t72 | arrive → Delete All → 空板（模板 #72） | bound_model_move | adapted（映射场景已跑） | 9def6142 | bf108f7..0b4b919；a501339 | **部分覆盖**——模型到达已证；Delete All 清场未入判据 |
| m7t74 | move/rotate/scale 字段 OCR → slice done（模板 #74） | uia_replay_layer 链 | replay-ok + 复验 | 4ab5b246（层高链）；move 域 50a7fa3a / 9def6142 | bf108f7..0b4b919；a501339 | **部分覆盖**——切片调整 + 保存重开链已证；rotate/scale 字段判据未登记 |
| m8x_137_flow_param_tabs | Standard/High Flow 双 tab；带标志参数独立/不带标志同步；工艺侧 Speed tab（脚本头） | uia_process_combo（工艺页签组合） | SHADOW（映射场景已跑，flow 判据未入） | 99616c25（手写）/ 2248e3b7（replay_process） | bf108f7..0b4b919；a501339 | **部分覆盖**——工艺页签导航已证；流量双档独立/同步判据未登记（台账已标「部分覆盖候选」） |

## F3 保存重开和导出（2 行）

| ID | 旧必验断言 | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m3g_export_3mf | zip 有效 + 3D/3dmodel.model 存在 + `printer_settings_id` 保留 + 二次加载模型到达 | v3_project 批（编辑→保存→重开→持久化→重切整链） | blocked（第四批待验） | 26a5db13（批4 首槽完整 SHADOW）；批1-3 59281fcb/f655154d/d07534e7 NON_GREEN | 6cf2b1bf；930d09da / 22fe3321 / 1432fcef | **部分覆盖**——批4 首槽完整链 SHADOW 但整批未完（槽2 外部中断）；预设名判据已修待整批复验 |
| m3d_param_reslice | WM_SETTEXT+KILLFOCUS 提交链 → 重切 → `; layer_height` 0.4→0.2 + 字节 diff | 每 run A/B 重切 + 冻结 3MF/G-code SHA | hist·隐含（31/31） | 例 4ab5b246（层高 0.40→0.24 A/B 重切链） | bf108f7..0b4b919；a501339 | **完整覆盖**——A/B 重切 + 冻结 SHA 对比强于字节 diff；提交链由 UIA 属性写入等价 |

## F4 多盘、对象、变换与撤销（23 行）

| ID | 旧必验断言 | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m6a_transform_verify | 导出 3mf `<item transform>` 平移 X 精确=60.0、Y/Z 不变 | uia_hybrid_canvas（X+10）/ uia_replay_canvas | SHADOW + replay + 复验 | 52a21e14（画布门禁）/ 8c8b135f（goal-only）/ 851d655d（11-21 回放） | 6b3bfbae；0169551f；bf108f7..0b4b919 | **完整覆盖**——冻结 3MF 证全局 X 平移精确 + Y/Z/形状保持，明文矩阵↔世界三角面判据等价 |
| m7f_scale120 | Scale=120 OCR → 矩阵列范数≈1.2 → 还原读 100（#16） | general_scale_quality/others | adapted（两槽 NON_GREEN 待复验） | —（11-18 两槽 NON_GREEN，记录 zcode-generalization-2026-11-18） | — | **未覆盖**——缩放槽裁图/检查器误拒两轮未过，修订待复验 |
| m7e_rotate45 | Rotation Z=45 OCR → 3mf 矩阵 cos/sin≈0.7071（#15） | 画布数值 rotate 字段未登记 | gap-cap | — | — | **未覆盖**——CANVAS_REPLACE 合同扩展候选 #8 |
| m3h_undo_redo | Undo 后模型复现（色度≥1% 双轮）→ Redo 再度清场（<0.4%） | Ctrl+Z 未开放、撤销语义判据未定义 | blocked（撤销合同） | — | — | **未覆盖**——撤销合同缺口（候选 #2：保存前后 3MF config 快照 diff） |
| m3f_multi_plate | Slice all 模式选中 + done 态（P0-3） | 多盘选择/盘切片 UIA 未登记 | gap-cap | — | — | **未覆盖**——每盘 gcode 判据未登记（候选 #4） |
| m3b_delete_scene | Delete All → 色度回落空床（<0.4%）+ 空场切片拒绝 | 右键菜单/删除未登记 | gap-cap | — | — | **未覆盖**——菜单合同缺口（候选 #3） |
| m7h_context_delete | 对象菜单 Delete → 空板 + 切片拒绝（#18） | 右键菜单合同未登记 | gap-cap | — | — | **未覆盖**——同上 |
| m7g_arrange | Add Primitive 重叠 → Arrange → ≥2 blob 距离>120px（#17） | 工具栏按钮 Invoke 未登记 | gap-cap | — | — | **未覆盖**——工具栏按钮合同缺口 |
| m7j_change_filament | Change Filament → 导出 3mf extruder 属性变更（#21） | pilot_material（逻辑材料槽 2） | SHADOW | d301c03a（逻辑 slot2/对象 T1/实际 68 层） | b6b15eb5 | **完整覆盖**——实际 T1 对象挤出强于 3mf 属性断言 |
| m7i_add_primitive | 空板菜单 Add Primitive>Cube → 到板 + 切片接受（#19） | 原始体对话框未登记 | gap-cap | — | — | **未覆盖**——原始体对话框合同缺口 |
| m7t75 | arrange 分离 → 删一留一 → slice+gcode（模板 #75） | 多实例布局未登记 | gap-cap（依赖多实例选择合同） | — | — | **未覆盖**——依赖多实例选择合同 |
| m7t77 | Cut Perform → 2 parts → move/arrange → slice（模板 #77） | 分割工具未登记 | gap-cap | — | — | **未覆盖**——分割工具合同缺口 |
| m7t89 | cube → rotate45 → Color painting dab → slice（模板 #89） | 旋转+涂色组合 | gap-cap（依赖 rotate 与涂色画布） | — | — | **未覆盖**——rotate 与涂色两项依赖均缺 |
| m7t78 | orient 视口 diff → Flatten 激活点面 → slice（模板 #78） | 朝向工具未登记 | gap-cap | — | — | **未覆盖**——朝向工具合同缺口 |
| m7t79 | split 槽位驱动，can_split 门控如实（模板 #79） | 同分割族 | gap-cap | — | — | **未覆盖**——同分割族缺口 |
| m7t80 | VLH + Support Painting 激活+涂抹 → slice（模板 #80） | 画布绘制+可变层高未登记 | gap-cap | — | — | **未覆盖**——画布绘制合同缺口 |
| m7t81 | Add Part 第二体积 → MeshBoolean 激活（UI 证据）（模板 #81） | 布尔工具未登记 | gap-cap | — | — | **未覆盖**——布尔工具合同缺口 |
| m7t82 | cut → Change Filament → slice（模板 #82） | 材料槽+剪贴组合 | gap-cap | — | — | **未覆盖**——材料槽链 slot2 0/2 未闭环 + 剪贴缺 |
| m7t84 | 打印机 combo 切换 + 耗材合并=m4d 映射（模板 #84） | 材料槽族扩展 | gap-cap（依赖预设切换） | — | — | **未覆盖**——依赖预设切换合同 |
| m7t86 | 朝向+布尔+整理组合 → slice（模板 #86） | 多原子组合 | gap-cap（依赖单项） | — | — | **未覆盖**——依赖单项合同均缺 |
| m7t87 | flatten+VLH+support paint → slice（模板 #87） | 同上 | gap-cap | — | — | **未覆盖**——依赖单项合同均缺 |
| m7t88 | 2×import + split 探测 + scale + filament → slice（模板 #88） | 同上 | gap-cap | — | — | **未覆盖**——依赖单项合同均缺 |
| m7t109 | 打印机切换 + 耗材弹窗枚举 → slice（模板 #109） | 同上 | gap-cap | — | — | **未覆盖**——依赖预设切换 + 材料槽合同 |

> 注：`uia_move_layer`（平移+层高组合，e251f0f2 SHADOW 源 b9266e1 + 回放 b1d0ecff 源 19b9b4d + 复验 c4e6f4cc）
> 与 `uia_save_as`（d7299035 + 复验 112e643a）、`overwrite`、safety 三件（批 caff0452，源 29f567e）、
> fixture_cold/shared 为**登记册外场景行**，不占 89 分母，其证据已在上表相关 ID 行内引用。

## F5 混色、渐变、多材料与高流量（32 行）

| ID | 旧必验断言 | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m3t_mixing_add_ratio | Add Mix 默认 Ratio/2 行 50/50/推荐卡；跨类红幅+OK 禁；滑块 10-90 钳制+90% 橙幅 | uia_mix_recipes / uia_replay_mix | scripted-probe（回放探针 + 复验） | c0b2a5c3（手写）/ eab535b0（引导 AI）/ cb413cf7（11-21 复验） | 5518067；69c90f1；bf108f7..0b4b919 | **部分覆盖**——Ratio 50/50 登记+保存重开已证；红幅/OK 禁/滑块钳制负例未证 |
| m3u_mixing_ratio_flow | 徽章→50/50+预览重绘；OK 登记 'F2 50%+F3 50%'；Edit 保参数；75/25 更新；取消无残留 | 同上 | scripted-probe | 同上（u2 Ratio 保存重开保留） | 同上 | **部分覆盖**——登记+持久化已证；Edit/75/25 更新/取消分支未证 |
| m3v_mixing_cycle_input | 默认 '12'；512 截断；'623'/'2a3' 红幅+OK 禁（语法 [nn]） | 循环输入校验未入场景 | gap（负例） | — | — | **未覆盖**——Cycle 输入校验负例无任何 V3 证据 |
| m3w_mixing_cycle_flow | '23' 登记；'232'→67/33 更新；Match↔Cycle 保图案；切 Ratio 重登记 | Cycle 模式未入场景 | gap | — | — | **未覆盖**——场景只证 Ratio+Gradient，Cycle 模式未跑 |
| m3j_mixing_entry | 有颜色模型→弹窗出现；combo 默认 'Auto'；Auto Start→喷嘴警告（'Got it' 可关） | mix recipes 含入口段 | scripted-probe（部分） | eab535b0（两次 UIA Invoke 打开 Add Mix） | 69c90f1 | **部分覆盖**——入口打开已证；默认 Auto+喷嘴警告断言未证 |
| m3k_mixing_match | Manual 匹配 → 映射列表色度渲染（0→~0.12 双轮）→ Confirm 关闭弹窗 | 台账称「mix recipes 含 match 段」 | gap（映射声明待核对） | —（运行记录只见 Ratio+Gradient 两段） | — | **未覆盖**——Match 执行链无运行证据；台账「match 段」声明与记录不符，待核对 |
| m3l_mixing_delta | hover 色块 → ΔE tooltip OCR（'Good (AE=0.0)' 级别+数值） | tooltip 通道 V3 无 | gap | — | — | **未覆盖**——tooltip 观测通道未登记 |
| m3r_mixing_progress | 100ms 密集轮询抓进度条 + 'Stop Matching'（瞬态）；完成后 Stop 隐藏 | 匹配中状态未入场景 | gap | — | — | **未覆盖**——瞬态进度判据无证据 |
| m3m_mixing_filaments | 4 耗材 '+' 禁用；4→3→2 '−' 禁用（边界）；色域警告 banner '0%–70%' | 材料槽合同可部分复用；slot2 端到端未通过 | adapted（部分） | slot2 复验 26739846（0/2 NON_GREEN 终态） | 33869a6 | **未覆盖**——耗材增删边界判据未登记；slot2 弹窗链未闭环（四败归一） |
| m4d_mixing_filops | trash 静默删除；引用中删除→Warning 二次确认原文→级联；Options 合并 | 同上 | adapted（部分） | — | — | **未覆盖**——物理耗材删除/合并判据无证据 |
| m3n_mixing_cancel | Cancel→确认弹窗原文 'Are you sure…discard'→Discard 不保存 | 业务取消弹窗读回未登记 | gap-neg | — | — | **未覆盖**——取消确认负例合同缺口 |
| m3o_mixing_nomodel | 清场后入口 → 'No model detected' 原文 + 'Got it' 可关 + 弹窗不开 | 入口门禁负例未登记 | gap-neg | — | — | **未覆盖**——无模型门禁负例缺口 |
| m3p_mixing_persist | 匹配→Confirm→Save→重载：模型到达（5.9%>2.1%）+ 面板保留 + 弹窗可重开 | V3_PLAN §8 组共享 fixture（保存重开已设计） | adapted（台账未跑；11-19 已有链） | 9137fdbd（引导）/ 7fbf949c（回放）：新 profile 重切保留 u2/u3/槽6 | 5518067；740f407 | **部分覆盖**——持久化+重开+重切已证（建议台账 adapted→部分）；面板可视保留/弹窗重开断言未证 |
| m3q_mixing_view | 默认 'Isometric'+盘 '01'；View popup 切 'Top-Front' → 视图区色度变化 | 视图族 | gap-cap | — | — | **未覆盖**——视图切换合同缺口（同 m3i 族） |
| m3s_mixing_hover | 增删按钮 hover → tooltip 出现+OCR 非空（降级冒烟） | 无原生映射（tooltip 通道不迁移） | n/a（降级保留） | — | — | **不适用**——hover tooltip 降级用例，迁移不改变降级态 |
| m3x_mixing_match | Match 卡默认 blend+15%+2:1:1；GGGGGG 红幅+OK 禁；FF5733→6s 重算；Min Mix 15→3；取色器 | mix recipes | scripted-probe（部分） | —（Match 卡未入场景） | — | **未覆盖**——Match 卡交互（重算/滑块/取色器）无证据 |
| m3y_mixing_gradient | 恒 2 行+Mix Effect+交换钮；默认 F3->F2 登记；交换→F2->F3；重开保 Gradient | mix recipes 渐变段 | scripted-probe（部分） | 7fbf949c（u3 Gradient 80→20 保存重开保留） | 740f407 | **部分覆盖**——渐变登记+持久化已证；交换钮/预览重绘未证 |
| m3z_mixing_compat | 11 耗材 10 对：同类放行（PLA/PETG）、PLA+PETG/ABS/TPU/BVOH 阻断+OK 禁 | 门禁与兼容负例 | gap-neg | — | — | **未覆盖**——兼容矩阵负例未登记 |
| m4a_mixing_gates | 无方案：1 耗材面板隐藏+提示原文+弹窗不开；加到 6→钳制 4 | 入口门禁负例 | gap-neg | — | — | **未覆盖**——耗材数门禁负例缺口 |
| m4f_mixing_cap64 | 64 色：混色添加+耗材添加均禁用；删 1→恢复 | 上限负例 | gap-neg | — | — | **未覆盖**——64 上限负例缺口 |
| m4j_mixing_samecolor | 同色对无阻断可登记；'12345'→Excessive 橙幅不阻止 | 同色+预警负例 | gap-neg | — | — | **未覆盖**——同色/预警负例缺口 |
| m4b_batch_manual | Manual 默认 4 行；Auto 卡 4 槽；行选择→匹配→Confirm→耗材 5→3 | 面板 UIA 未登记 | gap-cap | — | — | **未覆盖**——批量弹窗面板合同缺口 |
| m4c_mixing_panel | 物理行材料名+种子条目+Options 按钮；Delete 清空→空态+添加可用 | 面板 UIA 未登记 | gap-cap | — | — | **未覆盖**——侧栏面板合同缺口 |
| m4e_mixing_paint | 选中模型→'Color painting' tooltip→激活→调色板 6 色块（PARTIAL，逐块涂色留人工） | 画布绘制未登记 | n/a→gap-cap（保留降级） | — | — | **不适用**——PARTIAL 降级保留；V3 涂色合同未登记不改变降级态 |
| m4g_mixing_sublayer | Advanced→'Subdivide Mix Layer'；0.4mm 无警告；0.1mm→'Configuration Conflict' 原文 | cfg_value 族可扩 | adapted（候选） | — | — | **未覆盖**——细分层高 dithering 判据未入 cfg 域 |
| m4h_mixing_templates | 0.4 变体 '0.10mm Color Mixing' 存在可选；0.8 无模板+Auto 门禁原文 | 预设族 | gap-cap（依赖预设） | — | — | **未覆盖**——依赖预设切换合同 |
| m4i_mixing_slice | 比例+渐变两方案 → 切片完成 → gcode 1.36MB 含 5 种换刀标记 | mix+slice 组合 | adapted（候选；11-19 已有重切产物） | 7fbf949c（冻结 3MF + 重切 G-code SHA） | 740f407 | **部分覆盖**——混色工程重切 G-code 已有产物证据；换刀标记数/体积判据未核 |
| m8b_official_color | FilamentColorDialog 出现+模态；选色卡 OK/Cancel 后 swatch 变/不变；OCR SKU（#44/46/47/48） | 耗材颜色 UIA 未登记 | gap-cap | — | — | **未覆盖**——官方色盘合同缺口（候选 #6） |
| m8c_temp_mix_gate | 低+低共存放行切片 done；槽切 ABS 后 Slice 拒绝+横幅；恢复后切片恢复（#111/112） | 偏好开关+切片门禁（类 m8x_125） | gap-cap | — | — | **未覆盖**——温混门禁+偏好合同缺口 |
| m8x_125_aux_mix_pref | 偏好关→按钮置灰+红条+切片不启动；偏好开→风险确认→切片完成→还原偏好（#125，脚本头） | V3 待补涂色、偏好、警告与风险确认合同 | gap-cap | — | — | **未覆盖**——涂色/偏好/警告/风险确认四项合同全缺 |
| m8f_nozzle_flow | Diameter=0.4mm/Flow=Standard；Standard vs High Flow gcode diff；重切字节一致（#133/135/136） | 喷嘴/流量组合框未登记 | gap-cap | — | — | **未覆盖**——流量组合框合同缺口（候选 #6） |
| m8g_flow_single | 同值流量包两模式各切一份，除流量模式字段外无差异（#136，脚本头） | 同上 | gap-cap | — | — | **未覆盖**——依赖同 m8f 合同 |

## F6 性能及其他专项（7 行）

| ID | 旧必验断言 | V3 映射判据（台账） | 证据类型 | run ID | 源 SHA | 签核建议 |
|---|---|---|---|---|---|---|
| m2_perf_showcase | 大工程切片+录像演示（显式 perf 专用） | 独立 perf 轨道 | off（禁用） | — | — | **不适用**——perf 批次另计，不入 GUI 判据签核 |
| m8a_fit_view | Fit 后色块面积≥1.5×且质心居中；Select All 后回拉；切盘+Fit 帧差（#16-19） | 视图合同未登记 | gap-cap | — | — | **未覆盖**——Fit 视图判据缺口 |
| m8d_purifier_gcode | PLA(vitr45)→MODE=1+ALARM_TEMP=45；ABS/PC(vitr>50)→MODE=3 保温分支（#113/122/126-128） | cfg_value 域不含温度/净化器参数，需扩域 | gap-cap（cfg 域扩展） | — | — | **未覆盖**——正例判据可从 m8x_123 旧脚本移植，域未扩 |
| m8e_purifier_weakcool | PETG(vitr70)→MODE=3 DESIRE_TEMP=0 无 ALARM_TEMP DELAY_OFF=180（#114/129） | 同上 | gap-cap | — | — | **未覆盖**——同上 |
| m8x_123 | vitr=45→强冷 MODE=1+ALARM 45；vitr=80→保温 MODE=3；A≠B gcode 顶盖更新（#123，脚本头） | 同上 | gap-cap | — | — | **未覆盖**——分支翻转判据已有旧脚本实现待移植入 cfg 域 |
| m7k_flush_options | Flush Options 勾选态翻转（gcode 语义人工，PARTIAL 保留） | 冲洗面板读回未登记 | gap-cap（PARTIAL 保留） | — | — | **未覆盖**——PARTIAL 降级保留；冲洗面板读回合同缺口 |
| m3a_empty_slice | 点 Slice 不启动任务 + 按钮保持 idle + Preview 无色度 | 负例门禁 | gap-neg | — | — | **未覆盖**——按钮门禁状态读回负例缺口（候选 #7） |

---

## 统计汇总

| 族 | 行数 | 完整覆盖 | 部分覆盖 | 未覆盖 | 不适用 |
|---|---:|---:|---:|---:|---:|
| F1 启动/页签/工程 | 9 | 3（m0/m7a/m7t83） | 2（m7b/m7t73） | 2（m1/m3i） | 2（m0_anchor/m1b） |
| F2 导入/预设/工艺/切片 | 16 | 3（m2/m5b/m5h） | 6（m7c/m5c/m5e/m7t72/m7t74/m8x_137） | 7（m7d/m3c/m3e/m5a/m5d/m5f/m5g） | 0 |
| F3 保存重开导出 | 2 | 1（m3d） | 1（m3g） | 0 | 0 |
| F4 多盘/对象/变换/撤销 | 23 | 2（m6a/m7j） | 0 | 21 | 0 |
| F5 混色/渐变/多材料/高流量 | 32 | 0 | 6（m3j/m3t/m3u/m3p/m3y/m4i） | 24 | 2（m3s/m4e） |
| F6 性能与专项 | 7 | 0 | 0 | 6 | 1（m2_perf） |
| **合计** | **89** | **9** | **15** | **60** | **5** |

与台账「本批分族迁移汇总」的对照：台账 21 项证据候选签核后为完整 7 + 部分 8（m5c/m3g/m3p/m4i/m7b/m7t73
等候选外行依运行记录补证升为部分）；候选内的 m3k/m3v/m3w/m3x 四条经逐案核对无对应运行证据，降为未覆盖。
所有 gap/blocked/adapted 未跑行一律未覆盖，**未把 gap-cap 写成已覆盖**。

## 无法评估清单

**0 条**——89 个 ID 均已给出签核建议。两点判据源/映射核对说明（不构成无法评估，供宿主复核）：

1. **m5 族与 m8g/m8x 判据源**：BLACKBOX_CASES.md 无 m5a-m5h、m8g、m8x_123/125/137 表行，
   旧断言取自脚本头（台账纪律明文允许）。补全路径：如宿主要求全部以 BLACKBOX_CASES.md 为源，
   需先把这些脚本头判据回登 BLACKBOX_CASES.md（属文档增补，非本初稿范围）。
2. **两条台账映射声明缺记录指针**：① F1 m7t83「4 模型试点 11-19」未在 docs/runs/ 找到独立记录文件
   （签核改以 11-21 复验 9def6142 + 11-22 单源 a501339 为据）；② F5 m3k「mix recipes 含 match 段」
   与 zcode-compound-replay/compound-expansion 记录（仅 Ratio+Gradient）不符，本稿按未覆盖处理。
   补全路径：向台账补登这两处的 run 出处，或修正映射列。

## 自检（行数与非空字段）

- 六族行数：F1 9 / F2 16 / F3 2 / F4 23 / F5 32 / F6 7，合计 **89**（与台账冻结分母一致）。
- 每行非空字段 ≥5：ID、旧必验断言、V3 映射判据、证据类型、签核建议 五列全行非空
  （run ID/源 SHA 为「—」的行仍满足 5 列非空）。
- 红线自查：未改动 BLACKBOX_CASES.md（只读引用）；全文 DRAFT 标注；gap/blocked/adapted 未跑
  一律「未覆盖」；完整/部分仅授予有 SHADOW/replay/hist·隐含/scripted-probe 证据的行。
