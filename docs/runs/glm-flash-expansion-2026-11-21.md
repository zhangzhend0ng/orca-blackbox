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

**已闭环 3/5**（全部 SHADOW：参数写入+保持项+冻结重开+G-code 排程）：
- **#266 墙圈数与薄壁** `05dd9020`（168.8s）：wall_loops=4 + detect_thin_wall=1，68 层保持。
- **#267 外壳层数与图案** `f324120d`（185.2s）：top=5/bottom=3 + concentric/rectilinear 双图案切换。top_color_penetration_layers 缺席为记录的口径缩减。
- （#254 见前段）

**打通的共享能力**（后续 39 条待实现用例直接受益）：行标签是 OG_CustomCtrl 绘制（无 HWND，census f5acdb1a 实证）→ 落地"OCR 短语找行 + 枚举 Edit/ComboBox 按行 y 配对"引擎（param_case_lib + param_combo_row）；修复 4 处 `EnumChildWindows` 少传 lparam 的宿疾（含 hybrid 标签增强自 a4a53a6 起被静默降级的事实——bottom_strength 通过实为模型自选对，先前"标签修复闭环"归因有误，予以更正）；预设脏清单键 `different_settings_to_system` 的合法规则。

**在攻 2 条**：#268（Gyroid 在图案弹窗第 2+ 页，滚动投递未生效）、#259（熨烫组 Speed 行 OCR 未中）。失败 run 全留证据。


## 飞书补充段终态（2026-11-22 08:0x）

**补充用例 3/5 SHADOW 独立通过**：#254 层高组合（`95cd45f5`）、#266 墙圈数薄壁（`05dd9020`）、#267 外壳层数图案（`f324120d`）。

**两条在攻、精确归档**：
- **#268 填充组合**（5 跑：9866d291/79ca1e8c/ce169b74/7968a6db/a8837dcc/08f6904b/96c325d3）：密度/方向/重叠/Gap fill 全链已通，唯一卡点=图案弹窗中 **Gyroid 在列表深处且自绘弹窗滚动回弹**（真光标轮与 PostMessage 轮均不累积；列表可见页恒从 Aligned 起）。下一步：专项探针（拖动弹窗滚动条或逐行小步轮+沉降）。
- **#259 熨烫组合**（60237e59/7eadbe35/a3fd0bff）：组合切换已通、Flow/Spacing 为目标值故跳过编辑；卡点=Topmost 选后页面重建中 **Speed 行的绘制标签未OCR命中**（Speed/Ironing speed/speed 三变体全空）。下一步：重建后带 band 打印定位真实标签。

**共享引擎沉淀**（供剩余 39 条直接复用）：行定位（OCR 短语+多词）→ 控件配对（Edit/ComboBox 枚举按行 y，侧栏恒在画布左）→ ui.edit 已证提交链；弹窗选取（捕获+OCR+点击+容错匹配+真光标轮）；脏清单规则；变更集注册表。全部带失败 run 实证注释。


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
- 补充路线 44 条进度：**已闭环 4/5 → 5 项在库可攻**（#254/#266/#267/#268 + Mac 侧口径）；fa 新 authored 7 条（#276-279/#292-294）注册待跑。

**合并**（宿主唯一合并点）：fa 分支（诊断+7 pilot+物理首跑，b4fd7d7）+ Mac 分支（runner 移植+签核表，6dc02a7）均并入本分支并推送；agent 分支 origin 侧同步（codex/mac-author 代理推送；fa 中转检出接力）。

**下一批**：#259 combo 提交步 band 校准；#270 复跑；fa 7 条 authored 首跑；租约释放失败根因（runner 异常路径不释放）。


## 续会话（2026-11-22 22:00–23 日 00:25）：#259/#268 双卡点全灭

