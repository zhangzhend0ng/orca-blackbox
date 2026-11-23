# GLM 总控扩样批次 2026-11-21

批次终态与口径见[独立复核](#独立复核2026-11-21)，续跑顺序见[迁移任务表](../V3_MIGRATION_LEDGER.md#后续任务表)。

分支 `codex/glm-flash-expansion-20261121-0217`（自 `codex/orca-integration@44034f8`）。台账与逐族映射见 [V3_MIGRATION_LEDGER](../V3_MIGRATION_LEDGER.md)；本页只记运行叙事。

## 环境

- 客机 win11-test 预检全过：relay 通、无孤儿、suite Ready、KVP 关但 host_guard BIOS 兜底（06d2257）实测 True、分辨率 1920。
- v3 检出 `C:\coil\orca-blackbox-v3-r1` 以 Git bundle 逐提交快进（模式同 v3_project_batch_phase setup_bundle；本批 0227b3f→0b81f5d→bf108f7→ceaf295）。
- SUT `5c48644d…`（2.4.0）不变；ZCode app-server bundle **已从 d9afd58d 升到 6b84e928**（11-19 后自动更新），见下述基础设施发现。
- 三份 UIA 门禁收据（d7299035 / bfd5c93a / 52a21e14）离线经 `uia_gate_proofs` 复核通过。

## zcode 轨道（模型侧）

| Run | 场景 | 结果 |
|---|---|---|
| `3140ae82` | uia_general_wall goal-only | 基础设施失败：新版 app-server 新增 `session/readReplyLanguage`，驱动白名单外 → 已修（0b81f5d，答 `{language:'en'}`） |
| `6165a41c` | 同上 | **假通过被拦**：新版 turn 即启即取工具快照，windows_mcp ferry 经 relay 未完成握手 → 请求 toolNames=[] → glm-5.3-flash 单轮虚构"已改壁环数并保存"；驱动 `native_calls_incomplete` 拦截，0 工具调用，清理确认 → 已修（bf108f7，create/send 间 25s 有界等待） |
| `38535cc0` | 同上 | blocked：clash-guard 02:37:45 起 OFF_SAFE（宿主代理被关，非本会话操作），ip_guard 纪律性拒绝，未进客机 |

zcode 轨道待 guard 恢复后续跑。

## script 轨道（无模型复验，六个源提交 bf108f7 至 0b4b919）

| Run | 场景 | 结果 |
|---|---|---|
| `4ab5b246` | uia_replay_layer | **SHADOW 独立通过**（business+path pass，145.5s）——层高 0.40→0.24 链在新 HEAD 复验 |
| `42a45554` | uia_replay_enums | **SHADOW 独立通过**（business+path pass，173.2s）——接缝 Random+熨烫 Topmost 双下拉链复验 |
| `cb413cf7` | uia_replay_mix | **SHADOW 独立通过**（148.7s）——混色 Add Mix 比例+渐变回放复验 |
| `c4e6f4cc` | uia_replay_move_layer | **SHADOW 独立通过**（149.0s）——平移+层高组合回放复验 |
| `112e643a` | uia_replay_save | **SHADOW 独立通过**（147.0s）——另存为副本回放复验 |
| `b5184a26` | cfg_value_06 | **SHADOW 独立通过**（174.5s）——layer+ironing 值组合 |
| `d1d12e57` | cfg_value_07 | **SHADOW 独立通过**（141.6s）——layer+seam 值组合 |
| `fa2ec36f` | pair_layer_move | **SHADOW 独立通过**（145.2s） |
| `9def6142` | bound_model_move（Prusa.stl） | **SHADOW 独立通过**（183.3s）——STL 几何导入→U1 工程→X 平移→保存重开全链 |
| `851d655d` | uia_replay_canvas | **SHADOW 独立通过**（144.9s）——画布 X+10 回放 |
| `2248e3b7` | uia_replay_process | **SHADOW 独立通过**（152.7s） |
| `67dae249` | dep_ironing_topmost | **SHADOW 独立通过**（174.0s）——依赖链正例 |
| `5fc5ceda` | dep_ironing_disabled | **SHADOW 独立通过**（138.2s）——依赖拒绝负例 |
| `112c8fbf` | cfg_value_01 | **SHADOW 独立通过**（138.2s） |
| `441f0f26` | cfg_value_04 | **SHADOW 独立通过**（178.0s） |
| `4283f5c9` | pair_layer_ironing | **SHADOW 独立通过**（172.8s） |
| `d35b3397` | pair_move_ironing | **SHADOW 独立通过**（180.6s） |
| `50a7fa3a` | pair_move_layer | **SHADOW 独立通过**（144.8s） |
| `10460efd` | pair_layer_seam | **SHADOW 独立通过**（141.2s） |
| `fc4ae0a9` | pair_move_seam | **SHADOW 独立通过**（145.1s） |
| `c2d18783` | pair_seam_ironing | **SHADOW 独立通过**（172.8s） |
| `49f1cecd` | uia_hybrid_layer（手写基线） | **SHADOW 独立通过**（144.7s） |
| `a47e895f` | uia_hybrid_layer_strength（手写基线） | **SHADOW 独立通过**（148.7s） |
| `3784e528` | uia_hybrid_canvas（手写基线） | **SHADOW 独立通过**（180.9s） |
| `fa448238` | uia_save_as（手写基线） | **SHADOW 独立通过**（136.9s） |
| `99616c25` | uia_process_combo（手写基线） | **SHADOW 独立通过**（205.0s） |
| `c0b2a5c3` | uia_mix_recipes（手写基线） | **SHADOW 独立通过**（168.7s） |
| `382b92d4` | uia_quality_enums（手写基线） | **SHADOW 独立通过**（229.4s） |
| `c09c1abb` | uia_move_layer（手写基线） | **SHADOW 独立通过**（189.0s） |

| `72cfda6b` | fixture_cold | **SHADOW 独立通过**（325.5s）——冷启 fixture 组（子用例 move_layer+enums） |
| `d7bab669` | fixture_shared | **SHADOW 独立通过**（285.3s）——组共享进程 fixture 作用域（V3_PLAN §8 机制） |

**脚本轨道终计 31/31 SHADOW 独立通过**（源 bf108f7→0b4b919）：手写 UIA 基线 8 + 无模型回放 7 + pair 7 + cfg_value 4 + bound_model_move 1 + dep 负例 2 + fixture 组 2 = SCRIPT_SCENARIOS 登记全项。每轮 business/path 双检查 + 冻结 3MF/G-code SHA + 新进程独立重开 + 清理回据。

第二轮后累计 9/9。第三轮（uia_replay_canvas/process + dep_ironing_topmost/disabled 负例）运行中。

## 基础设施发现（团队需要知道）

1. **ZCode app-server 升级破坏 MCP 工具可用性**：新 bundle 在 turn 开始即快照工具注册表，不等 MCP 就绪。windows_mcp 是 stdio→relay→客机 HTTP 摆渡，握手 3 个往返需数秒，导致工具集为空。glm-5.3-flash 在无工具时**不会报告无工具，而是直接虚构完整业务成功**——本次被驱动机械拦截（native_calls_incomplete），但任何依赖"模型自述成功"的口径都会被骗。缓解已提交（25s 等待）；根治建议 ferry 预热或直连。
2. clash-guard OFF_SAFE 语义（代理关+hosts 拉黑）会静默阻断全部 zcode 批次；`~/.clash-guard/status-token` 集成文件曾被清理，已按 status-api.md 恢复。


## 续跑（guard 恢复后，13:51 起）

guard 于会话后恢复 ready（OK/US 出口）。客机重新同步至 edcaa13（期间发现并修复 guest_v3_bundle_sync 的裸 SHA 区间问题：git bundle 需带 ref 名，改用 HEAD 区间）。

| Run | 场景 | 结果 |
|---|---|---|
| `d74f73f4` | uia_general_wall (zcode goal-only) | **SHADOW 独立通过**，280.2s，首次尝试零恢复：壁环数 3 保存、几何/0.4 层高保持、独立重开 68 层实际挤出（2130 条 XY/E 移动）、Save As 纯 UIA（ValuePattern+InvokePattern，0 截图 0 坐标）、冻结 3MF `52359892…`/G-code `2d26dc2f…`、清理确认。**两项 app-server 适配修复（0b81f5d+bf108f7）端到端验证。** |

泛化八槽复验批（uia_generalization，开发集复验口径）随后启动。


## 泛化八槽复验批（batch `66f6963e`，源 `33869a6`，14:0x–14:4x）

三份门禁收据（d7299035/bfd5c93a/52a21e14）经 `uia_gate_proofs` 复核后启动 `zcode_matrix --suite uia_generalization`。开发集复验口径（11-18 批后已有裁图/串行/恢复修订），每槽一次、900s/40 工具上限、SHADOW 判定。

| 槽位 | Run | 结果 | 工具数/耗时 |
|---|---|---|---|
| wall | `a054d0bb` | 业务失败：引导式提示下 Save As 对话框对原生控件走坐标路由，`native_uia_dialog_route_required` 致命拦截（对照：goal-only 单跑 d74f73f4 同场景 SHADOW——**提示模式敏感性**） | 15 / 206s |
| slot2 | `26739846` | 业务失败：执行未完成，无 proof（与历史材料槽2受阻同型） | 11 / 196s |
| bottom_strength | `ce43098a` | 业务失败：`pilot_target_setting_mismatch`（保存产物目标参数不符；**11-18 唯一通过槽本轮回落**） | 9 / 230s |
| bottom_quality | — | **通过（pass_tool_recovery）**：11-18 该槽死于坐标点击 UIA 控件，本轮带一次受控恢复独立通过 | 34 / 447s |
| y_quality | — | 业务失败 | 12 / 215s |
| y_others | — | **通过（pass_tool_recovery）**：Y 平移历史 0/6 **首次通过**（串行调度修复生效） | 27 / 382s |
| combo | — | 业务失败 | 17 / 226s |
| combo_dialog | — | 业务失败（40 工具上限耗尽） | 40 / 423s |

**正式 2/8**（对照 11-18 的 1/8，通过槽完全不同）。开发锚点 0/2 → 低于 V3_PLAN §4 探索投入阈值，本轮不开探索轮。八槽清理全部确认；客机终态 suite Ready、Orca/python 均 0。acceptance_pass=false，结果范围 SHADOW/业务失败，不改发布门。


## 剩余轨道收官（15:0x–15:3x，源 a8a43ba）

| Run | 场景 | 结果 |
|---|---|---|
| `872323a5` | safety_cancel | **预期拒绝验证通过**（矩阵 grade=PASS：撤销后零输入、工具收据、清理确认） |
| `ab0b9373` | safety_timeout | **预期拒绝验证通过**（grade=PASS，deadline 截停） |
| `03137618` | safety_guard_disconnect | **预期拒绝验证通过**（grade=PASS，fail-closed） |
| `51d7e1e9` | overwrite | **SHADOW 独立通过**（246.8s）——F3 同路径冲突负例在新 HEAD 落定 |
| `c21e9496` | pilot_material3 | NON_GREEN：`native_action_budget`（40 动作预算耗尽，首次真实执行留回执） |
| `7a6170d7` | pilot_infill | blocked（基础设施）：guard 15:30 节点失效 CUT_DEAD→BLOCKED，ip_guard 拒绝 |
| — | pilot_transform | blocked（预登记能力回执）：`scene_numeric_range_and_canvas_edit_authority_not_ready` |

安全三件套在升级版 app-server 下重新成立（停输/超时/守卫断开均按合同拒绝且清理确认）。guard 当日两次翻转：02:37 OFF_SAFE（代理被关）、15:30 CUT_DEAD（节点失效）。


## 第三段续推（guard 18:53 恢复后，源 4fef3cb）

| Run | 场景 | 结果 |
|---|---|---|
| `1e8178fc` | pilot_infill（填充 30%） | **SHADOW 独立通过**（278.1s，零恢复）——11-18 失败的业务线清账 |
| `1d145d63` | uia_general_slot2 (goal-only) | NON_GREEN：`native_uia_refresh_required` 致命（点击后未刷新观察）——材料槽 2 本批 0/4，确认持续缺口 |
| `f33c1744` | uia_general_y_quality (goal-only) | NON_GREEN：`native_uia_main_window_required`（前台离主窗后正确拒绝）——0/7 终身 |

## 截至第三段累计

真实客机独立验收 **39 个通过/预期拒绝 run**：脚本 31（SCRIPT_SCENARIOS 全项）+ zcode 8（锚点 wall goal-only、泛化 bottom_quality/y_others、安全 3/3、overwrite、pilot_infill）。所有失败均留证据：2 次 app-server 基础设施（已修复）、6 次管理层同步失误（已固化教训）、guard 两翻一阻、业务失败各含权威层/独立判据回执。客机终态干净。


## 根因分析（离线，19:0x）

**bottom_strength 回落 = 模型选错字段**：今日冻结件 `top_shell_layers=6`（原 3）、`bottom_shell_layers=3`（未动）——模型把 "6" Type 进顶壳 Edit（automation_id -30540），11-18 通过件打的是底壳（-30515）。UIA EditControl name 为空，需按混合合同用裁图做“自绘标签↔Edit 绑定”，本轮模型绑定失败选了邻近字段。ValuePattern 提交链本身正常（顶壳值已落盘）；oracle 正确拒绝错字段+破坏保持项。**非基础设施、非合同漂移**。改进方向：给 Strength 页提供与 Quality 页（enums 修复）同类的标签绑定辅助。

**slot2 四败归一 = 材料槽弹窗导航缺口**：四次四种死法——①矩阵引导式：点 Objects 页签后遇 `wxWindowNR` owned 弹窗卡住（模型诚实报告 blocked，未保存）；②goal-only：`native_uia_refresh_required`（点击后未重新观察）；③11-18 矩阵：画布点击后前台变同 PID 非主窗；④11-18 dev 同族。共同根因：per-object 耗材分配路径会弹 owned 弹窗，现有弹窗合同（Save As/取消）不覆盖该区域的导航/解除。**共享层能力缺口**，非模型噪声。


**strength_a 探针**（`e006b2b8`，源 7c031cc）：**SHADOW 独立通过**（256.8s，零恢复）——Strength 页层高 0.40→0.24、独立重开 112 层实际 G-code。证明 Strength 页整体可导航可提交；bottom_strength 失败确系“顶/底壳字段二选一误绑”而非页面级问题。历史业务矩阵代表件在新 HEAD 保持。

## 分析段终计

本段产出三项定性：①bottom_strength=模型字段误绑（顶/底壳），提交链正常，oracle 拒绝正确；②slot2=材料槽 owned 弹窗导航合同缺口（四败归一）；③Strength 页代表件复验通过。全会话独立验收通过累计 **40**（脚本 31 + zcode 9）。


## 并行段（19:2x–20:0x，源 a4a53a6）

**B 线修复**：Snapshot 标签绑定辅助（a4a53a6）——侧栏 ValuePattern 控件附加同排左侧最近 wx 标签；MCP 等待策略移至 probe（驱动默认 0，单测 15s 预算恢复）。全量单测 1428 通过、仅原 2 个先前已存在失败。

**A 线复验（全部零恢复 SHADOW）**：

| Run | 场景 | 结果 |
|---|---|---|
| `6cba9296` | uia_general_bottom_strength (goal-only) | **SHADOW（240.6s）——标签绑定修复闭环**：bottom=6 落对字段、top=3 保持（与修复前 top=6/bottom=3 精确镜像） |
| `213374f7` | others_a | SHADOW（270.6s） |
| `081c8500` | others_b | SHADOW（257.7s）——11-18 该场景曾失败，本轮过 |
| `dd08dda2` | save_dialog | SHADOW（275.1s） |
| `48989b69` | quality_b | SHADOW（236.6s，源 8f281d3 段） |

历史业务矩阵本批已复核 `quality_b`、`strength_a`、`others_a`、`others_b`、`save_dialog`、`overwrite` 六项的通过收据。泛化槽 bottom_strength 在 goal-only 和标签辅助同时启用时通过开发复跑，保留原矩阵 guided 判定。

**本批累计 31 条 Script SHADOW 通过、11 条 ZCode 业务或路径 SHADOW 通过、3 条安全预期拒绝通过。**


## slot2 弹窗合同修复（20:1x–20:4x，源 532e370→5841436）

三轮合同修改及各轮客机复跑如下。

| 修复（提交） | 证据 | 复跑 |
|---|---|---|
| 弹窗合同开放给耗材槽族+高度预算（532e370） | 卡死弹窗=同款 wxWindowNR/"panel" | `7cae138f`：绑定未触发——弹窗跨侧栏缝超 +1px 容差，弹窗期无裁图可用=死锁 |
| 几何放宽（缝 160/宽 300/高 480）+popup_bounds 记录+goal 提示教弹窗裁图（e47e13c/69d302d） | `81587927`：死于 recovery_observation（模型恢复协议失误） | `07ab7efb`：模型用 **UIA Invoke** 合法开下拉，但 opener 只认坐标点击→死锁 |
| **UIA 动作点击也登记 opener**+轨迹携带 popup_opener+验证器重建（5841436） | `df2b6784`：opener=[147,617] 已入轨迹✓、模型主动请求 wx_process_popup 裁图✓，但假定弹窗已开而未观察→致命；`0a7680b4`：UIA 动作后未刷新观察即点击→RecoveryViolation | — |

**终态为端到端未闭环（NON_GREEN）。** 弹窗合同已扩展，UIA opener 登记与失败拒绝有运行证据。`07ab7efb` 发生在 UIA opener 补齐之前，属于合同缺口。最终合同 `5841436` 下两次运行均在观察或刷新阶段被拒，清理均确认，业务验收 0/2。

## 独立复核（2026-11-21）

审查对象为 `codex/glm-flash-expansion-20261121-0217@6df44ca`。`44034f8..6df44ca` 实际为 30 个提交。以下为本地收据、冻结产物和矩阵判定的离线复核。

- **Script** 31 个登记场景均为 SHADOW 通过，业务、路径和清理收据齐全。源提交共六个（`bf108f7`、`ceaf295`、`87c3d28`、`11c3cec`、`74ae046`、`0b4b919`）。29 个单场景与两组 fixture 的 4 条子运行均核对了冻结 3MF/G-code 哈希与独立重开收据。可作为相应场景的 SHADOW 回归依据，`6df44ca` 的单源整套结果待补。
- **ZCode** 11 条业务或路径 SHADOW 通过，3 条安全预期拒绝经矩阵判定器复算通过。开发集 `66f6963e156b424fbbc542cc8883da6a` 重算为 **2/8**，两个通过槽均使用受控恢复，`acceptance_pass=false`。历史 1/8 和本次 2/8 分别留档。guard 阻断与同步故障单列，不把计划未启动槽计成模型失败。
- **slot2** 最终合同 `5841436` 下 `df2b6784` 与 `0a7680b4` 均有拒绝和清理收据，均无独立业务通过。早期 `07ab7efb` 有 UIA opener 合同缺口。结论为端到端未闭环，下一步按相同判据建立 Script 正对照。
- **标签与提示模式** 直接核对了两份冻结 3MF。`ce43098a` 顶壳 6、底壳 3，`6cba9296` 顶壳 3、底壳 6。开发复跑确认修订后选对字段。两轮同时变更了代码和提示模式，标签的独立贡献待做对照。壁环数 goal-only 成功、引导式失败各一次，且源 SHA 不同。空工具 run `6165a41c` 的完成自述被 `native_calls_incomplete` 拒绝。
- **迁移与探索** 89 条登记册与 31 个 Script 场景分别统计。台账的 21 项是待签核证据候选，其中至少 9 项已知只映射部分断言。独立复核发现 F5 缺一条明细，已补 `m8x_125_aux_mix_pref`。已用于修复的路径归开发回归，另行冻结未参与调试的目标来评估探索闸。此次没有新增客机运行或发布 GREEN。


## 并行补充：实体机 Win10 七盘流程第 4 次复现（2026-11-22，D:\GUI_Test\out-p4）

用户提示第二台 SSH 可达 Windows（DESKTOP-FA706G3，admin@172.18.6.193，控制台会话在线）。零搭设复跑便携 OrcaPerfRunner（--check 过，校验和一致）：**exit_code 1，第 4 次稳定复现**。run.log 根因：`showcase_snapmates: FAIL (Orca could not become foreground for video)`——SSH 触发的交互计划任务下 Orca 无法成为前台（demote_watchdog 两次将前台归还启动前窗口）。与 11-21 三轮同因合并：**真机控制台前台获取问题，非切片/渲染问题**（VM 上同二进制通过、GL 栈不同）。修法属性能轨道：让控制台前台空闲（关闭 UU 远程等常驻前台窗）或改前台捕获策略。产物：out-p4/run.json+run.log+两段 pending.mp4+两个 showcase 摘要留在机内未拉取（gitignored 级）。


## P0-2：单源整套复验（2026-11-22 00:1x–01:2x，源 a501339）

31 个 Script 场景在同一提交下全部重跑：**31/31 SHADOW 独立通过，零失败**（中途一次因并行提交造成 HEAD 失配损失 5 个 run 槽，已按"批中零提交"纪律整批重启重跑）。

| Run | 场景 | 结果 |
|---|---|---|
| `6b178c5d` | uia_replay_layer | **SHADOW**（144.8s） |
| `fb481167` | uia_replay_save | **SHADOW**（145.4s） |
| `6f3ed5f7` | uia_replay_canvas | **SHADOW**（149.1s） |
| `4dcb2b88` | uia_replay_process | **SHADOW**（153.3s） |
| `ba79e6b1` | uia_replay_mix | **SHADOW**（149.5s） |
| `22118444` | uia_replay_enums | **SHADOW**（178.7s） |
| `a6c8b72b` | uia_replay_move_layer | **SHADOW**（145.3s） |
| `a19d20ca` | pair_layer_move | **SHADOW**（150.6s） |
| `0fe99870` | pair_layer_seam | **SHADOW**（145.5s） |
| `77231f23` | pair_layer_ironing | **SHADOW**（173.0s） |
| `b7f1cdb9` | pair_move_layer | **SHADOW**（174.0s） |
| `7797c47a` | pair_move_seam | **SHADOW**（167.8s） |
| `9fcdccf6` | pair_move_ironing | **SHADOW**（180.9s） |
| `bb245c03` | pair_seam_ironing | **SHADOW**（181.5s） |
| `5f68bb1e` | cfg_value_01 | **SHADOW**（142.5s） |
| `55eae296` | cfg_value_04 | **SHADOW**（178.7s） |
| `acf976c5` | cfg_value_06 | **SHADOW**（179.3s） |
| `37222cc8` | cfg_value_07 | **SHADOW**（146.9s） |
| `4ea831e5` | uia_hybrid_layer | **SHADOW**（145.1s） |
| `32e6d486` | uia_hybrid_layer_strength | **SHADOW**（149.6s） |
| `563608f4` | uia_hybrid_canvas | **SHADOW**（186.0s） |
| `77198db9` | uia_save_as | **SHADOW**（141.6s） |
| `09887fdf` | uia_process_combo | **SHADOW**（209.4s） |
| `95792d16` | uia_mix_recipes | **SHADOW**（169.3s） |
| `e04df341` | uia_quality_enums | **SHADOW**（233.8s） |
| `9448609e` | uia_move_layer | **SHADOW**（193.7s） |
| `148865ff` | bound_model_move | **SHADOW**（184.5s） |
| `d43fc6fe` | fixture_cold | **SHADOW**（329.3s） |
| `eee638dd` | fixture_shared | **SHADOW**（285.8s） |
| `c9062724` | dep_ironing_topmost | **SHADOW**（174.8s） |
| `2f20d2a3` | dep_ironing_disabled | **SHADOW**（138.1s） |

单源证据链齐备：每 run 冻结 3MF/G-code SHA + 独立重开进程 + 清理回执。本表即评估要求的"`6df44ca` 后单源整套"补齐（于后续源 a501339 完成，代码相对 6df44ca 仅门禁改版一项，已单测覆盖）。


## P0-1 闭环：slot2 Script 正对照（2026-11-22，源 5de8616）

按评估 P0 顺序先建确定性对照再验 ZCode。三步落地（两修一验）：

| 步 | 内容 | 结果 |
|---|---|---|
| 1 | 注册 `pilot_material` 为 script 场景 + `assign_filament_slot2()`（m7j 的右键菜单 Change Filament 路由，选第二个物理行） | `578c564b`：死于潜伏 `UnboundLocalError`（binding 仅画布族赋值）——已修 |
| 2 | 修复后 `e6668fef`：脚本执行正确、本地对收割产物全量 verify 通过（槽2/T1/68层/27.2），但客机校验拒于 `project_layer_config`——`pilot_material` 缺 TRIALS 键，落入默认层高判据（要求层高改变，而业务禁止）——已修 | — |
| 3 | `30482d62`：**SHADOW 独立通过**（181.9s）——object_filament_slot=2、object_tools=[1]、68 层、last_z 27.2、几何不变、层高 0.4 保持 | ✅ |

**结论：slot2 业务路径+oracle 确定可行。ZCode 在该业务上的失败自此正式归因模型执行（时序纪律），非路径/判据问题。**


### P0-1 后续：ZCode 对照验证（源 d446ba1）

- `c40850f8`：死于 probe 运行期 clash-guard 轮询（guard 又 BLOCKED）——暴露评估门禁改版不完整（demo 预检改了、probe 轮询没改）。已补齐：常规场景运行期改轮询 `GatewayGuard`（内网网关事实入收据），safety 场景保留真 guard（d446ba1）。
- `95a8f324`（新门禁下）：模型第 6 种路线——自己发现了 m7j 式右键菜单路由（canvas 裁图→右键→菜单弹窗出现→请求裁图→点击菜单项），被正确拒绝（上下文菜单窗口不在弹窗绑定合同内，`native_uia_main_window_required`），清理确认。

**P0-1 最终结论：Script 正对照确定通过（30482d62）+ ZCode 同业务 0/7（六种路线六种失败，每次权威层拦截正确）。slot2 的差距被精确定位为模型执行层；框架、路径、判据、门禁全部证明就绪。**


## 飞书补充实现段（2026-11-22 03:0x 起）

**#254 层高组合（P0）→ `uia_param_layer_pair` SHADOW**（`95cd45f5`，161.8s）：0.2/0.25 写入、首层 Z=0.25、135 层、末层 27.05、其余设置保持——表内判据逐项落进 V3 oracle。实现路径三修：①标签实为"First layer height"（OCR 实证）；②该行无可定位 Edit（值列校准不含它）→ 改 float_edits_in_view 第二行位置编辑（edit_layer 同款已证机制）。变更集 LAYER_PAIR 入白名单+合成单测 4 条。


## 飞书补充段进展（2026-11-22 05:0x–07:0x）

**首批 5 条中已闭环 3 条（3/44；全部 SHADOW
- **#266 墙圈数与薄壁** `05dd9020`（168.8s）：wall_loops=4 + detect_thin_wall=1，68 层保持。
- **#267 外壳层数与图案** `f324120d`（185.2s）：top=5/bottom=3 + concentric/rectilinear 双图案切换。top_color_penetration_layers 缺席为记录的口径缩减。
- （#254 见前段）

**打通的共享能力**（当时后续 39 条待实现用例直接受益；截至 11-24 03:40 未清 3 条）

**在攻 2 条**：#268（Gyroid 在图案弹窗第 2+ 页，滚动投递未生效）、#259（熨烫组 Speed 行 OCR 未中）。失败 run 全留证据。


## 飞书补充段终态（2026-11-22 08:0x）

**补充用例 3/5 SHADOW 独立通过**：#254 层高组合（`95cd45f5`）、#266 墙圈数薄壁（`05dd9020`）、#267 外壳层数图案（`f324120d`）。

**两条在攻、精确归档**：
- **#268 填充组合**（5 跑：9866d291/79ca1e8c/ce169b74/7968a6db/a8837dcc/08f6904b/96c325d3）：密度/方向/重叠/Gap fill 全链已通，唯一卡点=图案弹窗中 **Gyroid 在列表深处且自绘弹窗滚动回弹**（真光标轮与 PostMessage 轮均不累积；列表可见页恒从 Aligned 起）。下一步：专项探针（拖动弹窗滚动条或逐行小步轮+沉降）。
- **#259 熨烫组合**（60237e59/7eadbe35/a3fd0bff）：组合切换已通、Flow/Spacing 为目标值故跳过编辑；卡点=Topmost 选后页面重建中 **Speed 行的绘制标签未OCR命中**（Speed/Ironing speed/speed 三变体全空）。下一步：重建后带 band 打印定位真实标签。

**共享引擎沉淀**（供当时剩余 39 条直接复用；截至 11-24 03:40 未清 3 条）


## 交接快照（2026-11-22 13:0x，供三机并行新会话接手）

VM 批已收完、桌面空闲、客机 HEAD=6288f47（与远端一致）。最后一批结果：

| Run | 场景 | 错误 | 诊断 |
|---|---|---|---|
| `6ec6f4c0` | #268 infill | Gyroid 弹窗空行 | **[popup] children: []**——图案弹窗零子窗，纯自绘列表；VK_NEXT 关弹窗、WM_CHAR 无渲染、滚轮回弹。下一步=真桌面现场试验（拖自绘滚动条/按住列表底部自动滚动），正是 fa706g3 agent 任务A |
| `eacfc6ff` | #263 bridge | Bridge flow 行未找到 | band 实拍：'Extra briage layers (peta)'/'Filter out small internal bridges'/'Bridge counterbore holes'——Bridge 组实际标签与配置键名不同，Flow/Density 或在折叠区下方 |
| `121abf7b`/`8946a225` | #270/#271 | gui_wait_timeout | 93s 快败，疑 Speed 页 tab hint/Advanced 流程问题，待 band |

batch2 四例与两个老卡点的全部证据就绪；引擎与注册链完好（batch2 四例合同/单测已过，只差 ops 标签校准）。


## 四面并行会话（2026-11-22 12:45–18:00，GLM 总控）

**编队**：driver v2（teammate_loop2.py：yolo 建会话+权限兜底+轮询到 turn 完成末条提取；v1 三缺陷=blob 令牌污染/权限空答死等/首读即退）。五任务全闭环 REPLY SEEN：

- **fa706g3 任务A**（诊断，008bab6）：#268 配方=真滚轮 −1 格×2、≥400ms 沉降→Gyroid 完整入镜（第 21 项），点词框中心提交；typeahead/VK_DOWN(真+PM)/VK_END 全灭；触摸式伪滚动条上拖=深处；重开弹窗自动定位选中项。#259 真相=ironing_speed("Ironing speed")在 Speed 页 other-layers 组（PrintConfig.cpp:3618+Tab.cpp:2433），Advanced 前置，tesseract 首字母 I→l 须匹配 "roning speed"。侧栏病理：弹窗交互后滚轮死锁、大格复位、页签切换/Advanced 切换复活。
- **fa706g3 任务B**（6a73dbb）：7 条 pilot（#276-279/#292-294）夹具实测校准（"by object"/"100%"/"normal(auto)"），三方注册+check_registry PASS。
- **fa706g3 任务C**（3fc337e）：物理 Win10 口径 m0/m1/m2 GREEN；m3j-l RED=SUT 构建差异（nightly c98c6d3 无 MixedFilamentBatchDialog，探针实证）。
- **Mac 任务A**（1a391d8）：层高正例 `0a24557a` **SHADOW**（68→112 独立重开）；0.32 负对照 `b715f843` 按合同拒绝；壁环数/X+10 NON_GREEN 精确归因（Mac 参数页扁平无页签、后台会话画布不消费合成点击）。
- **Mac 任务B**（e6eee4d）：P0-3 签核表 89/89（完整 9/部分 15/未覆盖 60/不适用 5、无法评估 0）。

**VM 产线**（batch2 收尾→batch3→校准轮）：
- 基础设施链修：agent_bridge 轮询 25→45s（app-boot 饱和误杀）；bundle_sync EAP Stop→Continue（git stderr "okay" 在 PS Direct 终止同步）；param 族跳过预点击（Speed 页签 named_child 6/6 gui_wait_timeout）；Speed 标签实证校准（First layer speed/infill、travel="150%"）。
- **楔子根因**：客机 `.desktop_locks` 陈旧租约→新 run FileExistsError 秒退→demo 等满上限。自愈=批前清锁+timeout 900 看门狗（queue7 起）。
- **#268 填充组合 `f307ef1f` SHADOW**（3.5min）：Gyroid 弹窗首次选中+参数写入+保持项+冻结重开+G-code 排程全绿。唯二修复=fa 配方入引擎（真滚轮+触摸条兜底+real_drag_screen）与 pilot 键名 top_bottom_infill_wall_overlap（74fe62e3 diff 实证；验证器既有规则已覆盖类型噪声）。
- 在攻：#259 combo 提交步（row 已达、点击未落，text=None）；#264/#271 标签族与 #290/#291 combo/enable 族——全部留 band 证据；#270 first_speeds 标签已校准待复跑。
- 补充路线 44 条进度：**首批 5 条中已闭环 4 条（4/44）→ 5 项在库可攻**

**合并**（宿主唯一合并点）：fa 分支（诊断+7 pilot+物理首跑，b4fd7d7）+ Mac 分支（runner 移植+签核表，6dc02a7）均并入本分支并推送；agent 分支 origin 侧同步（codex/mac-author 代理推送；fa 中转检出接力）。

**下一批**：#259 combo 提交步 band 校准；#270 复跑；fa 7 条 authored 首跑；租约释放失败根因（runner 异常路径不释放）。


## 续会话（2026-11-22 22:00–23 日 00:25）：#259/#268 双卡点全灭

- **#259 熨烫 `073f086f` SHADOW**：补充路线 **首批 5 条全闭环（5/44）**
- **fa 作者链首验**：#277 support_basic `91678bcb` **SHADOW**（agent 编写→宿主审查合并→VM 首跑一次通过）。
- fa B2 闭环（04fa1ff）：第二批 7 条（#255-257/#260-261/#272-273）夹具实测键名零偏差+四方注册断言；已合入主线 54582a9。**fa 累计 authored 14 条**。
- Mac A2 闭环（5c503ca，blocked 精确归因）：wall_loops 控件在硬虚拟化 outline 未物化区、该页所有滚动通道失效、Mac build 预设行无 edit 图标；修正两处上轮误判（AXValue/AXHelp 可读、扁平页滚动箭头有效）；解锁三路径=屏幕录制 TCC/Automation TCC/上游 AX 补全。
- queue9 其余留证：speed_limits/raft/support_filament/by_object/spiral_vase/timelapse 六族 band 证据归档待校准；first_speeds 三度被陈旧租约楔（unlock 前置未覆盖其场景，租约释放根因仍未修——下一批首项）。
- 验证器/引擎七项修复全部入主线（a9bcb6f→…→073f086f 前共 5 提交），#259 收敛链本身即引擎硬化史。


## 九小时续航会话（2026-11-23 00:25–08:10，GLM 总控）

**SHADOW 净增 +4：#257 精度补偿（8ff22123）、#273 空驶速度（3c1ab0d1）、#297 排除对象（01163442）** + 早段 #259。参数族累计闭环 **9 条**（#254/#257/#259/#266/#267/#268/#273/#277/#297——含 fa 作者链 3 条：#277/#257/#273 + fa B4 1 条 #297）。

**引擎级修复（根因三连）**：
1. **双向滚动**（b7c11f8）：编辑提交后面板重建、滚动落点随机（983bab81 从页底起搜）——短语搜索改「下 12 轮 + 回上 26 轮」。line_width 因此全链至 save、by_object 因此通过 combo。
2. **租约陈旧接管**（99b5d6d）：锁内写 PID、获取冲突验活接管——异常路径不释放锁的楔子根因之一。
3. **combo 元组解包**：run_ops 不再静默吞 set_combo_by_popup 失败（#259 六轮收敛链首环）。

**fa706g3 四批全闭环（B1-B4）**：**累计 authored 29 条 + 2 条混色族只做归因**（mixed_filament_* 无参数页行，需 mix 引擎链，未登记）——合计 42 条登记为参数场景模块。作者链首验通过率 4/29 首跑 SHADOW（#277/#257/#273/#297），其余留 band 证据分层校准中。

**Mac A2/B2 闭环**：面板寻址 blocked 精确归因（硬虚拟化 outline+滚动全灭+Mac build 无预设 edit 图标；AXHelp 可读/滚动箭头有效两误判修正）；写回工单 216 行对账（可立即写回 6 行 SHADOW 口径、待首跑 21+、维持 189）。

**queue14 终态（23 场景 40 run）**：1 SHADOW + 22 留证。失败分类：参数行/标签族 9、checkbox 状态回读 5、file_toolbar_missing 3（ESC 重试已加未验证）、楔 3、slice_button_unavailable 2、模态 1（分类合计 23，比 22 条留证多 1，哪一类多计未逐条复核）。skirt/timelapse/arc_resolution 执行完成但验证未过（终层校准）。

**楔子（宿主侧 launch 链）未根除**：本窗口发生率 ~25%（租约修复前 ~40%）；签名=hv_go 全输出而 launch_done 未写、客机无 run 目录。已缓解：900→620s 看门狗+即时重试（queue14 起 rc=124 也重试）。根因候选：提权子进程在 hv_go 返回后、写 launch_done 前被外部终止——下一窗口用 Sysmon/ETW 跟踪。

**下一批**：①终层校准（layer density 二词变体、clearance 行、checkbox 回读、slice_button）；②楔子 ETW 根因；③P0-3 签核转正+写回工单执行（6 行）；④Mac TCC 人工决策。


## 续二：模型切换、Mac 负对照、引擎根因批（2026-11-23 15:15–17:45，GLM 5.4 总控）

**参数族闭环数不变：9/44（Windows 冻结构建 SHADOW）。本节没有新增 Windows SHADOW。**

**模型**：两台靶机的 `new-provider` 登记 `glm-5.4` 并设为默认；`teammate_loop2.py` 改为钉死并核验模型（建会话回执 / 应答消息 / 请求三者一致才执行，默认不回退）。靶机 bundle 0.17.3 对 5.4 只有 `disabled/enabled` 两档，且显式指定的档位不会保存到会话上（回合一开始即 `Reasoning level is required`），所以走「不带模型建会话 + 核验会话模型」。fa 普查 E2/E3 与 Mac A6 三个真实任务均由 glm-5.4 完成。

**fa 标签普查**（fa706g3，Orca 2.3.5-nightly，校准口径，非回归证据；`docs/runs/evidence/fa706g3-label-census-2026-11-23/`）：

| 页 | 行数 | 其中标签样 | complete |
|---|---:|---:|---|
| Quality | 102 | 74 | （首轮，无此字段） |
| Strength | 61 | 46 | （首轮，无此字段） |
| Speed | 79 | 65 | true（两轮停在 1240/1240px） |
| Support | 51 | 39 | true（780/780） |
| Multimaterial | 61 | 42 | true（880/880） |
| Others | 66 | 54 | **false**（15 分钟页预算在第二轮 1320px 处用完；尾部 y>1800 两轮坐标差约 100px，有重复行） |

普查直接回答的事实：
- **Others 页（默认模式）没有 `Add line number` 行**（11-24 更正：该行只在应用的 develop 模式出现；按场景播种 develop 模式后 #296 已 SHADOW，见「续五」）。G-code 输出组整组是 Reduce infill retraction / Verbose G-code / Label objects / Exclude objects / Filename format；对 163 张帧裁图做不带过滤的离线重读，`line number` 零命中。VM 2.4.0 的全页扫描同样没找到。
- **Others 页没有 `Timelapse` 行**（同法零命中；11-24 更正：源码 `toggle_line("timelapse_type", is_BBL_Printer)`，仅 BBL 机型有，U1 上不适用）。#294 延时摄影不属 U1 的工艺参数页。
- `Flush into this object` 在 2.3.5 不存在（2.4.0 源码有，版本差异）；支撑冲刷行的真实行名是 `Flush into objects' support`。
- 新种子配置启动后页签只有五个、没有 Speed，点一次 Advanced 才出现六个；切页签不回页顶（滚动位置跨页签共享）；Others 页大片区域吞滚轮。

**Mac 壁环数 2→3（run 306d3efe）——记为 Mac 口径 SHADOW，带保留项，不计入 44 条**：
- 判据是 agent 自写的差分判据 `verify_walls_differential`：原 Windows 轨道判据拒绝了 2.4.1 保存期的配置迁移噪声（新增 24 键、46 个向量迁移、预设改名、模板 G-code 刷新）。共享的 `harness/pilot_common.py` 未被改动。
- A6 负对照 52 项：45 项必须项里只有真实 run（A）与由基线重建的正确配置（X4）通过，43 项拒绝；B（基线自身）/ D（只改别的键）/ E（壁环数 3 并夹带 5 个无关改动）/ F（壁环数 4）全部拒绝。宿主在 Mac 上独立重跑该脚本，52 项判定、错误码与输入哈希逐项一致。
- 保留项（A6 自列，照录）：界面读回 2/3/3 是「读到期望值才落账」的闸门，不是测量，数值的独立佐证来自保存件与 G-code 回显；G-code 取自切片器打开的盘面文件，GUI「导出 G-code」未测；只证明了这一个判据函数，其后的宿主检查没在构造件上执行；首跑 ffe0c6e4 的 NON_GREEN 不改写。SUT 为 macOS / Orca 2.4.1。

**引擎根因批**（`C:\coil\vm_setup\fleet_prompts\apply_calibration_r3.py`，31 处断言式替换，任何锚点对不上即整体中止；离线模拟测试 `test_calibration_r3_sim.py`：真实工作树 15/15 通过，原版 8 项变红）：
1. **滚轮焦点死锁**：按短语/按行找行的两个扫描循环此前盲滚 12+26 格、没有卡住检测（只有 `scroll_group_into_view` 带自愈）。键盘焦点落在数值框时 wx 让该控件吃掉滚轮，面板不动，于是组标题进视野后第一屏之外的行永远够不到（99a53a80、f149c3da）。加 `_StallGuard`（带内容连续 3 步不变即清焦点，两次无效判页底）与 `focus_off_edit`（`GetGUIThreadInfo` 查焦点，必要时附着输入队列 `SetFocus` 到面板）。
2. **行首锚定 `^`**：`Wipe speed` 此前落在上一行 `Role based wipe speed`（复选框行，13613ac7），`Travel` 落在 `Initial layer travel`。
3. **组内限定 `group_span`**：同一页上 `Outer wall` / `Travel` 各有三处（速度、加速度、抖动组；2.4.0 截图 f0e683fb）。
4. **两行式行**：标签一行、数值框在下一行约 34px 处（Overhang speed e4a08beb；Speed 页首行 0b7886bc）。只有声明了 `field` 或 `"below": true` 的行才向下一行找，避免灰掉的行误填到下一行。
5. **页首组标题定位无解**：`scroll_group_into_view` 对进不了可视带的标题一直滚到 420 秒超时，每个操作调用两次共 840 秒——这是 **#270 first_speeds 每次「卡死」的真因**（`Initial layer speed` 是 Speed 页的第一个组，页在顶时标题贴在可视带上沿之上）。改为 6 步不动即接受。
6. **组名不存在**：#263 写的 `Bridge`（实为 `Bridging`）、#276 在 Quality 页写的 `Advanced`（实为 `Line width`），此前同样空滚 420 秒（eacfc6ff 的时间账吻合）；改为 16 轮后放弃并明确报错。
7. **弹窗多词目标**：点击与事后校验都只在单个 OCR 词里找，`By Object` / `Outer only` 这类目标在两处永远不成立；改为按行拼接匹配。
8. **失败点截图** `param_failure.png` 随收割带回：OCR 带文本有歧义时，看图一次定案。

**ops 校准**（依据：源码图谱 + 2.3.5 普查 + 2.4.0 截图）：#263（Bridging / External bridge density / 删除页面上不存在的 Max bridge length）、#276、#292（`Print sequence` 的值是 `By Layer`；中午改成 `Intra-layer` 是把相邻两行的 OCR 粘连误读成一个值，已更正）、#291（`Brim-object gap`）、#271（`Small perimeters threshold`，组限定）、#274（`First layer` / `^Travel`）、#284（`wipe_tower_filament` 在 Multimaterial 页 `Filament for Features` 组，此前写在 Support 页，`filament` 一词只命中了组标题）、#256（`^Wipe speed`）、#270（首行两行式）。

**工具**：图谱挖掘修正了重复页名（Tab.cpp 里工艺设置与打印机设置各有一个 `Multimaterial` 页，此前后者覆盖前者，害我一度误报「15 个操作的组名不存在」，核实后是 5 个）；ops 校验器新增组名校验与多词 combo 锚点校验，并按引擎语义理解 `^`。

**运行鉴别更正**：
- queue15 的 25 连快败是另一会话在同一条分支上提交导致客机与宿主提交失配，不是楔。
- 「没有收割结果」的 run 多数是启动成功而宿主侧等待进程先死，客机照常跑完：e86ca34f、c43dafc2、f8706b6f、0b7886bc 已手动收割，均为 NON_GREEN。f8706b6f 那次是我在队列运行期间用了 relay 单槽通道所致。
- 加分段标记之后没有一例复现为启动阶段真楔。

**queue17（补丁前，10 场景）**：0 SHADOW。带证据的失败 5 个（filament_features、seam_wipe、overhang_curl、accelerations、brim），skirt 执行完成但验证 target mismatch，tree_support 败在保存工具栏，其余因客机桌面被占而未跑成。

**r3 补丁首版的事故（如实记录）**：ae44283 入主线并同步客机后，验证队列的第一个场景（run b4d1c596）就以 `NameError: name 'uia_set_float' is not defined` 失败——替换脚本在整体替换 `_find_phrase_row` 时把它后面的 `def uia_set_float(...)` 函数头一并吃掉了，原函数体变成上一个函数尾部永远执行不到的代码。语法合法，所以编译通过；离线测试只调搜索逻辑、不调 `uia_set_float`，所以全绿。已停队列止损（损失 2 个 run 槽），补回函数头，并加了两道护栏：替换脚本自带「补丁前后顶层定义清单比对，任何原有定义消失即中止」；离线测试加「入口函数存在且参数符合预期」。修正后的脚本产出与修复后的文件逐文件一致；原版副本上扩展后的测试 8 项变红。该测试已入库为 `tools/test_param_engine_sim.py`（23 项，改引擎后必跑）。

## 续三：queue18 的账、普查探针与 r3c（2026-11-23 17:45 起，GLM 5.4 总控）

**结论（截至 21:10，queue20 在跑）：queue18（r3b）10 个场景 1 过 9 败、queue19（r3c.1）10 个场景 2 过 8 败、另有队前验证 run by_object（b6bc43ae）SHADOW

**queue18（引擎 024733e，每个场景一次，业务失败不重试）**

| 场景 | run | 结果 | 失败签名 |
|---|---|---|---|
| bridge (#263) | 55e8a417 | **SHADOW** | bridge_flow 1 / density 100% / angle 0 / 68 层 / 27.2，其余设置保持 |
| by_object (#292) | 6640e4a9 | NON_GREEN | pilot_target_setting_mismatch（下拉选项未选中） |
| feature_speeds (#271) | af5292e5 | NON_GREEN | param_uia_field:^Top surface:0 |
| accelerations (#274) | 5c90c7a6 | NON_GREEN | param_row:Outer wall acceleration |
| seam_wipe (#256) | 5aa4826e | NON_GREEN | param_row:^Wipe speed |
| speed_limits (#276) | fc5b643c | NON_GREEN | param_uia_field:layer height:0（升级前通过过的场景，回归） |
| filament_features (#284) | 6b399e48 | NON_GREEN | AttributeError: 'list' object has no attribute 'startswith' |
| brim (#291) | f323be97 | NON_GREEN | param_combo_target:Outer only（弹窗 OCR 为空） |
| overhang_speeds (#264) | f775cd31 | NON_GREEN | param_checkbox:Detect overhang |
| overhang_bridge (#272) | ec02cd86 | NON_GREEN | param_row:Overhang speed |

在 speed_limits 回归出现时停的队列：第 9 个之后才停，比该停的时机多烧了约 5 个场景。

**普查探针 `uia_param_census`（54fa243；run c101c0f4、e80c899c；原始输出 `docs/runs/evidence/param-ui-census-2.4.0-2026-11-23/`）**——日志解释不了的失败不再靠推理，一个 run 把引擎依赖的事实量出来：
- 工作区 `(0,0,1920,1032)`，最大化窗口自报到 y=1039，选项视口 `(1,718,421,1031)`，Process 行 y=614。
- **滚轮一格 = 60px（两行）**，上下行皆然。焦点在复选框 Button 上时滚轮照常（连滚 8 格）。
- **单位标签（`mm/s`、`mm/s or %`…）也是带文本的 wxWindowNR 窗口**，宽 120、x=203；真实组标题宽 393、高 18、x=13。两者都是选项视口的后代窗口（`IsChild` 为真）。
- **下拉弹窗开在控件正下方，不避让任务栏**：`Print sequence` 在 y 961–987 时弹窗为 993–1049，`By object` 的点击点 `(304,1035)` 经 `WindowFromPoint` 解析到 `Shell_TrayWnd (0,1032,1920,1080)`。
- **ESC 关不掉选项弹窗**；其后的第一次点击只是把它关掉。
- 六个页签的真实组标题（已存为夹具 `harness/param_ui_titles_2.4.0.json`）。它与源码图谱不一致：图谱写 `Initial layer speed`、`Tree supports`，页面是 `First layer speed`、分支角度在 `Advanced` 下——**图谱来自宿主源码树，不是客机构建**。

**被推翻的推理（如实记录）**：(a)「复选框后焦点在 Button 上锁住滚轮」——错，是我写的卡死检测用 OCR 词 y 集合做签名，等高行下页面在动也判「没变」，9 格后误报页底；(b)「`Other layers speed` 标题找不到」——标题一直在，是它滚到 Process 行以上后被 `ly > py` 滤掉，而找不到的分支只往下滚；(c)「加速度组第二行找不到是跨度静态」——主因是单位标签被当成下一个标题，组跨度塌缩成约 10px。

**r3c（485843b + 0a7687d）**：标题集按宽度/x/高度/文本重写并保留视口后代；组跨度每步重读；标题行不当成行（`on_title_line`）；卡死检测改用标题窗口 y + OCR 文本；弹窗打开前停靠（`park_for_popup`，留 220px）、点击前验 `popup_hit_clickable`、关闭要验证、打不开补点一次；下拉结果先读 ComboBox 窗口文本；无组扫描预算 110 格/90 秒；rowcombo 接受列表标签；灰字段报 `param_uia_field_disabled`。ops 重标定 4 处（first_speeds / tree_support / overhang_speeds / ironing_top），校验器改以普查夹具判组名（在旧 ops 上报 4 处）。

**离线测试 `tools/test_param_engine_sim.py`**：48 项，新树全绿；同一份测试在 r3b 树（54fa243）上 16 项变红，其中 9 项是行为检查。第一次跑新检查时 7 项红，逐条核对全是测试自身的错（调到前面检查留下的桩、假页面滚轮方向写反而老检查靠第二方向碰巧通过、期望值算错、假句柄撞号）。

**验证顺序**：离线测试 → 普查探针（e80c899c：IsChild 属实、停靠生效）→ 一个最便宜的真实场景 by_object（b6bc43ae，SHADOW：停靠 4 格 → 弹窗 813–869 → 窗口文本 `By object`；business/path 两项 pass，保存件 `print_sequence='by object'`）→ queue19。

**queue19（r3c.1 = 0a7687d）10 个场景 2 过 8 败**（下表；第 3 个通过 by_object b6bc43ae 是上面的队前验证 run，不在表里；#270 f96dbc0b 是 r3 修后的单跑，见「续二」）

| 场景 | run | 结果 | 失败签名 → 定性 |
|---|---|---|---|
| feature_speeds (#271) | b1103170 | NON_GREEN | 6 个字段里 5 个对，`small_perimeter_speed` 存成 `50` 而期望 `50%`——ops 值写错 |
| accelerations (#274) | 43897d4d | **SHADOW** | 6 个值全对 |
| seam_wipe (#256) | 6b5ea183 | **SHADOW** | 5 个值全对 |
| speed_limits (#276) | 1e944276 | NON_GREEN | `layer height:0`：OCR 是客户区坐标、窗口矩形差 7px（最大化窗口的不可见边框），标题行排除差 1px 没生效 |
| filament_features (#284) | f27ba25c | NON_GREEN | 停靠多滚 1 格把行推出视口顶；且 ops 指向的行本身不对 |
| brim (#291) | 5a73aee3 | NON_GREEN | 同上；且目标文案 `Outer only` 不在弹窗里 |
| overhang_speeds (#264) | 90881c68 | NON_GREEN | 复选框走 `find_option_row`，只在单个 OCR 词里匹配，两词标签 `Detect overhang` 永远不中 |
| overhang_bridge (#272) | 7f9beea4 | NON_GREEN | 编辑阶段无报错，但四个字段只有最后一个落值（`overhang_3_4_speed=10`）——待查 |
| overhang_curl (#265) | c8225950 | NON_GREEN | 两行式标签的复选框居中在整行，距匹配行 15px > 容差 14 |
| fuzzy (#295) | 03c8d0ca | NON_GREEN | 目标文案 `All external walls` 不在弹窗里（实为 `All walls`） |

**弹窗普查**（`uia_param_census` 改为逐个打开全部下拉 ops 的弹窗：run 67690ed4、f1c5433b、40989dec、c814315c）：
- 真实弹窗行文本：Brim type = Mouse ear / Painted / **Outer brim only** / Inner brim only / Outer and inner brim / No-brim；Fuzzy skin = None / Contour / Contour and hole / **All walls**；挤出机 = Default / **1 PETG** / 2 PLA / 3 PLA / 4 PLA / 5 PLA；Interface pattern = **Rectilinear** / Concentric / Rectilinear Interlaced / Grid；Ironing type、Seam position、Wall generator、Gap fill、Top/Bottom surface pattern、Print sequence 的目标都在列表里。
- 真实行名：Support 页 `Filament for Supports` 组是 `Support/raft base` / `Support/raft interface`，`Advanced` 组有 `Interface pattern`；Multimaterial 的 `Filament for Features` 只有 Walls / Infill / Solid infill / Wipe tower——**没有支撑行**。
- **`WindowFromPoint` 不返回禁用窗口**：支撑未启用时 `Tree`、`Default` 底下是 393×270 的行容器；Draft shield 在 skirt loops 为 0 时同理。ops 里先勾 Enable 的顺序是对的，是普查孤立探测才撞上。
- 弹窗 OCR 默认 psm 3 会整行漏读（`1 PETG`、`5 PLA`），psm 6 才读全。
- 自绘值的弹窗空间不够时会向上翻转（fuzzy：弹窗在点击点上方）；ComboBox 式的弹窗（Print sequence）不翻转、直接开到任务栏下——两种弹窗行为不同。

**被推翻的推理（续）**：「Support 页点了没弹窗是 7px 坐标」——不是，是窗口禁用；「filament 行在 Multimaterial 页」——那组没有支撑行。

**r3d / r3d.1 / r3e（76e77d5、398ba7b、804a88f）**：OCR 与窗口矩形比较一律经 `client_origin`（标题行、组跨度、复选框、值定位）；停靠不再多滚一格；两词复选框标签走短语匹配；弹窗 OCR psm 6；值定位解析到行容器即报「该行是灰的」；两行式标签的控件在匹配行上下 15px 的窄带里找唯一一个；日志行缓冲（此前未 flush 的行乱序落盘，日志先后不可信）；ops 重标：brim、fuzzy 目标文案，feature_speeds `50%`，#279/#284/#287 改为 Support 页「启用支撑 → Support/raft base → PETG」（pilot 记入 `enable_support=1` 偏差），#281 改为 `Interface pattern → Rectilinear`。离线测试 49 项（r3c 树上 5 项红）。

**fa706g3 静态审查**：第一次派整批 diff（约 700 行），40 分钟预算用完没有产出；缩到弹窗相关的 4 个函数后闭环，报 3 处确定性缺陷全部采纳（屏幕外重开弹窗后 `cx/cy` 过期、重开失败后仍用已关闭弹窗的句柄、盲点循环只更新矩形不更新句柄），另指出「页面任意一行含目标文本就算成功」的校验是假阳性来源，已改为按目标值做词序定位。它对两行式标签的几何分析（控件居中于整行）与 overhang_curl 的实测一致。

## 续四：queue20、fa 第二条线、r4–r5.9（2026-11-23 21:08 – 24 日 01:35，GLM 5.4 总控）

**结论（截至 02:05，引擎 `3789b0b`）：参数族闭环 SHADOW 39/44（88.6%），GREEN 仍为 0。相对「续三」的 14 条新增 25 条：queue20 在 r3e 上 10 过；r5 之后 VM 再过 5 条（#258 #264 #272 #278 #293），fa706g3 第二条实体线过 10 条（#279–#287、#295）。未清 5 条都有定性，没有一条处在「不知道为什么」。** 口径以保存件为准：39 个场景各有至少一个 `release_verdict=SHADOW` 的收割 run，核对脚本逐个重开 3mf 比对 pilot 期望值（VM 29 + fa 10；fa 的 10 条另经 fa 上的 agent 用独立脚本复核，53 个键 0 不一致）。

**queue20（r3e = `804a88f`，26 个场景：11 过、15 败；line_width_all 跑了两次，共 27 个 run，业务失败不重试）**

| 结果 | 场景（run） |
|---|---|
| **SHADOW ×11** | brim #291（1e4dec5d）、speed_limits #276（32dff095）、overhang_curl #265（7dc4cabd）、feature_speeds #271（2aa82922）、skirt #290（282e8a85）、surface_flow #262（a7504d39）、infill_structure #269（540a8807）、jerk #275（4641e238）、wall_generator #260（7e59e22a）、single_wall_avoid #261（3727296c）、precision_comp #257（ecdef7a4） |
| NON_GREEN ×15（16 个 run） | 支撑类 5 个（support_filament a2d4a0f0、filament_features dad3c3c2、support_interface 30a605d1、material_advanced 6897a472、support_ironing 001573f1）与 spiral_vase f4a37c84、tree_support b82b416f、ooze_prevention fb7cb075、flush_options 0f98dac9、prime_tower eac5e090、raft 32d30aba：UI 操作阶段即抛协议错误；fuzzy 1193a356（目标文案不在弹窗里）；overhang_speeds 50798c59（四个值落进同一个框）；arc_resolution 0fe51b33（`gcode_actual_layer_step_mismatch`）；line_width_all 4149046c / e0905644 |

15 个失败里 13 个的签名是引擎或标签级，不是场景级（另两个是 #258 的判据与 #255 的夹具）。按「第二个引擎级证据就停」的纪律本应更早停；实际跑完了全部——换来的是一张完整的失败分布表，下一节按它逐类处理。

**fa706g3 第二条实体线**（用户明令「fa 那边直接做，不用那么小心」）：2.4.0 构建原位替换（2.3.5 留作 `Release_235_bak`）；资源从宿主拷贝后仍差 **325 个 Snapmaker 预设文件**（经 PS Direct 从客机拉回、哈希核对后补齐——第一次跑就因 `change_filament_gcode` 不同被判「改了无关设置」）；7 处「真实执行必须在 Hyper-V 客机」闸门改为显式放行 `ORCA_BB_ALLOW_TESTBOX=1`（与 dev 用的 `ORCA_BB_ALLOW_HOST` 分开，每个 run 写 `execution_host.json`，只计 SHADOW）；GUI 只经计划任务 `glm_line` 进交互会话（SSH 直跑会崩）；宿主入口 `C:\coil\vm_setup\fa_line\fa_run.py <场景>`，结果拉回本工作树的 `artifacts/windows_mcp_harvest/<run>/`。纪律见 README 第 6 条。fa 的检出与客机同步到同一提交后才跑（fa 上独立复跑离线测试与校验器：86/0、0 问题）。

**r4 / r4.1 / r4.2（`68537ab`、`9f0922c`、`6e12606`）**：两份 fa 静态审查与 queue20 的落实——全部标签候选一次扫描；编辑数不对即报 `survey_and_raise`；切片被拒时读红色提示条原文进错误；普查转储每页每一行（`ROWDUMP`），`tools/rows_from_census.py` 拼成行夹具 `tools/param_ui_rows_2.4.0.json`。**r4.1 自己引入一个回归**（浮点分支用了只在 rowcombo 分支定义的变量，NameError），r4.2 修并补了「rowcombo 之后再跟 float」的顺序测试。r4.2 加的 rowcombo 回读在提交版本里每次都抛 NameError（引用了没导入的模块），到 r5 才真正生效。Mac 的 5 个 commit（B1–B5）以 format-patch 搬回合并（`aedc4bf`）。

**queue21（`aedc4bf`，8 个场景 0 过——预期，跑的是修前引擎；每个都查到了原因）**

| 场景 | run | 失败签名 → 定性 |
|---|---|---|
| overhang_speeds #264 / overhang_bridge #272 | 210446b4 / d42cd1ed | `param_uia_field:Overhang speed:1<=field1` → 这一行是**一个标签、五个数值框纵向堆叠**（间距 27px，标签居中）；field i 应是自上而下第 i 个框 |
| raft #278 | be0664ae | `param_row:layer density` → 首层密度/扩展是 **Support 组**的行（`First layer density` / `First layer expansion`），Raft 组只有 `Raft layers` 与 `Raft contact Z distance` |
| flush_options #286 | 59ff697f | `param_checkbox:this` → `Flush into this object` **在全局配置里不画**（ConfigManipulation.cpp:886） |
| prime_tower #283 | aa451776 | `param_row:Stabilization cone apex angle` → 该行**只在 Wall type = Cone 时存在**（ConfigManipulation.cpp:858） |
| spiral_vase #293 | 49723134 | `main_window_modal_blocked` → 勾选后应用弹**自己的 Yes/No 对话框**；旧代码等的 `wait_popup` 只认下拉弹窗 |
| tree_support #282 | 1f23038c | `param_row:Tree support branch angle` → `Tree supports` 是**条件组**，Style 离开 Default 后才出现；限定在 Advanced 组的扫描在下一条带里 OCR 到了这一行却仍报找不到 |
| arc_resolution #258 | 56846c08 | 四个配置值全对；`gcode_actual_layer_step_mismatch` → 见下「层网格」 |

**r5 – r5.9（`6751f18`、`399f977`、`7410d45`、`b88f6ee`、`9e4b971`、`e931fa4`、`3789b0b`）**——每条都有 run 证据；离线测试 `tools/test_param_engine_sim.py` 从 59 项到 97 项（r5 的 86 项在 aedc4bf 上 8 项红，r5.5 的 88 项在 7410d45 上 2 项红；之后各版的红证只对新检查逐条做过）：

- 值控件按**枚举**找（该点下最小的带文本子窗口），禁用与否看 `IsWindowEnabled`。r3d.1 的尺寸判据在 fa 上把一个启用的 254×39 下拉框判成禁用（744a5451）。
- `field` 行按纵向堆叠取第 i 个框（210446b4 截图）。
- rowcombo 回读读**值**而不是标签行：值窗口文本 + 值区 OCR + 去色块后的 OCR 三路（fa 4ec54abd：带挤出机色块时整值区 OCR 为空，去色块后读到 `PETG`，而同样的裁切把普通值读成 `Yefault`）；并**锚定在点击的那一行**（fa e9071eba：刚改过的行是橙字加青色焦点框，整行被 OCR 丢掉，词组扫描落到下一行 `Fuzzy skin generator mode ~ Displacement`）。判定只看值（`on` 在 `ironing` 里面）。
- 勾选后的模态按**效果**找（主窗口被禁用——正是下一道 guard 会撞上的事实）。这个框是 **wx 自绘对话框**：类名 `#32770`，但 Yes/No 是 `wxWindowNR` 自绘按钮、另有一个 `htmlWindow`（d8cec0d4 首次打印子窗口）。此前三版分别按「Button 子窗口」「原生任务对话框 TDM_CLICK_BUTTON」「WM_COMMAND / 真实 Enter」去答，全部无效——客机还刻意让应用不进前台，真实按键根本到不了。现在：有带文本的 Button/wxWindowNR 子窗口就点它；原生任务对话框的梯子（TDM_CLICK_BUTTON → WM_COMMAND → 投递 Enter → 前台时的真实 Enter）留在后面。
- 负数：数值框会丢弃**孤立的 `-`**，`-100` 进去出来是 `100`（fa d134da1b，被 r4 起带符号的回读抓到；r4 之前同样的编辑会「通过」）；数字后再在行首补负号同样被丢，字段被提交成 +100（fa 9d2369fb）。改成打完数字后用控件自己的 Down 键一步步走到目标值（fa 0eb5a417）。
- ops 重标：raft（首层两行在 Support 组）、tree_support（`Tree supports` 条件组）、prime_tower（Wall type→Cone 设顶角→切回 Rib）、flush_options（去 `this`）、spiral_vase（答 Yes）、first_speeds（旧 op 一直靠「把组标题当行 + below」碰巧通过，r3 起引擎跳过标题行会回归；改为先按值锚定）。
- raft 的第二次失败（5a4728b6）：四个值都落了，**应用拒绝切片**——切片按钮灰着，红色提示条「Jump to tree support」：筏板不与**树状**支撑类型（夹具默认）同时生成。Type 在支撑未启用时是灰的，所以先启用支撑再把 Type 切到 Normal（#279 的配方），`enable_support` / `support_type` 记入 pilot 偏差。
- 校验器：条件行、N/A 用例、未普查的弹窗目标各成一张带证据的表（按 op 的首个标签键入，不按序号——raft 加了两个 op 后序号键悄悄失配），其余不匹配仍是问题；`tools/check_ops_red_proof.py` 证明七类坏输入各会翻红。41 个场景 0 问题 12 条备注。

**r5 之后两条线按场景分跑，不重复跑同一场景**

| 线 | 场景 | run | 结果 |
|---|---|---|---|
| VM | overhang_speeds #264 | aff4e62e | **SHADOW** |
| fa | fuzzy #295 | 6b8fa2d9 | **SHADOW** |
| VM | overhang_bridge #272 | cfd5b08f | **SHADOW** |
| VM | first_speeds #270（回归） | db7c08f3 | **SHADOW**（r5 无回归） |
| fa | prime_tower #283 | 2bacb634 | **SHADOW**（保存件 `wall_type=rib`、`cone_angle=15`） |
| fa | tree_support #282 | e946ad14 | **SHADOW** |
| fa | flush_options #286 | f0175fa7 | **SHADOW**（记偏差：`flush_into_objects` 保持 0） |
| fa | ooze_prevention #285 | 9d2369fb → 0eb5a417 | NON_GREEN（负号）→ r5.6 后 **SHADOW** |
| VM | raft #278 | 5a4728b6 → f5d76e39 | NON_GREEN（树状支撑拒绝切片）→ r5.6 后 **SHADOW** |
| VM | spiral_vase #293 | eab35b9a / 4d9731ec / 9ef272d0 / d8cec0d4 → 680d5426 | 四次 NON_GREEN → r5.9 后 **SHADOW**（记偏差：`wall_loops=1`、`top_shell_layers=0`、`sparse_infill_density=0%` 是应用自己改的） |
| VM | arc_resolution #258 | 55cc30bd | **SHADOW**（r5.6 判据修正后） |
| fa 队列 2（r5.1） | support_filament #279 / filament_features #284 / support_interface #281 / support_ironing #280 / material_advanced #287 | 0c8f604e / b9d0efa5 / 83cce033 / 51380cfe / d9df6fdb | **SHADOW ×5** |

**层网格（#258 带出的事实）**：夹具立方体是 **27.0 mm** 高（网格 −13.5…13.5）。非精确 Z 时切片器按 0.4 网格打 68 层、顶层打在 **Z 27.2**（网格上取整）——其它用例的「68 × 0.4 / 27.2」判据量的是这个上取整，不是模型高度。开精确 Z 后网格**正好收在模型高度**：63 步 0.4 + 5 步 0.36，最后 Z 27.0（56846c08 逐层实测）。`analyze_gcode` 要求等步距，所以 #258 不挂等步距判据，只证四个配置值 + 设置保持。

**被推翻的推理（续二，如实记录）**：(a)「回读用整带 OCR 即可」——刚改过的行会整行被丢；(b)「复选框后的弹窗 `wait_popup` 等得到」——它只认下拉弹窗；(c)「负号可以直接打进数值框」「数字后再补负号就行」——两次都被丢；(d)「这个框是没有 Button 子窗口的原生消息框」——连推三版（WM_COMMAND、真实 Enter、TDM_CLICK_BUTTON）各烧一个 run，第四次把子窗口类名打印出来才发现是 wx 自绘按钮；**日志里缺的事实先打印，再改代码**；(e)「27.2 是 68×0.4 的模型高度」——模型 27.0；(f)「两行式标签：标签一行、数值框在下一行」——Speed 页首行是组标题与首行同名造成的错觉，overhang 才是真的纵向堆叠；(g)「Max bridge length 在页面上没有行」——支撑启用后它在 Support 页的 Advanced 组，#263 失败是因为它在 Quality 页的桥接组里没有。

**未清 5 条（定性）**：
- **#255 line_width_all**：七个字段全部编辑成功，应用拒绝切片——「Line width too small」（run e0905644）：U1 的 0.8 喷嘴预设不接受顶面线宽 0.40。用例值与夹具机型冲突；要么给该用例换 0.4 喷嘴预设，要么记偏差改顶面线宽。
- **#294 timelapse**：`toggle_line("timelapse_type", is_BBL_Printer)`，只有拓岩机型有这一行，U1 上不适用。
- **#296 gcode_output**：`gcode_add_line_number` 是 `comDevelop`，只在应用的 develop 模式显示。可做，差两步：把 `user_mode=develop` 按场景送进客机 worker 的 profile 播种（`profile.seed_profile` 已支持 `conf_extra` / `ORCA_BB_CONF_EXTRA`，`agent_guest.py:62` 的调用没传），再在 develop 模式下普查一次 Others 页的行文本。
- **#288 / #289**：混色面板（`mixed_filament_*`），不在工艺参数页。

**两个靶机 agent（本段）**：
- **Mac**：第一步 B1–B5（4/5 原语）已合并（`aedc4bf`）。第二步的 60 分钟预算用完、没有回复，但成果留在 Mac 工作区；第三步（28 分钟、小步提交）接着做，4 个提交已搬回合并（`6cc9cdb`…`3a9ced7`）：`scroll_page` 已证（拖/点页面滚动条、窗口最大化；折叠图标与带光标滚轮无效）；`locate_row` 先滚动再定位；**`pick_combo` 在 macOS Orca 2.4.1 上已证**（Others / Special mode / Print sequence → By object，run 014004，行读回 `~ By object`；指针点击与 Down+Return 两次输入谁完成了选择尚未分离）；最小场景「Layer height 0.4→0.2」从保存的 3mf 读回 `layer_height='0.2'`。未证：「Detect thin walls」场景两次超时（Advanced 模式下 Strength 页滚过头后没认出 `Walls` 标题；修正已写、未验证、未提交），「Print sequence」场景未跑。Mac 口径，不计入 44 条。
- **fa706g3**：弹窗审查 3 处、行定位审查 D1–D8 均已采纳；对 r5 的定向审查 30 分钟预算用完没有回复（靶机日志显示它一直在工作到被取消）。随后它用自己写的脚本（`C:\coil\glm_line\verify_fa_shadows.py`：ast 静态解析 pilot、不导入仓库代码、在临时副本上注入 4 类问题验证会报）**独立复核 fa 线 10 条：53 个键 0 不一致**。
- 两次「预算用完没有回复」都是任务大于预算（第 28 条老坑），不是驱动问题；提示词要带 `TEAMMATE_LOOP_OK` 并要求小步提交——第三步照做后产物齐全。

<!-- xu5:start -->
## 续五：通宵并行段（2026-11-24 02:05 – 10:00，GLM 5.4 总控）

用户指令：「持续并行推进到早上十点」。四条线同时跑：VM 全量回归、fa706g3 探索与复证、两个靶机 agent 的小步派活；引擎开发放在独立的 dev 工作树里，不碰回归队列正在执行的主工作树。

**结论：（中途版）按仓内判据 41/44 闭环；合并后的引擎上 41 个场景各有 SHADOW；按前置条件做的两个夹具都已被应用加载并原样保存；前置条件夹具上的全族一轮进行中。闭环 ≠ 飞书三条预期——详见「夹具」「模型」两段。**

**口径（这一节起写死）。「闭环 SHADOW」只等于下面四件事同时成立：参数值逐键写进了重开后的 3MF、其它设置保持、切片成功并导出 G-code、层网格不变（多数用例）。它不等于飞书那三条预期结果都成立。** 飞书每条都有「1. 参数写入正确、切片成功并产出 G-code；2. …；3. …」：第 1 条对每条可驱动用例都核对了；第 2、3 条里被自动核对的只有——首层 Z / 步进 / 层数（#254 逐项核对；其余用例核的是「与基准一致」这个不变性）、熨烫路径条数与速度（#259、#280）、G-code 里的注释行数（#296）。各特征的速度值、E/mm、擦料塔几何、待机 / 预热温度、外形尺寸这些**没有自动核对**；夹具是 27 mm 立方体，不是飞书指定的小船 / 欧特克 FDM 测试 / 圆柱 / 球，喷嘴与预设也和前置条件不同（见下面「夹具」一段）。每条用例的判据面见 `python tools/param_oracle_surface.py`。

**计数（都由工具现算，不手数）**
- `tools/param_closure_list.py --ids`：按每个场景**最新**一次收割 run 的 verdict 计（此前按「曾有过 SHADOW」计，判据变严后会漏掉重开的用例）。在 `b45125c` 上：40/42 已闭环，未清 #294、#296（另 2 条 #288 / #289 没有界面控件，不在 42 条的表里）。
- `tools/rejudge_shadows.py .`：用**当前** pilot 离线重判每条的最新 SHADOW 保存件。在 `8dfae16` 上：41 OK、0 fail、1 跳过（#294 没有 SHADOW run）。

**VM 全量回归 queue24（引擎 `36cbb8c`，02:05–04:31）**：39 条已闭环场景各跑一次，39 SHADOW、0 NON_GREEN。共享路径（复选框、浮点、下拉、纵向堆叠、对话框）排在最前，前几条若出现引擎级失败签名就停队——没有出现。**queue25（引擎 `b45125c`，04:37–05:27）**：r5–r8 改过的共享路径、#255、#296、混色探针共 14 条，12 SHADOW；gcode_output NON_GREEN 是当时强化过的判据（下文），mix_census 探针按设计以 `param_census_done` 收尾。**queue26（引擎 `8dfae16`）**：gcode_output 用定稿的 pilot 在客机复证，SHADOW。

**#255 线宽全家**：真规则是**线宽必须大于层高**（`Print.cpp validate_extrusion_width`，报「Too small line width」），与喷嘴无关。用例值是按 0.2 层高写的，而夹具是 0.4 层高。适配：ops 先把层高设 0.2（记偏差），层网格按实测钉为 134 层 / 顶 27.0（fa `4499d0c4` 首跑、`7c434f38` 带判据复跑、客机 `5e7227e0`）。

**#296 G-code 输出：三个预期效果只有一个在 U1 上成立——带两条产品限制闭环**
- 行只在应用的 develop 模式出现。做了按场景播种：`SCENARIO_CONF` → `profile.seed_profile(conf_extra=...)`，worker 把它写进报告（`6c3fde0`）。
- 白跑了两次「develop 普查」（`17d2db91`、`2adcf5cd`）：键放在配置顶层，应用读不到，以 **simple** 模式启动（五个页签、摘要行、页面不滚）。键在 `app` 段里（看应用自己 dump 的 conf 确认），改后（`887ee6d`）真普查 `dc96eb66` 看到 `Add line number`。
- develop 模式下页面的 Advanced 开关被禁用、旋钮不画成开，`ensure_advanced` 会去点它并把应用带回 advanced：develop 场景不碰它（`process_panel.ADVANCED_SWITCH`，`bdd4e19`）。
- 首跑 `a9cce05e`：三个复选框都落了，文件名格式存成 `…gcode\n`——多行文本框里回车是换行。改成失焦提交，回读整段文本（`53679c3`）；`6c091f2e` 按值判据 SHADOW。
- **然后核对了 G-code 本身。** 飞书预期 2 是「G-code 包含注释、行号和对象标签」。导出的文件 6100 多行里行号 0 行、`EXCLUDE_OBJECT` 0 行（fa `6c091f2e` / `908ca2d`，客机 queue25）；pilot 加上断言（`45bea4d`）后该条转为 **NON_GREEN `param_gcode_line_number_missing`**（客机、fa `53693be9`）。
- **为什么没有**（fa agent 在 2.3.5 源码上定位，`main@c98c6d3`；宿主 2.4.1 源码树一致）：`gcode_add_line_number` 唯一的调用点在 `BackgroundSlicingProcess::export_gcode`（`:901`），只有 BBL 机型会走到（`process_fff` `:246-252`），其它机型走 `finalize_gcode`，原样拷贝文件。构建本身也印证：导出头里没有只给 BBL 写的 `; model label id:`。`EXCLUDE_OBJECT` 标签由 `exclude_object` 控制（2.3.5 树 `GCode.cpp:6595`；2.4.1 树 `:9377`），它默认是 0——#297 那次 run（`1b0c899d`）里它是开的，有 137 行。「注释」是行尾注解：开了 `gcode_comments` 的 run 有 3028 行命令带 ` ; …`，默认 run（`2f5c45ad`）只有 2 行；只数以 `;` 开头的行看不出差别（2002 对 2003）。
- 排除掉的解释：导出后文件会被重写（让应用导出后多留 40 秒，`ORCA_BB_POST_EXPORT_WAIT`，文件没被重写、仍是 0 行号：fa `34ebb1ac`、`231703fe`、`99552935`）；重开会话不在 develop 模式（两边都放进去，`908ca2d` 仍没有）。
- pilot 定稿（`dae0b2d`）：断言行尾注解的行数 > 1000（`param_gcode_verbose_comments_missing`）；行号与对象标签作为实测值记录、不判，并写明这是本机的两条产品限制。离线对 `908ca2d`、`231703fe` 的导出件核过；合并后各复证一次：客机 `3ea6602a`、fa `5b302619`，都是 SHADOW（行尾注 3049 / 3051 行，行号 0，对象标签无）。按「最新一次 run」计，可驱动的 42 条里 41 条闭环。

**#288 / #289 混色：不可界面驱动。** fa agent 在 2.3.5 源码上查到 9 个键里只有 `mixed_filament_definitions` 有编辑控件（Add Mix 对话框），其余 8 个由 `update_mixed_filament_panel` 从工程配置读出再原样写回，带 Bias 数值框的行编辑面板被无条件 `Hide()` 加 `#if 0` 关掉；宿主 2.4.1 源码树一致（`Plater.cpp:7387-7390` 读、`:7463-7470` 写回）。2.4.0 构建没有源码，于是写了探针 `uia_param_mix_census` 读构建本身（`474e28b`；fa `15af746c`、客机 `243a59fa`）：侧栏「Color Mixing」一条混色，Options 菜单 = Edit / Merge with / Delete；Add Mix 四个页签只有耗材选择、混合比、Cycle 图案、Match 颜色、渐变，没有偏置 / 层高 A-B / 渐变模式 / 点彩 / 塌陷 / 凹陷。证据 `docs/runs/evidence/mix-census-2.4.0-2026-11-24/`。这两条不写参数场景模块。

**引擎 r6–r10：两轮 fa 定向审查的落实，加一条 fa 线自己暴露的**（每轮=三个函数、四组具体问题、18–20 分钟，都闭环）
- r6（`d1d244b`，审 `36cbb8c`）：对话框按类名 `#32770` 加属主选、只答 op 声明的那个问题（`dialog` 键）、答完等框关并等页面稳定；下拉回读整词匹配（`Rib` ⊂ `Rectangle`、`Rectilinear` 是同弹窗「Rectilinear Interlaced」的首词）、值窗带宽 ±10 并校验高度、锚点行 OCR 不认标签就不信；负数走步先实测步长，不在网格上 / 不走 / 没到目标就抛错不提交。
- r7 / r7.5：对话框的 Yes / No 是**自绘**的 `wxWindowNR`，不是 Button 类——按 Button 子窗、`TDM_CLICK_BUTTON`、`WM_COMMAND` 三种做法各烧掉一次 run 之后，先把子窗类名打印出来才看清（r9 `b5ef5db`）。
- r8（`639c2e6`）：复选框一勾应用立刻弹框时，主窗口被禁用、后续点击被吞、框不再画成勾——点击后主窗口被模态接管即视为已翻转（fa `6da8ec2c` 暴露；客机 `680d5426` 是时序运气）。
- r9（`b5ef5db`，审 `53278b8`）：点击**之前**主窗口已被别的模态禁用的不算翻转；对话框答 No 后应用会把值改回去，`run_ops` 在页面稳定后重读复选框（`param_checkbox:…:reverted`）；焦点挪不出文本框即报错；多行与否由控件的 `ES_MULTILINE` 决定，不看值里有没有数字。
- r10（`3ca4f32`，`param_case_lib._park_field`）：堆叠字段被页面底边裁掉时，Win32 仍报它可见，`uia_set_float` 选中它、`ui.edit` 拒绝点击——fa 的窗口比客机矮，「Overhang speed」第 4 个框正好在那里（fa `4491e40` / `7e7fd61`，#264 / #272 第一次在 fa 上跑）。现在先给这个框留 12 px、下滚正好够的格数再重定位，最多三次。fa 复证：`188053e` / `c2368e86` SHADOW，对照 speed_limits / surface_flow 仍 SHADOW。
- 离线测试 97 → 158 项（aedc4bf 上 8 项红；其后各版逐检查做过红证，r10 的新检查把 `_park_field` 停掉后 4 条翻红）。单测这一夜没跟着跑：`unit_tests` 里有两条从 r9 / develop 模式那两次改动起一直是红的（收据多了 `committed` 键、重开会话多了 `conf_extra`），06:46 才发现并修掉（全量 1450 过 1 跳过 3）。

**fa706g3 线**：探索与复证都在 dev 提交上跑。#255、#296 首次通过在这条线；r6 后复证 fuzzy / ooze_prevention / prime_tower / gcode_output（`4a763b19` / `c68a0b93` / `e198278f` / `6c091f2e`），r8 后复证 spiral_vase / wall_thin / overhang_curl（`442b1e93` / `cdae6424` / `a01b5667`），r9 后复证 spiral_vase / wall_thin / overhang_curl（`38ff873f` / `ded39e9c` / `54c6c6f5`，三个 SHADOW；日志里有「模态后视为已翻转 → 答 Yes → 框 0.2 秒后关闭 → 复选框回读为 True」）。合并到 `8dfae16` 之后又跑了一轮：合并到 `8dfae16` 之后又跑了一轮：第二样本 5 条全 SHADOW（gcode_output `5b302619`、spiral_vase `a96e23f4`、wall_thin `4cc4512c`、overhang_curl `391a927d`、layer_pair `819b402a`）。全族回归里 fa 跑另一半 13 条：11 条 SHADOW，overhang_speeds `4491e40` / overhang_bridge `7e7fd61` 第一次在这台机器上跑就死在 `edit_outside_client`——fa 的窗口比客机矮，「Overhang speed」第 4 个堆叠框落在页面底边之外（见 r10）。

**夹具与飞书前置条件不一致（本段新查清，未解决）**。44 条的前置条件原文是「固定U1 0.4mm喷嘴、PLA耗材和0.20mm标准工艺预设」；夹具 `fixtures/agent_layer_cube.3mf` 是 0.8 喷嘴 ×4、「0.40 Standard」、1 号挤出机（预设名 Generic PETG）打印、`filament_max_volumetric_speed` 10 mm³/s。后果有两条，都已实测：#255 的线宽被应用拒绝（真规则是线宽大于层高，已按「先设层高 0.2」适配并记偏差）；各特征的挤出速度被体积速度上限压在约 30 mm/s（0.82 × 0.4 mm 的线，10 ÷ 0.328），预设里写的 100 / 150 / 200 mm/s 在导出件里是 F1865–1870，飞书那类 F1800 / F2400 / F9000 的数字大部分看不到——只有低于上限的首层速度可见（#270：墙 F1800、填充 F2400）。读各特征实际进给的工具是 `tools/gcode_feature_speeds.py`（`91c9b0c`）。**按前置条件做的夹具（本段新增，客机与 fa 都已加载过）**。- `fixtures/feishu_std_cube.3mf`（`tools/build_feishu_std_fixture.py`）：同一个立方体，四个喷嘴 0.4、工艺「0.20mm Standard @Snapmaker U1 (0.4 nozzle)」、耗材全 PLA（1 号 Generic PLA、2–5 号 Snapmaker PLA Basic）。值取自宿主 2.4.1 源码树的厂商预设，沿 `inherits` 链展开；展开器先拿现有夹具验过：0.8 链能复现立方体配置 298 个共有键里的 286 个（差的 12 个是应用管理的键和两版预设之间的差异），不沿链展开只能复现 173 个（红证）。预设有而立方体夹具没有的量：首层 0.25（厂商预设自己的值）、线宽 0.42、内墙 300 / 外墙 200 / 填充 270 / 顶面 200 mm/s、首层 50 mm/s、体积流量 12 / 15 mm³/s——上限约 178 mm/s，飞书 #276 写的「受体积流量限制到约 178mm/s」就是这个预设的数。- 应用里的实测：三个「只保存、不改任何设置」的对照（`uia_param_save_only` / `uia_param_std_save_only` / `uia_param_shapes_save_only`）。立方体夹具：SHADOW，59 处原始差异全是序列化迁移（速度向量变成列表、预设名加上 `(fixture.3mf)`、版本 2.3.6→2.4.0）加应用新增的 8 个键——此前评审说的「每次保存另有 35 个其它键变化」到此有了对照：不是设置被改。前置条件夹具：应用按夹具里的值加载（0.2 / 首层 0.25 / 0.42 / 0.4×4 / 体积流量 12,15,15,15,15）。- 接线：场景名加后缀 `_std02` 就是同名用例在这个夹具上跑，45 个参数场景都有孪生（同一套 ops、pilot、页签、分派，只换夹具；全名留在 scope.json 和报告里）。耗材弹窗的行写的是「1 PLA…5 PLA」，所以把 PETG 目标换成「1 PLA」；层网格按夹具登记，新夹具先只记录不断言；对照场景不进 TRIALS，闭环数不受影响。- 两次返工（如实）：① `different_settings_to_system` 一开始按 2.4.1 预设算成 9 个键，而应用给这个工程写的是只有 `mixed_filament_definitions`——第一轮 `_std02` 全部死在 `pilot_dirty_manifest_out_of_scope`；② `top_shell_thickness` 预设里写 "1.0"、应用存成 "1"——第二轮的基线死在这一个键上。两处都改成照应用实际写出来的内容；第三轮之前拿应用上一轮存下的配置离线比对过：已知迁移之外 0 个键不同。- `_std02` 一轮（42 个场景各跑一次，VM 与 fa 分跑）：进行中（07:55 时 13 条里 11 条 SHADOW；layer_pair_std02 死在按立方体写死的 #254 驱动 `script_layer_fields_not_as_expected`，support_filament_std02 死在 fa 上弹窗第一行 OCR 没读出「1 PLA」）。已经能说的：#273 其它层空驶 F18000、#270 首层墙 F1800 / 填充 F2400 与飞书一致；#271 的 F6000 / F9000 出现了，但 27 mm 立方体的层时间太短，冷却缓冲把大部分移动压到 F3747——飞书用的模型是小船。- **多特征盘** `fixtures/feishu_shapes_plate.3mf`（`tools/build_shapes_fixture.py`）：立方体 / 圆柱体 / 搭桥 / 悬垂台阶 / 第二个立方体（3 号挤出机），间距不小于 20 mm，配置沿用立方体夹具的；后缀 `_shapes`。网格离线校验过（10 个壳全封闭、朝向一致、体积与设计一致；33 个单测，24 种坏输入被拒）。应用打开它、切片、导出、保存，设置全部保持（客机 `5ba2e343` SHADOW）：导出件里有 19 次换刀（T0 / T2）、擦料塔 75 段、桥 5 段、悬垂墙 16 段——飞书那些依赖换刀 / 擦料塔 / 桥 / 悬垂的行，在这个盘上才有东西可看。`_shapes` 孪生尚未跑。

**模型也不合前置条件（实测）**。飞书每条都指定了模型（圆柱体 / 小船 / 欧特克 FDM 测试 / 斯坦福兔子 / 文字浮雕 / 立方体复制成 2 个…），夹具是单个立方体。把 41 条最新闭环 run 的导出件逐个读了一遍（`tools/gcode_facts.py`、`tools/feishu_expect_facts.py`，`040b661` / `f557681`；对照表 `docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24/cube-fixture.txt`）：
- **看不到效果的**：支撑族 5 条（#277 / #279 / #281 / #280 / #282）的 G-code 里没有支撑路径——立方体没有悬垂，应用不生成支撑（只有筏层 #278 生成了支撑与界面：71 层、顶 29.2）；#258 挤出圆弧 0 条（没有曲线）；#263 没有桥；#271 其它层的外墙 / 内墙 / 填充 / 顶面仍是 F1864 / 1870 / 1864 / 2543；#264 / #272 / #265 的悬垂档速度没有悬垂可跑；所有 run 都只用 T0 打印，换刀映射（#279 / #284 / #287）与擦料塔（#283）无从观察；#292 / #297 只有一个对象。
- **能看到、且与飞书一致的**：#273 其它层空驶 F18000（飞书 ≈18000）；#270 首层外墙 / 内墙 F1800、首层填充 F2400（飞书 ≈1800 / ≈2400）。#270 的首层空驶读到 F45000，不是飞书的 ≈9000。
- **能看到效果、但没有写成断言的**：#290 裙边、#291 Brim、#278 筏层、#295 绒毛（外墙移动数从 244 涨到 3400 以上）。
- 其余各条的预期 2 / 3 在这个夹具上没有被核对：判据面里只有「值写入 + 其它设置保持 + 层网格不变」。

**两个靶机 agent**
- **fa706g3**：两轮定向审查（上面 r6、r9）；文档数字审计——对照固定提交 `36cbb8c` 找出 23 条过期快照、自相矛盾、缺复算入口的陈述，已照改（`59862c1`：每处快照标日期与现值，#296 / #294 的旧结论就地更正，queue19 改为 2 过 8 败加队前验证 run，Checkpoint 不再指向 11-21 停更的表，复算入口写进文档）；#288 / #289 可行性调研（上面）；#296 行号 / 对象标签的源码定位（上面）。
- **Mac**（Mac 口径，不计入 44 条）：B7——`pick_combo` 归因分离（仅指针 / 仅按键各一次都能完成选择）、thin-wall 与 print-sequence 两个最小场景通过；B8–B11——用宿主导出的平台无关用例表（`tools/param_cases_export.json`，42 条）跑真实用例 `param_case.py --case`：**#254 layer_pair（`034408`）、#266 wall_thin（`035959`）、#273 travel_speed（`045829`）在 macOS Orca 2.4.1 上通过**。第九步把定位改成「一屏读一次、全部候选一起判」（travel_speed 从进入 op 到命中行 52.8 秒）；其余四条未证明，卡点都在定位：surface_flow、speed_limits 的组标题被 OCR 读在 x=26–28 而阈值是 <26；precision_comp 的 `scroll_to` 在组标题刚上屏就停；arc_resolution 的 op0 点了单元格但效果没记上；三条都是我给的整条用例保险丝先熔断。第十、十一步：定位改成按「列左缘有没有折叠符号的墨迹」判组标题（离线重放 24/24）、保险丝按 op 分（150 秒 / 整条 420 秒）、每个 op 结束就落盘、「组标题滚出页面后行如何归属」作为单独一处改动（三个 run 的读数重放 36/36）进树。结果：**7 条里 6 条在 Mac 上 PASS**（layer_pair `034408` / `064408`、wall_thin `035959`、travel_speed `045829` / `064719`、speed_limits `061300`、surface_flow `062702`、arc_resolution `064139`），precision_comp 未证明（`063651`：`X-Y hole compensation` 的值是 0，OCR 在那一行读不到数字）。第十步中途它自己停下来问了我两个问题（多加的一条 carry 规则、每个 op 的保险丝额度）——我让它撤掉没要求的改动、按 150 / 420 重定；那一轮的回复文本因超预算丢了，结果是从靶机上的提交里读的。16 个提交已搬回（`451258b` … `104e91e`）。

**合并与同步**：dev 分支（`codex/glm-dev-20261124`）在回归队列排干后快进并入主线两次——`36cbb8c..b45125c`（34 个提交，04:40）与 `b45125c..8dfae16`（16 个提交，05:28），每次都推送、客机 bundle 快进、fa `fetch` + `checkout --detach`（主线每次只快进）。此后又有三次：`8dfae16..513f5d8`（夹具与 `_std02` 接线）、`..6c9ea57`（清单、详情上限、多特征盘与 `_shapes`）、`..8716285`（数字写法）。

**被推翻的推理（续三）**：(a)「Line width too small 是 0.8 喷嘴的限制」——是层高；(b)「user_mode 放配置顶层」——在 `app` 段，两次普查白跑；(c)「重开会话不在 develop 模式所以没有行号」——两边都放进去仍没有；(d)「#296 已闭环」——只核了配置值，核 G-code 就重开；(e)「闭环 = 用例通过」——只等于本节口径那四件事；(f)「导出后文件会被重写、行号会补上」——多留 40 秒也没被重写；(g)「对话框的 Yes / No 是按钮」——是自绘窗口，三种做法各烧一次 run；(h)「夹具的 `different_settings_to_system` 可以按预设树算出来」——应用给自己写的是另一个，第一轮 `_std02` 因此全部失败；(i)「预设里的数字照抄进工程配置就行」——应用把 "1.0" 存成 "1"；(j)「每次保存会改掉 35 个其它设置」——对照 run 证明那全是序列化迁移。

**未清 3 条（定性）**：#294（Timelapse 行仅 BBL 机型有）；#288 / #289（8 个键没有界面控件，只能随工程或预设载入）。#296 已闭环但带两条产品限制（行号、对象标签在 U1 上不生效）。
<!-- xu5:end -->
