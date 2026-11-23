# V3 原生 AI 迁移台账（GLM 总控 · 2026-11-21 批次）

可续跑的唯一权威台账。分母以 `cases.py` + `tools/check_registry.py` 冻结；旧业务判据以 `BLACKBOX_CASES.md` 与各用例脚本头为准（本表不复述全文，只存一行业务目标与判据指针）；原生场景以 `harness/native_matrix.py` SCENARIOS 为准。恢复流程见文末 checkpoint。

见[后续任务表](#后续任务表)和[独立复核记录](runs/glm-flash-expansion-2026-11-21.md#独立复核2026-11-21)。

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

## 旧判据摘要（逐族，出处 BLACKBOX_CASES.md 对应表行；迁入原生时判据等价或更强）

- **F1**：主窗出现/可见/尺寸>0（m0）；tab 选中色 teal(0,150,136) 翻转（m1）；启动→关闭往返 + fresh profile 干净（m7a/m7t73）。原生等价：ready 收据含 hwnd/pid/窗口矩形 + teardown 清理确认。
- **F2**：done 绿勾模板 + 色度占比≥2×基线（m2）；`; layer_height` gcode 头跟随（m3e）；WM_SETTEXT+KILLFOCUS 提交链→重切 gcode 字节 diff（m3d）；损坏文件错误弹窗+app 存活（m3c/m7d）。原生等价：独立重开切片 oracle（层数/参数/G-code 分支），已强于模板断言。
- **F3**：zip 有效+3D/3dmodel.model 存在+`printer_settings_id` 保留+二次加载模型到达（m3g）；Save As 对话框往返+同路径冲突确认（overwrite）。原生等价：project_3mf 解析+冻结 SHA+新 profile 重开。
- **F4**：`<build><item transform>` 平移 X 精确=60.0、Y/Z 不变（m6a，导出 3mf 明文矩阵）；Undo/Redo 后色度 ≥1%/<0.4%（m3h）；视角切换 viewport diff>10（m3i）。
- **F5**：混色表 48 条——比例/循环/匹配/渐变的 UI 状态机断言（红幅/OK 禁用/徽章/预览重绘/持久化 5.9% 色度 + 面板保留）；混切 gcode 1.36MB 含 5 种换刀标记（m4i）；64 上限增禁恢复（m4f）；同色可登记+5 色橙幅（m4j）。
- **F6**：顶盖 SET_PURIFIER_MODE 分支翻转（vitr≤50→MODE=1，>50→MODE=3，m8x_123）；高流量三配置对比（m8f/m8g）；Fit 视图色度恢复（m8a）；性能=进程指标采样（perf 轨道，非 GUI 断言）。

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
| m5e_combo_params | 跨页参数组合 | pair_*（已 7/7 回放）+ cfg_value_01..12（layer/seam/ironing 值组合域，01/04/06/07 已过） | replay-ok（pairwise 11-19）+ cfg 4 例 SHADOW |
| m5f_negative_params | Quality 负参数路径 | 负参数拒绝读回未登记 | gap-neg |
| m5g_preset_manage | 预设保存/管理 | 预设名保存已被 oracle 拒（v3-project 第三批） | blocked（保存配置预设名判据待修） |
| m5h_ironing_combos | 熨烫+Advanced 组合 | uia_quality_enums | native-SHADOW(hist)（a4f5926d 11-19）+replay-ok |
| m7t72 | 模型导入（模板） | bound_model_move | adapted |
| m7t74 | 单模型切片调整（模板） | uia_replay_layer 链 | replay-ok |
| m8x_137_flow_param_tabs | 流量喷嘴参数页签 | uia_process_combo（工艺页签组合） | 部分覆盖候选，旧判据待签核 |

## F3 保存重开和导出（登记册 2：m3d/m3g；另含 uia_save_as/overwrite 两个场景行）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m3g_export_3mf | 导出 3mf 可重载 | v3_project 批（4 批中 3 槽 NON_GREEN） | blocked（第四批待验，预设名判据） |
| m3d_param_reslice | 参数变更→重切 gcode 不同 | 每个原生 run 的 A/B 重切 | native-SHADOW(hist)·隐含 |
| uia_save_as（门禁） | 原生另存为 | uia_save_as | native-SHADOW(hist)（d7299035） |
| overwrite（负例） | 同路径冲突确认 | overwrite 场景 | adapted（历史正反例见 zcode-matrix-2026-11-17） |

## F4 多盘、对象、变换与撤销（23；另含 uia_move_layer 组合场景行）

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
| m7t75 | 多模型布局切片（模板） | 多实例布局未登记 | gap-cap（依赖多实例选择合同） |
| m7t77 | 模型分割 | 分割工具未登记 | gap-cap |
| m7t89 | 模型创建旋转涂色切片 | 旋转+涂色组合 | gap-cap（依赖 rotate 与涂色画布） |
| m7t78 | 自动朝向选底面 | 朝向工具未登记 | gap-cap |
| m7t79 | 拆分为对象/零件 | 同分割族 | gap-cap |
| m7t80 | 可变层高绘制支撑 | 画布绘制+可变层高未登记 | gap-cap |
| m7t81 | 布尔剪贴整理 | 布尔工具未登记 | gap-cap |
| m7t82 | 剪贴耗材切换 | 材料槽+剪贴组合 | gap-cap |
| m7t84 | 预设更改耗材合并 | 材料槽族扩展 | gap-cap（依赖预设切换） |
| m7t86/87/88 | 朝向/支撑/拆分/缩放/耗材组合主流程 | 多原子组合 | gap-cap（依赖单项） |
| m7t109 | 打印机预设全局耗材 | 同上 | gap-cap |
| uia_move_layer（组合） | 平移+层高组合 | uia_move_layer + uia_replay_move_layer | native-SHADOW(hist)（e251f0f2）+replay-ok（b1d0ecff） |

## F5 混色、渐变、多材料与高流量（32）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m3t-m3w（4） | Add Mix 比例/循环输入往返 | uia_mix_recipes / uia_replay_mix | scripted-probe（11-18 回放探针通过；AI 侧目标式未跑） |
| m3j/m3k/m3l/m3r | 混色匹配入口/模式/进度 | mix recipes 含 match 段 | scripted-probe（部分） |
| m3m/m4d | 耗材卡/物理耗材操作 | 材料槽合同可部分复用，slot2 端到端尚未通过 | adapted（部分） |
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
| m8x_125_aux_mix_pref | 涂色辅材与主材温类冲突，偏好关闭时拒绝切片，打开后经风险确认完成切片，最后还原偏好（#125） | 旧判据见 [`m8x_125_aux_mix_pref.py`](../tests/topcap/m8x_125_aux_mix_pref.py) 头部；V3 待补涂色、偏好、警告与风险确认合同 | gap-cap |
| m8f_nozzle_flow | 高流量喷嘴（#133/135/136） | 喷嘴/流量组合框未登记 | gap-cap |
| m8g_flow_single | 单一变量流量对比 | 同上 | gap-cap |

## F6 性能及其他专项（登记册 7；另含 safety/cfg/fixture 场景行）

| ID | 业务目标 | 原生映射 | 状态 |
|---|---|---|---|
| m2_perf_showcase | 大工程切片+录像演示 | 独立 perf 轨道 | off（禁用，perf 批次另计） |
| m8a_fit_view | 一键还原视图（#16-19） | 视图合同未登记 | gap-cap |
| m8d/m8e | 净化器 gcode/弱冷 | cfg_value 域=layer/seam/ironing，**不含温度/净化器参数**——需扩 cfg 规则域（温度→SET_PURIFIER_MODE 分支翻转判据已有旧脚本实现） | gap-cap（cfg 域扩展，正例判据可从 m8x_123 旧脚本移植） |
| m8x_123 | 软化温度→温类→gcode | 同上 | gap-cap（同上） |
| m7k_flush_options | 冲洗选项（PARTIAL） | 冲洗面板读回未登记 | gap-cap（PARTIAL 保留） |
| m3a_empty_slice | 空场景拒绝切片 | 负例门禁 | gap-neg |
| uia_process_combo | 工艺页签组合（cfg/dep 族） | uia_process_combo + dep_ironing_* | adapted（dep 族已有正反例设计） |
| safety 三件 | 停输/超时/守卫断开 | safety_cancel/timeout/guard_disconnect | native-SHADOW(hist)（3/3，caff0452 批） |
| fixture_cold/shared | 冷启/共享 fixture | FIXTURE_SCENARIOS | adapted |

## 本批运行记录（逐批追加）

| # | 时间 | 场景 | Run ID | 结果 | 备注 |
|---|---|---|---|---|---|
| 1 | 02:26 | uia_general_wall (zcode goal-only) | `3140ae8257294e36a5f2dd25c25f8163` | 基础设施失败 | ZCode app-server 已升级（zcode.cjs d9afd58d→6b84e928），新增 `session/readReplyLanguage` 请求，驱动判 unexpected_host_request，0 工具调用，清理确认 |
| 2 | 02:29 | 同上 | `6165a41c440543e9893dc55e8a1d0dd7` | 基础设施失败（假通过被拦截） | readReplyLanguage 已答 en；新版在 turn 开始即取工具快照，windows_mcp ferry（stdio→relay→客机HTTP）未完成握手 → 模型请求 toolNames=[]，glm-5.3-flash 单轮**虚构完成**（声称改壁环数+已保存），0 工具调用；驱动 `native_calls_incomplete` 正确拦截，客机 ready/setup 全好，清理确认 |
| 3 | 02:46 | 同上 | `38535cc0a2de450ebd5748ebd945888d` | blocked（基础设施） | 修复已提交（bf108f7）但 clash-guard 02:37:45 起 OFF_SAFE（代理被关，非本会话操作）→ ip_guard 纪律性拒绝；未进入客机 |

**zcode 轨道本批终态（guard 恢复后续跑完成）**：
- 锚点 `d74f73f4`（uia_general_wall goal-only）**SHADOW 独立通过**——两项 app-server 适配修复（0b81f5d readReplyLanguage、bf108f7 MCP 等待）端到端验证；壁环数 3+独立重开 68 层挤出。
- 泛化八槽复验批 `66f6963e`（源 `33869a6`）：**2/8**（bottom_quality、y_others，均 pass_tool_recovery；Y 平移历史首次通过）。wall 槽引导式提示死于对话框路由违规而 goal-only 通过（提示模式敏感性）；bottom_strength 回落；开发锚点 0/2 → 探索阈值未达，探索轮未开。八槽清理确认。
- 脚本轨道 31/31 SHADOW 不变。总累计本批独立通过：**34 个真实客机 run**（31 script + 1 zcode 锚点 + 2 泛化槽）。

## 历史证据指针（native-SHADOW(hist) 的 run 出处）

| 能力/场景 | 历史 Run | 记录 |
|---|---|---|
| Save As 门禁 | `d7299035e33b80969e0064a8d9b3e4fc` | runs/zcode-uia-first-2026-11-18.md |
| wx 层高门禁 | `bfd5c93af9571ba3ddc53f7099d7e407` | 同上 |
| ImGui 画布门禁 | `52a21e14b5e0456bf5e965cb98970cf4` | 同上 |
| 壁环数 goal-only | `f65ba49e6330436fa6a41d98758831f0` | V3_PLAN §7 |
| 画布 X+10 goal-only | `8c8b135fa05c437eaf6deef108dffc53` | 同上 |
| 底层数/Strength | `4aab27286416496a86916d5378ff3356` | 八槽 1/8 |
| 双下拉 enums | `a4f5926dcc5243838d2baf7297227a6d` | runs/zcode-compound-expansion-2026-11-19.md |
| 平移+层高组合+回放 | `e251f0f23b0338083fdb5919edde5f74` / `b1d0ecff0f77bdaedd26dc847dcddfab` | 同上 |
| pairwise 7/7 | 批 `c32661e9c8e14b3f9304ababd88e4033` | runs/pairwise-replay-2026-11-19.md |
| pilot 材料/壁环 | `d301c03a` / `af89824f` | runs/zcode-business-pilots-2026-11-17.md |
| cfg_value 01/04/06/07 | `2a6b9643`/`c96a3498`/`d13fa858`/`a38b163f` | artifacts/native_save_demo |
| dep_ironing 三件 | `f43a0013`/`aff32323`/`98890a09` | 同上 |
| 安全 3/3 | 批 `caff045271da4ec4a6ef62c516b643a1` | runs/zcode-matrix-2026-11-17.md |
| 泛化八槽 1/8 | 批 `05793ef532d7468374fc9a6332de264a` | runs/zcode-uia-first-2026-11-18.md |

## 候选/缺口登记（探索轮输入）

按用户影响×可复现性×验证成本排序的缺口（本轮如开不了探索轮，供下批直接取用）：

1. **预设切换读回**（m3e/m5a/m5g 族）：预设 combo 自绘+预设名读回无合同 → 需预设下拉 UIA/裁图混合合同 + gcode 头跟随判据（旧判据在 BLACKBOX_CASES.md m3e）。解锁 6+ 条。
2. **撤销/重做**（m3h）：Ctrl+Z 未开放、撤销语义判据未定义 → 需快照 diff 判据（保存前后 3MF config 对比）。解锁 1 条+组合场景。
3. **右键菜单**（m7h/m3b）：上下文菜单合同未登记 → 菜单弹出+菜单项 UIA Invoke + 场景状态读回。
4. **多盘**（m3f）：盘选择/每盘切片判据（旧判据=每盘 gcode 存在）。
5. **导入损坏负例**（m7d/m3c）：错误弹窗读回+无副作用（无新对象、进程活着）。
6. **高流量/官方颜色**（m8f/m8g/m8b）：喷嘴/流量组合框与耗材颜色——cfg_value 族扩展的好候选（该族合同已验证）。
7. **空场景切片拒绝**（m3a）：按钮门禁状态读回负例。
8. **rotate45**（m7e）：画布数值编辑 rotate 字段——CANVAS_REPLACE_SCENARIOS 合同扩展。

## 本批基础设施发现（给团队）

- **ZCode app-server 已升级**（zcode.cjs d9afd58d→6b84e928，11-19 后）：①新增 `session/readReplyLanguage` 宿主请求（已在驱动白名单应答 en，0b81f5d）；②turn 开始即取工具快照、不再等 MCP 就绪——windows_mcp 走 stdio→relay→客机 HTTP，握手未完成时模型请求 toolNames=[]，**glm-5.3-flash 会单轮虚构完整业务成功**（运行 6165a41c 实证，驱动 `native_calls_incomplete` 拦截）；已在 create/send 之间加 25s 有界等待（bf108f7）。建议后续把 ferry 握手改为无 relay 的直连或预热。
- **clash-guard OFF_SAFE**（02:37:45 起，代理被关，非本会话操作）：ip_guard 纪律性阻断全部 zcode 模型跑批；`~/.clash-guard/status-token` 集成文件丢失已按 status-api.md 恢复。guard 恢复 ready 前只跑 script 轨道。
- 11-20 客机识别故障（KVP 关）已被 06d2257 BIOS 兜底修复，本轮实测通过。

## 本批分族迁移汇总（初算，判据待签核）

分母为 89 个 ID，含 2 个禁用项。展开合并行与简称、补齐 `m8x_125_aux_mix_pref` 后，六族明细为 9/16/2/23/32/7。下表保留原批分类；**本批证据候选**指有 SHADOW 证据可以用于逐案签核的映射。21 个候选中已标明部分映射 9 个（F2 1 个、F5 8 个），其余 12 个仍须核对旧必验断言。**历史**为旧源通过待复验，**blocked** 为有具体阻塞，**gap** 为缺 UI 能力或拒绝合同，**未跑**为已登记适配但本批未执行。

| 族 | 条数 | 本批证据候选 | 历史 | blocked | gap | 未跑 | n/a | off |
|---|---:|---|---|---|---|---|---|---|
| F1 启动/页签/工程 | 9 | 3（m0/m7a 链隐含于每 run 收据；m7t83=bound_model_move） | 0 | 0 | 2（m1 tab、m3i 视图） | 2（m7b/m7t73） | 1（m0_anchor） | 1（m1b） |
| F2 导入/预设/工艺/切片 | 16 | 8（m5b/m7t74/m5h/m5e/m7c/m7t72/m2/m8x_137部分） | 1（m5c） | 1（m5g 预设名） | 6（损坏2、预设2、Support、负参数） | 0 | 0 | 0 |
| F3 保存重开导出 | 2 | 1（m3d） | 0 | 1（m3g） | 0 | 0 | 0 | 0 |
| F4 多盘/对象/变换/撤销 | 23 | 1（m6a） | 1（m7j） | 1（m3h 撤销） | 19（rotate/多盘/删除/排列/原始体/分割/朝向/支撑绘制/布尔/剪贴/耗材组合等） | 1（m7f 复验候选） | 0 | 0 |
| F5 混色/渐变/多材料/高流量 | 32 | 8（Add Mix 回放链 m3j/k/t/u/v/w/x/y 部分） | 0 | 0 | 17（neg6+cap11，含高流量/颜色/温混/面板/模板/m8x_125） | 5（m3p/m3m/m4d/m4g/m4i） | 2（m3s/m4e 降级） | 0 |
| F6 性能与专项 | 7 | 0 | 0 | 0 | 6（m8a/m8d/m8e/m8x_123/m7k/m3a） | 0 | 0 | 1（m2_perf） |
| **合计** | **89** | **21** | **2** | **3** | **50** | **8** | **3** | **2** |

原分类合计为 89。31 个 Script 场景使用独立的场景分母，其中含登记册外场景。ZCode 在 guard 恢复后完成开发集八槽，结果为 2/8，历史冻结结果保留 1/8。探索投入闸未达，探索轮未启动。

## 后续任务表

按优先级推进。用例和探针在 Hyper-V `win11-test` 执行，沿用仓库登记入口和验收链。每个 run 绑定宿主与客机源 SHA、SUT、合同、fixture 和验收收据。模型运行先验证所选供应商路由与预期工具集。当前 ZCode 启动器还会强制检查 Clash guard，路由核验与门禁调整按下表执行。预检拦截与同步故障留在计划分母，单列基础设施结果。

| 优先级 | 任务 | 当前状态 | 验收条件 |
|---|---|---|---|
| P0 | slot2 先跑 Script 正对照，再验 ZCode | 弹窗合同已扩展，最终合同业务 0/2，`NON_GREEN` | 在同一 SUT、初态和合同下，Script 打开弹窗、刷新观察、选择槽 2 并保存。独立新进程重开验证目标对象绑定槽 2，其他对象和槽位保持，清理确认。再按同一判据验收模型，保留首轮与复跑。 |
| P0 | 固定单一源提交复跑 31 个 Script 场景 | 已有跨六个源提交的 31/31 SHADOW，目标提交整套待跑 | 冻结拟纳入日常回归的源 SHA、SUT 和场景清单。逐场景确认业务、路径、清理收据。含 fixture 组的共享与冷启判据，以及涉及保存的冻结产物和独立重开。 |
| P0 | 独立重算 89 条迁移覆盖 | 89 个 ID 均已入表，旧判据未逐案签核 | 逐条登记旧必验断言、V3 判据、执行模式、run ID、源 SHA 和证据位置。分别汇总完整、部分、历史通过和未验证。优先审 F5 的 8 条和 F2 的 `m8x_137_flow_param_tabs`。 |
| P0 | 核验 Snapmaker GLM 网关与 Clash guard 的依赖 | GLM 使用公司网关，现启动器仍强制检查面向 OpenAI 出口的 Clash guard | 核实 ZCode 实际使用的代理与公司批准的网关路由。若该路由独立于 Clash guard，按供应商配置门禁，并以公司网关身份、可用性及工具就绪作为 GLM 的准入条件。适用 Clash guard 的路由保留原有检查；相关断连用例按对应路由单列。调整实现前按当前门禁运行。 |
| P0 | 核实源同步与工具就绪门禁 | 已见同步失误及零工具假通过被拒 | 给预检、模型实际启动和业务验收分别留收据。确认源不一致或工具未注册时停止推进。报告计划槽位、实际开跑、基础设施受阻和有效业务验收数。 |
| P1 | 回补历史业务矩阵证据 | 本批六项有收据，`quality_a` / `strength_b` 待补 | 定位同批有效收据或在目标提交独立复跑，按八项冻结矩阵汇总。 |
| P1 | 对照标签辅助和提示模式 | bottom_strength 开发复跑一次通过，wall 有单场景模式差异 | 固定源、SUT、fixture、模型、初态和判据。每组只切换标签辅助或提示模式中的一项，保留各次原始结果，并覆盖未经调试的相邻易混字段。此表的开发场景留在开发回归。 |
| P1 | 推进已登记的确定性缺口 | 预设、撤销和菜单等仍缺合同或判据 | 按上方候选清单逐项落实旧必验断言，先做可独立验收的 Script 正反例，再评估 AI 路径。 |
| P2 | 冻结新保留集并重评探索投入闸 | 开发集 2/8，探索轮未开启 | 由评估方冻结未参与调试的目标与初态，依据 [V3_PLAN §4](V3_PLAN.md#4-最小有决策价值的评估) 单次执行各槽。锚点 2/2、新目标至少 3/4 且两目标均有成功、组合与干扰 2/2，并满足安全与清理条件，才考虑受控探索。 |

## Checkpoint（恢复用）

- 恢复命令（宿主 Git Bash，本仓根）：
  `git fetch origin codex/glm-flash-expansion-20261121-0217 && git switch codex/glm-flash-expansion-20261121-0217 && git log -1`
  然后读本文件「本批运行记录」最后一条 + `docs/runs/glm-flash-expansion-2026-11-21.md`。
- 源提交：本文件最后一次 commit（见 git log -- docs/V3_MIGRATION_LEDGER.md）。
- 客机恢复：`runner/hv_go.ps1` 自动校验客机 HEAD=宿主 HEAD；v3 检出 `C:\coil\orca-blackbox-v3-r1` 用 `runner/guest_v3_bundle_sync.ps1 -Head <sha>`（本批固化，36b9463）快进——**每次宿主提交后、下次 native run 前都要同步**（本批曾因漏同步浪费 4 个 run 槽，见 a66a86ac）。
- 恢复时核对源提交、读取最后一次运行和上方任务表，再用 `tools/check_registry.py` 校验登记册分母。按任务验收条件决定续跑。


## 飞书新表补充路线图（base JB5jbAczEa7vZUsWFencTmNnnob / tblKjIVV8KA53kUQ，2026-11-22 拉取 216 条）

| 桶 | 条数 | 处置 |
|---|---:|---|
| 已自动化 | 92 | 与登记册 89 基本重合，走既有 P0-3 签核 |
| **待实现·常用工艺参数** | **44**（P0 33/P1 11，#254-297） | **本轮主攻**：全部为参数组合用例，映射到已验证 cfg_value/pairwise 域；按组扩展 config_dependencies + process_panel 基线（uia_process_combo 模式）+ 标准 oracle |
| 状态空缺 | 26 | 分诊：打印板右键菜单 14（菜单合同缺口族）、文件导入导出 12（F3 扩展）、主流程 4 |
| 不适用→**更正两次** | 49→约 20 | **联机域按 Orca 软件口径=已通**（2026-11-22 定稿）：11-19 实测登录→设备页→新建工程→切片→提交→Upload completed→设备收到同名任务→执行升温 140/140°C，软件环节零失败（runs/orca-cn-{login,device-upload,print}-2026-11-19；探针链固化于 hv_go -Cloud* 系列，限 win11-test/test 独立探针槽）。记录保留 NON_GREEN 仅因验收点含设备侧进度，卡点为打印机物理状态（热床异物检测/首层实物），非 Orca 缺陷。联机 16+AI 监控 14 中走探针链可测的转"可测待排"；真不适用=仅需特定硬件状态或人工介入的约 20 条。同步耗材 4、延时摄影导出 4 待单查 |

实现顺序（按 P0×组共享度）：层高组合(#254) → 熨烫(#259) → 墙圈数(#266) → 外壳(#267) → 填充(#268) → 速度链(#270/271) → 支撑(#277) → 其余按表。每条=确定性 script 基线+保存重开+3MF 设置/G-code 双判据（V3 标准），fixture 用现行立方体（与表内"球"差异记录在案）。判据等价性：表内判据（参数写入+首层 Z/步进语义）⊆ V3 oracle 检查面。

### 2026-11-22 下午进度（四面前置会话）

- **已闭环 SHADOW：#254/#257/#259/#266/#267/#268/#273/#277/#297 共 9 条**（#268 Gyroid 弹窗配方；#259 六轮收敛链；fa 作者链 4 条：#277/#257/#273/#297）。引擎三连修：双向滚动（编辑后滚动落点随机）/租约陈旧接管/combo 元组解包。fa B1-B4 累计 authored 29+#288/#289 混色族归因——44 条参数族全部入库或归因。
- **已登记待跑（fa706g3 authored，已并入主线）**：#276/277/278/279/292/293/294 七条（夹具实测 VALUES+三方注册+check_registry PASS）。
- **在攻留证**：#259（combo 提交步 text=None）、#263（Bridge flow 行在 OCR 带上方）、#264/#270/#271（Speed 页标签/滚深）、#290/#291（两枚举 combo/auto_brim 字段禁用）——全部失败 run 留 band 证据。
- 基建修复入主线：ps_direct 轮询 45s、bundle_sync EAP、param 族免预点击、弹窗真滚轮引擎、租约锁自愈（批前清锁+900s 看门狗）。
- 独立证据：物理 Win10 fa706g3 m0-m2 GREEN（环境口径）；Mac 层高 SHADOW 0a24557a+负对照拒绝；P0-3 签核表 89/89 初稿（DRAFT 待宿主逐行复核）。

### 2026-11-23 进度（模型切换 + 引擎根因批 + Mac 壁环数）

- **参数族闭环仍是 9 条 SHADOW**（#254/#257/#259/#266/#267/#268/#273/#277/#297），本节无新增 Windows SHADOW；下列引擎修复的效果待重跑验证。
- **引擎根因批入主线**（详见运行记录「续二」）：扫描循环的滚轮焦点死锁自愈、`^` 行首锚定、组内限定、两行式行、页首组标题定位（#270「卡死」真因，2×420 秒）、组名不存在的快速失败、弹窗多词目标、失败点截图入收割。离线模拟测试 15/15，原版 8 项变红。
- **用例范围结论**（源码图谱 + 2.3.5 普查 + 2.4.0 扫描三方一致）：#296 的 `Add line number` 行与 #294 的 `Timelapse` 行不在工艺参数页；#263 的 `Max bridge length`、#278 的 `Raft expansion` 同样无此行（已从 ops 与 VALUES 移除并记录）。这几条需改判据或归入其他页/设备侧，不能靠引擎修复闭环。
- **ops 校准**：#256/#263/#270/#271/#274/#276/#284/#291/#292 九条的组名或标签已按实证改正（含一处我自己的误改：#292 锚点）。
- **Mac 轨道壁环数 2→3**（run 306d3efe）：记为 Mac 口径 SHADOW，带保留项（判据为差分判据，52 项负对照经宿主独立重跑复现；GUI 导出未测；SUT 2.4.1/macOS），不计入 44 条。
- **标签普查**：fa706g3 上 2.3.5 的五页完整 + Others 部分，证据 `docs/runs/evidence/fa706g3-label-census-2026-11-23/`，校准口径。
