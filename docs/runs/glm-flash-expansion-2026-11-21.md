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
