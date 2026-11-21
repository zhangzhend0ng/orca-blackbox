# GLM 总控扩样批次 2026-11-21

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

## script 轨道（无模型复验，HEAD=bf108f7/ceaf295）

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
