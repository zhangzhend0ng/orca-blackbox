# V3 原生 AI 迁移台账（GLM 总控 · 2026-11-21 批次）

可续跑的唯一权威台账。分母以 `cases.py` + `tools/check_registry.py` 冻结；旧业务判据以 `BLACKBOX_CASES.md` 与各用例脚本头为准（本表不复述全文，只存一行业务目标与判据指针）；原生场景以 `harness/native_matrix.py` SCENARIOS 为准。恢复流程见文末 checkpoint。

## 冻结分母（2026-11-21 02:20 实测 check_registry PASS）

**89 条登记 | regression=74 smoke=4 other=11（9 启用专项 suite=None + 2 禁用）**
- 禁用（保留分母、不计启用）：`m1b_maa`（引擎实验，MaaFw 注入已判死）、`m2_perf_showcase`（显式 Hyper-V 性能演示，独立 perf 轨道）。
- 手工/外设依赖与历史实验：m7k_flush_options（P0 PARTIAL，需冲洗选项面板读回）、m4e_mixing_paint（涂色 gizmo 部分降级）、m3s_mixing_hover（hover tooltip 降级）——判据降级原因见 BLACKBOX_CASES.md 对应行，不因迁移改变。

## 批次环境登记

| 项 | 值 |
|---|---|
| 执行分支 | `codex/glm-flash-expansion-20261121-0217`（自 `codex/orca-integration@44034f8`） |
| 开始 / 截止 | 2026-11-21 02:17 / 08:17（收尾窗口 07:37 起） |
| 客机 | win11-test（DESKTOP-NVS6QT4），relay=宿主提权通道，suite Ready，无孤儿，KVP 关闭但 host_guard BIOS 兜底（06d2257）实测通过 |
| v3 客机检出 | `C:\coil\orca-blackbox-v3-r1`（software_testing@534cfee，clean；本轮 bundle 快进到本分支 HEAD） |
| SUT | guest `C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe` SHA256 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`（2.4.0） |
| 模型/路由 | ZCode 原生 app-server → Snapmaker `new-provider/glm-5.3-flash`（Anthropic 协议）→ Windows-MCP 0.8.9 UIA 优先 → win11-test；逐 run 以 host.json provider/model/toolset 收据核验 |
| 三份 UIA 门禁收据 | Save As `d7299035e33b80969e0064a8d9b3e4fc` · wx 层高 `bfd5c93af9571ba3ddc53f7099d7e407` · ImGui 画布 `52a21e14b5e0456bf5e965cb98970cf4`（2026-11-18 通过，源 fcfb0f/ee84a61/6b3bfba） |

## 状态词汇

`native-SHADOW(hist)` 历史独立通过（旧源，需本 HEAD 复验才计入本批）；`replay-ok` 无模型回放通过；`adapted` 场景已登记未跑；`gap-cap` 缺 UI 能力；`gap-neg` 负例缺拒绝合同；`blocked` 有具体阻塞；`off` 禁用/perf 轨道。首轮与复验分列（复验=同场景新 run ID 标 re-）。

## F1 启动/页签/工程基本操作（9）

| ID | 业务目标（旧判据→BLACKBOX_CASES.md） | 原生映射 | 状态 |
|---|---|---|---|
| m0_boot_check | 启动→定位→截图→关闭冒烟 | 每个原生 run 准备段（agent_session 启动链） | native-SHADOW(hist)·隐含 |
| m0_anchor_health | 锚点模板健康自检 | 模板层属旧视觉路线；UIA 路线无模板依赖 | n/a（路线差异，登记不改） |
| m1_minimal_loop | tab 切换闭环（消息注入） | tab=自绘；UIA 页签切换未登记 | gap-cap（页签 UIA 合同） |
| m1b_maa | MaaFw 引擎实验 | — | off（禁用） |
| m7a_boot_shutdown | 启动/退出（#7/#8） | 原生 run 启动+停输+自然退出即全链 | native-SHADOW(hist)·隐含 |
| m7b_new_project | 新建项目（#9） | fixture_cold（fresh profile 工程） | adapted |
| m7t73 | 新建项目（主流程模板） | 同上 | adapted |
| m7t83 | 新建项目导入模型 | bound_model_move 准备链 | native-SHADOW(hist)（4 模型试点 11-19） |
| m3i_view_menu | 视图菜单切换相机视角 | 菜单栏 UIA Invoke + 视角判据未登记 | gap-cap |

## F2 导入、预设、工艺与切片（16）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m2_slice_chain | 切片业务链（fresh profile） | 每个原生 run 独立重开+重切段 | native-SHADOW(hist)·隐含 |
| m7c_import_stl | STL 导入（#11） | bound_model_move（STL 输入） | native-SHADOW(hist) |
| m7d_import_corrupt | 损坏导入优雅失败（#12） | 错误弹窗读回合同未登记 | gap-neg |
| m3c_corrupt_3mf | 损坏 3mf 加载失败 | 同上 | gap-neg |
| m3e_preset_switch | 预设切换→gcode 头跟随 | 预设下拉自绘+预设名读回未登记 | gap-cap |
| m5a_preset_cycle | 预设级主流程 | 同上 | gap-cap |
| m5b_quality_params | Quality 页参数主流程 | uia_hybrid_layer / uia_replay_layer | native-SHADOW(hist)+replay-ok |
| m5c_strength_infill | Strength 页参数主流程 | uia_hybrid_layer_strength / 壁环数 | native-SHADOW(hist)（f65ba49e 11-18 目标式） |
| m5d_support_enable | Support 页参数主流程 | Support 页 UIA 合同未登记 | gap-cap |
| m5e_combo_params | 跨页参数组合 | pair_*（已 7/7 回放）+ cfg_value_* | replay-ok（pairwise 11-19） |
| m5f_negative_params | Quality 负参数路径 | 负参数拒绝读回未登记 | gap-neg |
| m5g_preset_manage | 预设保存/管理 | 预设名保存已被 oracle 拒（v3-project 第三批） | blocked（保存配置预设名判据待修） |
| m5h_ironing_combos | 熨烫+Advanced 组合 | uia_quality_enums | native-SHADOW(hist)（a4f5926d 11-19）+replay-ok |
| m7t72 | 模型导入（模板） | bound_model_move | adapted |
| m7t74 | 单模型切片调整（模板） | uia_replay_layer 链 | replay-ok |
| m8x_137_flow_param_tabs | 流量喷嘴参数页签 | uia_process_combo（工艺页签组合） | adapted |

## F3 保存重开和导出（4）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m3g_export_3mf | 导出 3mf 可重载 | v3_project 批（4 批中 3 槽 NON_GREEN） | blocked（第四批待验，预设名判据） |
| m3d_param_reslice | 参数变更→重切 gcode 不同 | 每个原生 run 的 A/B 重切 | native-SHADOW(hist)·隐含 |
| uia_save_as（门禁） | 原生另存为 | uia_save_as | native-SHADOW(hist)（d7299035） |
| overwrite（负例） | 同路径冲突确认 | overwrite 场景 | adapted（历史正反例见 zcode-matrix-2026-11-17） |

## F4 多盘、对象、变换与撤销（20）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m6a_transform_verify | 变换工件验证 | uia_hybrid_canvas（X+10）/ uia_replay_canvas | native-SHADOW(hist)（52a21e14/8c8b135f） |
| m7f_scale120 | 缩放 120% | general_scale_quality/others | adapted（11-18 两槽 NON_GREEN，裁图/检查器误拒，修订待复验） |
| m7e_rotate45 | 旋转 45° | canvas 数值编辑 rotate 字段未登记 | gap-cap |
| m3h_undo_redo | 撤销/重做恢复场景 | Ctrl+Z 快捷键未开放、撤销语义判据未定义 | blocked（撤销合同） |
| m3f_multi_plate | 多盘每盘切片 | 多盘选择/盘切片 UIA 未登记 | gap-cap |
| m3b_delete_scene | 清空场景 | 右键菜单/删除未登记 | gap-cap |
| m7h_context_delete | 右键删除（#18） | 右键菜单合同未登记 | gap-cap |
| m7g_arrange | 自动排列（#17） | 工具栏按钮 Invoke 未登记 | gap-cap |
| m7j_change_filament | 换耗材（#21） | pilot_material（逻辑材料槽 2） | native-SHADOW(hist) |
| m7i_add_primitive | 添加原始体（#19） | 原始体对话框未登记 | gap-cap |
| m7t77 | 模型分割 | 分割工具未登记 | gap-cap |
| m7t78 | 自动朝向选底面 | 朝向工具未登记 | gap-cap |
| m7t79 | 拆分为对象/零件 | 同分割族 | gap-cap |
| m7t80 | 可变层高绘制支撑 | 画布绘制+可变层高未登记 | gap-cap |
| m7t81 | 布尔剪贴整理 | 布尔工具未登记 | gap-cap |
| m7t82 | 剪贴耗材切换 | 材料槽+剪贴组合 | gap-cap |
| m7t84 | 预设更改耗材合并 | 材料槽族扩展 | gap-cap（依赖预设切换） |
| m7t86/87/88 | 朝向/支撑/拆分/缩放/耗材组合主流程 | 多原子组合 | gap-cap（依赖单项） |
| m7t109 | 打印机预设全局耗材 | 同上 | gap-cap |
| uia_move_layer（组合） | 平移+层高组合 | uia_move_layer + uia_replay_move_layer | native-SHADOW(hist)（e251f0f2）+replay-ok（b1d0ecff） |

## F5 混色、渐变、多材料与高流量（31）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m3t-m3w（4） | Add Mix 比例/循环输入往返 | uia_mix_recipes / uia_replay_mix | scripted-probe（11-18 回放探针通过；AI 侧目标式未跑） |
| m3j/m3k/m3l/m3r | 混色匹配入口/模式/进度 | mix recipes 含 match 段 | scripted-probe（部分） |
| m3m/m4d | 耗材卡/物理耗材操作 | 材料槽合同（slot2 已过）部分复用 | adapted（部分） |
| m3n | 取消确认（#25） | 业务取消弹窗读回未登记 | gap-neg |
| m3o | 无多色模型门禁（#28） | 入口门禁负例未登记 | gap-neg |
| m3p | 匹配方案持久化 | 混色保存重开（V3_PLAN §8 已设计，组共享 fixture） | adapted（未跑） |
| m3q | 原模型视图/切换 | 视图族 | gap-cap |
| m3s | hover tooltip（降级） | — | n/a（降级保留） |
| m3x | Match 模式卡片 | mix recipes | scripted-probe（部分） |
| m3y | 渐变模式 2 行+效果 | mix recipes 渐变段 | scripted-probe（部分） |
| m3z/m4a/m4f/m4j | 兼容矩阵/批量门/64 上限/同色 | 门禁与上限负例 | gap-neg |
| m4b/m4c | 批量对话框/侧栏面板 | 面板 UIA 未登记 | gap-cap |
| m4e | 涂色 gizmo（PARTIAL） | 画布绘制未登记 | n/a→gap-cap（保留降级） |
| m4g | 细分混色层 dithering | cfg_value 族可扩 | adapted（候选） |
| m4h | 0.1mm 混色模板 | 预设族 | gap-cap（依赖预设） |
| m4i | 混切+导出链 | mix+slice 组合 | adapted（候选） |
| m8b_official_color | 官方颜色 | 耗材颜色 UIA 未登记 | gap-cap |
| m8c_temp_mix_gate | 高低温混用门（#111/112） | 偏好开关+切片门禁（类 m8x_125） | gap-cap |
| m8f_nozzle_flow | 高流量喷嘴（#133/135/136） | 喷嘴/流量组合框未登记 | gap-cap |
| m8g_flow_single | 单一变量流量对比 | 同上 | gap-cap |

## F6 性能及其他专项（9）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m2_perf_showcase | 大工程切片+录像演示 | 独立 perf 轨道 | off（禁用，perf 批次另计） |
| m8a_fit_view | 一键还原视图（#16-19） | 视图合同未登记 | gap-cap |
| m8d/m8e | 净化器 gcode/弱冷 | cfg_value 参数编辑族（顶盖 SET_PURIFIER_MODE 分支翻转） | adapted（候选：cfg_value 扩展） |
| m8x_123 | 软化温度→温类→gcode | cfg_value（参数→G-code 分支） | adapted（候选） |
| m7k_flush_options | 冲洗选项（PARTIAL） | 冲洗面板读回未登记 | gap-cap（PARTIAL 保留） |
| m3a_empty_slice | 空场景拒绝切片 | 负例门禁 | gap-neg |
| uia_process_combo | 工艺页签组合（cfg/dep 族） | uia_process_combo + dep_ironing_* | adapted（dep 族已有正反例设计） |
| safety 三件 | 停输/超时/守卫断开 | safety_cancel/timeout/guard_disconnect | native-SHADOW(hist)（3/3，caff0452 批） |
| fixture_cold/shared | 冷启/共享 fixture | FIXTURE_SCENARIOS | adapted |

## 本批运行记录（逐批追加）

| # | 时间 | 场景 | Run ID | 结果 | 备注 |
|---|---|---|---|---|---|
| — | — | — | — | — | （启动后追加） |

## 候选/缺口登记（探索轮输入）

（首轮探索后追加：候选 ID、去重依据、最短复现、独立判据、清理方式。）

## Checkpoint（恢复用）

- 恢复命令（宿主 Git Bash，本仓根）：
  `git fetch origin codex/glm-flash-expansion-20261121-0217 && git switch codex/glm-flash-expansion-20261121-0217 && git log -1`
  然后读本文件「本批运行记录」最后一条 + `docs/runs/glm-flash-expansion-2026-11-21.md`。
- 源提交：本文件最后一次 commit（见 git log -- docs/V3_MIGRATION_LEDGER.md）。
- 客机恢复：`runner/hv_go.ps1` 自动校验客机 HEAD=宿主 HEAD；v3 检出 `C:\coil\orca-blackbox-v3-r1` 需 bundle 快进（模式见 runner/v3_project_batch_phase.ps1 setup_bundle）。
- 恢复后先做：①`git log -1` 核对源；②读最后 run 记录决定回收或续跑；③`tools/check_registry.py` 核对分母仍 89。