- **#259 熨烫 `073f086f` SHADOW**：补充路线 **5/5 全闭环**（#254/#259/#266/#267/#268）。收敛链（六轮实证迭代，每轮失败即修）：①combo 元组未解包静默吞错→解包 raise；②find_option_row 滚深 6→12（"lroning type ~ No ironing" 行入 band 但双词值永远匹配不上单 OCR 词）；③词序定位元组 ("No","ironing")+单词 popup target "Topmost"→combo 提交成功、Ironing 组六行重建；④Speed 页行 OCR "lroning"（I→l）需单词包含变体 "roning"（前缀匹配救不了）；⑤编辑值序列化为单元素数组 ['60']→make_verify+inspect_preserved_settings 双处规范化；⑥**键名错位**：分析器返回 ironing_xy_e_moves 而判据读 ironing_moves（恒 0，从未被熨烫用例触发过）。
- **fa 作者链首验**：#277 support_basic `91678bcb` **SHADOW**（agent 编写→宿主审查合并→VM 首跑一次通过）。
- fa B2 闭环（04fa1ff）：第二批 7 条（#255-257/#260-261/#272-273）夹具实测键名零偏差+四方注册断言；已合入主线 54582a9。**fa 累计 authored 14 条**。
- Mac A2 闭环（5c503ca，blocked 精确归因）：wall_loops 控件在硬虚拟化 outline 未物化区、该页所有滚动通道失效、Mac build 预设行无 edit 图标；修正两处上轮误判（AXValue/AXHelp 可读、扁平页滚动箭头有效）；解锁三路径=屏幕录制 TCC/Automation TCC/上游 AX 补全。
- queue9 其余留证：speed_limits/raft/support_filament/by_object/spiral_vase/timelapse 六族 band 证据归档待校准；first_speeds 三度被陈旧租约楔（unlock 前置未覆盖其场景，租约释放根因仍未修——下一批首项）。
- 验证器/引擎七项修复全部入主线（a9bcb6f→…→073f086f 前共 5 提交），#259 收敛链本身即引擎硬化史。


## 九小时续航会话（2026-11-23 00:25–08:10，GLM 总控）

**SHADOW 净增 +4：#257 精度补偿（8ff22123）、#273 空驶速度（3c1ab0d1）、#297 排除对象（01163442）** + 早段 #259。补充+参数族累计闭环 **8 条**（#254/#257/#259/#266/#267/#268/#273/#277/#297 计 9——含 fa 作者链 3 条：#277/#257/#273 + fa B4 1 条 #297）。

**引擎级修复（根因三连）**：
1. **双向滚动**（b7c11f8）：编辑提交后面板重建、滚动落点随机（983bab81 从页底起搜）——短语搜索改「下 12 轮 + 回上 26 轮」。line_width 因此全链至 save、by_object 因此通过 combo。
2. **租约陈旧接管**（99b5d6d）：锁内写 PID、获取冲突验活接管——异常路径不释放锁的楔子根因之一。
3. **combo 元组解包**：run_ops 不再静默吞 set_combo_by_popup 失败（#259 六轮收敛链首环）。

**fa706g3 四批全闭环（B1-B4）**：**累计 authored 29 条 + 2 条混色族归因**（mixed_filament_* 无参数页行，需 mix 引擎链）——飞书 44 条参数族全部入库或归因。作者链首验通过率 4/29 首跑 SHADOW（#277/#257/#273/#297），其余留 band 证据分层校准中。

**Mac A2/B2 闭环**：面板寻址 blocked 精确归因（硬虚拟化 outline+滚动全灭+Mac build 无预设 edit 图标；AXHelp 可读/滚动箭头有效两误判修正）；写回工单 216 行对账（可立即写回 6 行 SHADOW 口径、待首跑 21+、维持 189）。

**queue14 终态（23 场景 40 run）**：1 SHADOW + 22 留证。失败分类：参数行/标签族 9、checkbox 状态回读 5、file_toolbar_missing 3（ESC 重试已加未验证）、楔 3、slice_button_unavailable 2、模态 1。skirt/timelapse/arc_resolution 执行完成但验证未过（终层校准）。

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
- **Others 页没有 `Add line number` 行**。G-code 输出组整组是 Reduce infill retraction / Verbose G-code / Label objects / Exclude objects / Filename format；对 163 张帧裁图做不带过滤的离线重读，`line number` 零命中。VM 2.4.0 的全页扫描同样没找到。**#296 的行号操作不在工艺参数页**，属用例范围问题。
- **Others 页没有 `Timelapse` 行**（同法零命中）。#294 延时摄影不属工艺参数页。
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
