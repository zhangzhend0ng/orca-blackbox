# Mac 壁环数判据负对照（任务 A6）：证据包

标签 `mac-author-20261123-01`（续 `codex/mac-author`），2026-11-23。宿主 GLM 总控派任务 A6：
给 A5 的壁环数结论（run `306d3efe`，SHADOW）补负对照，证明 `verify_walls_differential()`
不是假通过。纯离线：不跑 GUI、不启动 Orca，判据函数与入库基线未改动。

**结论：判据在 B/D/E/F 全部正确拒绝。** A（run `306d3efe` 的保存工程）通过；C（首跑
`ffe0c6e4` 的保存工程）在新判据下**同样通过**（与 A 的差别见「C 的情况」）。52 项对照的
判定与错误码全部与预测逐项一致：45 项必须项（任务书 A–G 及其加固变体）、7 项说明/边界探针。
全部数字出自 [results.json](results.json)，生成工具 `tools/mac_walls_negative_controls.py`。

## A–G 结果

| 项 | 被判工程 | sha256（前 12 位） | 判定 | 错误码 |
| --- | --- | --- | --- | --- |
| A | 真实：run 306d3efe 的保存工程 | `436d6baf701f` | 通过 | — |
| B | 真实：入库基线 walls_control.3mf | `2e8a5caf0a9b` | 拒绝 | `pilot_wall_loops_target` |
| C | 真实：首跑 ffe0c6e4 的保存工程 | `8d6ca231589a` | 通过 | — |
| D | 构造：拷贝基线，initial_layer_print_height 0.44→0.5，wall_loops 仍为 2 | `7c107fb7e675` | 拒绝 | `pilot_wall_loops_target` |
| E | 构造：拷贝基线 + wall_loops=3 + 另外 5 个参数（manifest 未动） | `2331e2dfcf49` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| F | 构造：拷贝基线 + wall_loops=4 | `c02ad17ce378` | 拒绝 | `pilot_wall_loops_target` |
| G | 无真实异地构建保存件，按任务书跳过；改为身份模拟与基线文件替换（G1–G14） | 见下表 | 拒绝 11 / 通过 3（G5、G12、G13，均为边界探针） | 见下表 |

- 判据在第一个违规处就抛出，所以每项只报一个键；要多报就多构造（见 D/E 的加固变体）。
- D 的字面项（拷贝基线、只改 `initial_layer_print_height`）是被 wall_loops 闸门拒的，理由较浅。
  无关改动**搭载 wall_loops=3** 时是否仍被拒，由 D2–D4 回答（差分条款拒绝）。
- E 只报出字母序第一个违规键；E4–E8（逐个单独加）与 E9–E12（逐个摘除）证明 5 个参数各自
  都能被发现。
- G：真实的「另一台机器/另一次构建保存的 3mf」本机没有（Windows 客机 2.4.0 的保存件不在这台
  Mac 上），按任务书跳过；改用身份模拟 + 基线文件替换覆盖判据的两道锁，见「G 的展开」。

### 全部 52 项对照

| 项 | 性质 | 被判工程 | 基线 | sha256（前 12 位） | 判定 | 错误码 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 必须 | 真实：run 306d3efe 的保存工程 | 入库 | `436d6baf701f` | 通过 | — |
| B | 必须 | 真实：入库基线 walls_control.3mf | 入库 | `2e8a5caf0a9b` | 拒绝 | `pilot_wall_loops_target` |
| B2 | 必须 | 构造：基线 + wall_loops=3（manifest 未动） | 入库 | `b293f9bf7cf2` | 拒绝 | `pilot_dirty_manifest_out_of_scope` |
| B3 | 必须 | 构造：基线 + wall_loops=3 + manifest 只记 wall_loops | 入库 | `99cff2203eef` | 拒绝 | `mac_walls_unrelated_setting_changed:initial_layer_print_height` |
| C | 说明 | 真实：首跑 ffe0c6e4 的保存工程 | 入库 | `8d6ca231589a` | 通过 | — |
| D | 必须 | 构造：拷贝基线，initial_layer_print_height 0.44→0.5，wall_loops 仍为 2 | 入库 | `7c107fb7e675` | 拒绝 | `pilot_wall_loops_target` |
| D2 | 必须 | 构造：A + initial_layer_print_height 0.4→0.44（对照自己的编辑值） | 入库 | `3937a5583b4f` | 拒绝 | `mac_walls_unrelated_setting_changed:initial_layer_print_height` |
| D3 | 必须 | 构造：A + line_width 0.82→0.9（迁移之外的普通键） | 入库 | `f6fa475d1008` | 拒绝 | `mac_walls_unrelated_setting_changed:line_width` |
| D4 | 必须 | 构造：A + inner_wall_speed ['150']→['160']（已迁移键换成第三个值） | 入库 | `883bc141141e` | 拒绝 | `mac_walls_unrelated_setting_changed:inner_wall_speed` |
| D5 | 必须 | 构造：A + 未知键 z_fake_key | 入库 | `75fa59f7f8e3` | 拒绝 | `mac_walls_unknown_addition:z_fake_key` |
| D6 | 必须 | 构造：A + project_schema_version '1'→'2'（24 个新增键之一） | 入库 | `4f388696118c` | 拒绝 | `mac_walls_unknown_addition:project_schema_version` |
| D7 | 必须 | 构造：A 删掉 top_shell_layers | 入库 | `2deab75ee27d` | 拒绝 | `KeyError`（无错误码，error=`'top_shell_layers'`） |
| D8 | 必须 | 构造：A 的 manifest 多记 layer_height（值未变） | 入库 | `4ef620d4725f` | 拒绝 | `pilot_dirty_manifest_out_of_scope` |
| D9 | 必须 | 构造：A 的 manifest 少记 mixed_filament_definitions | 入库 | `6fc941e820d2` | 拒绝 | `pilot_dirty_manifest_out_of_scope` |
| D10 | 必须 | 构造：A + top_shell_layers '3'→3（整数） | 入库 | `39567f70b263` | 拒绝 | `mac_walls_unrelated_setting_changed:top_shell_layers` |
| D11 | 必须 | 构造：夹具 + wall_loops=3 + travel_speed→['400']（没有任何迁移） | 入库 | `88b7b00ca202` | 拒绝 | `mac_walls_unrelated_setting_changed:travel_speed` |
| D12 | 必须 | 构造：A 删掉 different_settings_to_system | 入库 | `6a962cf36ae9` | 拒绝 | `KeyError`（无错误码，error=`'different_settings_to_system'`） |
| E | 必须 | 构造：拷贝基线 + wall_loops=3 + 另外 5 个参数（manifest 未动） | 入库 | `2331e2dfcf49` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| E2 | 必须 | 构造：基线撤掉自身编辑 + wall_loops=3 + manifest + 另外 5 个参数 | 入库 | `7299fc6609ec` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| E3 | 必须 | 构造：A + 同样 5 个参数 | 入库 | `bff164d88a00` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| E4 | 必须 | 构造：A + bottom_shell_layers | 入库 | `bc707f341591` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| E5 | 必须 | 构造：A + layer_height | 入库 | `67f116e38a68` | 拒绝 | `mac_walls_unrelated_setting_changed:layer_height` |
| E6 | 必须 | 构造：A + sparse_infill_density | 入库 | `5d735501ad4f` | 拒绝 | `mac_walls_unrelated_setting_changed:sparse_infill_density` |
| E7 | 必须 | 构造：A + top_shell_layers | 入库 | `c4556b5a8fd0` | 拒绝 | `mac_walls_unrelated_setting_changed:top_shell_layers` |
| E8 | 必须 | 构造：A + travel_speed | 入库 | `cc2b881e061d` | 拒绝 | `mac_walls_unrelated_setting_changed:travel_speed` |
| E9 | 必须 | 构造：E2 摘掉 bottom_shell_layers | 入库 | `74084b5a8e6f` | 拒绝 | `mac_walls_unrelated_setting_changed:layer_height` |
| E10 | 必须 | 构造：E2 摘掉 bottom_shell_layers、layer_height | 入库 | `ade6377097e0` | 拒绝 | `mac_walls_unrelated_setting_changed:sparse_infill_density` |
| E11 | 必须 | 构造：E2 摘掉 bottom_shell_layers、layer_height、sparse_infill_density | 入库 | `951fcc08f8ac` | 拒绝 | `mac_walls_unrelated_setting_changed:top_shell_layers` |
| E12 | 必须 | 构造：E2 摘掉 bottom_shell_layers、layer_height、sparse_infill_density、top_shell_layers | 入库 | `2b5d42978f45` | 拒绝 | `mac_walls_unrelated_setting_changed:travel_speed` |
| F | 必须 | 构造：拷贝基线 + wall_loops=4 | 入库 | `c02ad17ce378` | 拒绝 | `pilot_wall_loops_target` |
| F2 | 必须 | 构造：A 的 wall_loops 3→4 | 入库 | `f16ed0cecb55` | 拒绝 | `pilot_wall_loops_target` |
| F3 | 必须 | 构造：A 的 wall_loops '03' | 入库 | `e8e5e9c5405a` | 拒绝 | `pilot_wall_loops_target` |
| F4 | 必须 | 构造：A 的 wall_loops 3（整数） | 入库 | `50d780543d51` | 拒绝 | `pilot_wall_loops_target` |
| F5 | 必须 | 构造：A 删掉 wall_loops 键 | 入库 | `07671722bcf2` | 拒绝 | `pilot_wall_loops_target` |
| G1 | 必须 | 真实：A，SUT 按 win11-test 在册构建呈现（2.4.0，另一个可执行文件摘要） | 入库 | `436d6baf701f` | 拒绝 | `Walls control baseline was recorded on a different Orca build` |
| G2 | 必须 | 真实：A，SUT 只改版本号 | 入库 | `436d6baf701f` | 拒绝 | `Walls control baseline was recorded on a different Orca build` |
| G3 | 必须 | 真实：A，SUT 只改可执行文件摘要 | 入库 | `436d6baf701f` | 拒绝 | `Walls control baseline was recorded on a different Orca build` |
| G4 | 必须 | 真实：2.3.6 夹具（旧构建的保存件），SUT 按 Mac 构建呈现 | 入库 | `ed1ca79dd1dd` | 拒绝 | `pilot_wall_loops_target` |
| G5 | 边界 | 构造：夹具 + wall_loops=3（2.3.6 schema，无迁移），SUT 按 Mac 构建呈现 | 入库 | `2954dee93a6b` | 通过 | — |
| G6 | 必须 | 真实：A；基线文件换成 2.3.6 夹具，json 未动 | 临时替换 | `436d6baf701f` | 拒绝 | `Committed walls control baseline digest mismatch` |
| G7 | 必须 | 真实：A；基线换成 2.3.6 夹具并同步 digest，json 的 SUT 未动 | 临时替换 | `436d6baf701f` | 拒绝 | `mac_walls_unknown_addition:first_layer_travel_acceleration` |
| G8 | 必须 | 真实：A；基线换成 2.3.6 夹具并同步 digest，json 的 SUT 改成 2.4.0 构建 | 临时替换 | `436d6baf701f` | 拒绝 | `Walls control baseline was recorded on a different Orca build` |
| G9 | 必须 | 内存构造：打开未编辑即保存的件（基线撤掉自身编辑）；基线毒化为 A 自己的工程 | 临时替换 | `0d57d2a890c1` | 拒绝 | `pilot_wall_loops_target` |
| G10 | 必须 | 构造：A + 另外 5 个参数；基线毒化为 A 自己的工程 | 临时替换 | `bff164d88a00` | 拒绝 | `mac_walls_unrelated_setting_changed:bottom_shell_layers` |
| G11 | 必须 | 构造：A + initial_layer_print_height 0.44；基线毒化为 A 自己的工程 | 临时替换 | `3937a5583b4f` | 拒绝 | `mac_walls_unrelated_setting_changed:initial_layer_print_height` |
| G12 | 边界 | 真实：A；基线换成同构建另一次保存（layer SHADOW run 0a24557a，同步 digest） | 临时替换 | `436d6baf701f` | 通过 | — |
| G13 | 边界 | 构造：A + layer_height 0.24（换入基线自带的编辑）；基线同 G12 | 临时替换 | `67f116e38a68` | 通过 | — |
| G14 | 必须 | 构造：A + layer_height 0.3（其他值）；基线同 G12 | 临时替换 | `0af57bef982f` | 拒绝 | `mac_walls_unrelated_setting_changed:layer_height` |
| X1 | 边界 | 构造：A 的 version 改回 2.3.6 | 入库 | `d34099ff7c7c` | 通过 | — |
| X2 | 边界 | 构造：夹具 + wall_loops=3 + travel_speed→['500']（恰为迁移值） | 入库 | `a44acf240a13` | 通过 | — |
| X3 | 边界 | 构造：A 去掉 manifest 里的 wall_loops 条目 | 入库 | `c6fa3dde4f67` | 通过 | — |
| X4 | 必须 | 构造：基线撤掉自身编辑 + 壁环编辑（由基线重建配置） | 入库 | `7522cb815684` | 通过 | — |

sha256 只列前 12 位，全值在 results.json。「基线 = 临时替换」的项，是把判据模块的 `ROOT` 指到
临时目录里的 `walls_control.*` 副本后判的，入库文件未动。

### G 的展开

| 问题 | 对照 | 结果 |
| --- | --- | --- |
| 被判 run 的 SUT 与基线登记的构建不同 | G1（版本和可执行摘要都不同）、G2（只版本不同）、G3（只摘要不同） | 拒绝：`Walls control baseline was recorded on a different Orca build` |
| 基线文件被换掉，json 未动 | G6（换成 2.3.6 夹具） | 拒绝：`Committed walls control baseline digest mismatch`——digest 锁，不是身份锁 |
| 基线文件被换掉，json 的 digest 也同步改了 | G7 | 拒绝，但**不是**身份锁拒的：json 的 SUT 没动，身份闸门放行，由内容闸门拒（`mac_walls_unknown_addition`） |
| json 的 SUT 被改成别的构建 | G8 | 拒绝：different Orca build |
| 基线被毒化成 A 自己的工程 | G9 / G10 / G11 | 仍拒绝：未编辑的保存件（target）、A + 5 个参数、A + 对照编辑键 |

「SUT 身份锁定」比的是 json 里**声明**的构建与被判 run 实测的构建，外加基线文件的 digest；
它不认证基线文件的出身。只换文件不改 json 会被 digest 拒；连 digest 一起改，身份闸门不响，
之后全靠内容闸门（2.3.6 schema 的基线会让每个 2.4.1 保存件都被拒，fail-closed）。

G12–G14 是手头唯一能做的真实换基线：同构建另一次运行（layer SHADOW run `0a24557a`）的保存件。
A 通过（应当如此：同构建、同迁移噪声）；A + `layer_height 0.24`（换入基线自带的编辑）**通过**，
A + `layer_height 0.3` 拒绝——这是豁免条款的一般形态，见问题 1。

## C 的情况

C 在新判据下通过。它和 A 的保存工程在判据眼里是同一份东西：

- `Metadata/project_settings.config` 逐字节相同（602 键，wall_loops "3"）。两个 3mf 唯一
  互异的条目是 `Metadata/model_settings.config`，差异只在 `source_file`（各自运行的暂存目录）。
- `edited.gcode` 只有第 2 行的生成时间戳不同（13:25:57 对 13:35:09），去掉该行后内容相同。
- C 当初被拒，是因为旧 oracle（Windows 轨道 `inspect_preserved_settings`）先遇到
  `pilot_config_unknown_addition`：它只接受已评审的 2.3.6→2.4.0 表示迁移（46 个向量键、8 个
  新增键、version 只认 "2.4.0" 等），而 2.4.1 保存件带 24 个新增键、version "2.4.1"。同一
  函数对 A 同样拒（results.json `run_C_vs_A.old_oracle`）。
- C 记录的 NON_GREEN **不改写**。它当时停在 `verify.saved_project`，其后的宿主检查没有执行过；
  本次对它的保存产物做了离线回放（读回 2/3/3、edited 切片 68 层且 lineage 相符、回显
  `wall_loops=['3']`，均满足），但回放不是重新判定。

## 问题 1：判据比较了哪些键、豁免了什么

判据只读 `Metadata/project_settings.config`，按顺序过五道闸门，遇第一个违规即抛出：

| # | 闸门 | 错误码 | 覆盖它的对照 |
| --- | --- | --- | --- |
| 1 | 入库基线 3mf 的 sha256 == json `control_saved_sha256` | `Committed walls control baseline digest mismatch` | G6 |
| 2 | json `sut`（version, executable_sha256）== 被判 run 的 SUT | `Walls control baseline was recorded on a different Orca build` | G1 G2 G3 G8 |
| 3 | 夹具 wall_loops=="2" 且被判件=="3" | `pilot_wall_loops_target` | B D F F2–F5 G4 G9 |
| 4 | 被判件相对夹具新增的每个键都在基线里且同值 | `mac_walls_unknown_addition:<key>` | D5 D6 G7 |
| 5 | 夹具键逐个（字母序）：wall_loops 跳过；manifest 只许增记 wall_loops；值未变放行；键≠`control_edit.key` 且在基线且等于基线值则豁免 | `pilot_dirty_manifest_out_of_scope`、`mac_walls_unrelated_setting_changed:<key>` | B2 D8 D9（manifest）；B3 D2 D3 D4 D10 D11、E 全系、G10 G11 G14（无关改动） |

被豁免的差异 = 被判件相对夹具的全部差异中，除 wall_loops（2→3）与其 manifest 条目之外的
部分，共 80 项，每项都要求与对照基线**同键同值**。

**(a) 24 个新增键**（夹具没有、2.4.1 保存时写入；值必须等于基线）

| 键 | 值 | 在旧 oracle `_ADDED_DEFAULTS` 里且同值 |
| --- | --- | --- |
| `bottom_color_penetration_layers` | `"3"` | — |
| `enable_tower_interface_cooldown_during_tower` | `"0"` | — |
| `enable_tower_interface_features` | `"0"` | — |
| `filament_adhesiveness_category` | `["300", "100", "100", "100", "100"]` | — |
| `filament_flow_step_size` | `["1", "1", "1", "1", "1"]` | 是 |
| `filament_flow_support` | `["standard", "standard", "standard", "standard", "standard"]` | 是 |
| `filament_grouping_mode` | `"standard"` | 是 |
| `filament_tower_interface_pre_extrusion_dist` | `["10", "10", "10", "10", "10"]` | — |
| `filament_tower_interface_pre_extrusion_length` | `["0", "0", "0", "0", "0"]` | — |
| `filament_tower_interface_print_temp` | `["-1", "-1", "-1", "-1", "-1"]` | — |
| `filament_volume_type` | `["standard", "standard", "standard", "standard", "standard"]` | 是 |
| `first_layer_travel_acceleration` | `"100%"` | — |
| `first_layer_travel_jerk` | `"100%"` | — |
| `nozzle_volume_type` | `["standard", "standard", "standard", "standard"]` | 是 |
| `prime_tower_enable_framework` | `"0"` | — |
| `printer_flow_support` | `["standard"]` | 是 |
| `process_flow_support` | `["standard"]` | 是 |
| `project_schema_version` | `"1"` | 是 |
| `support_interface_min_area` | `"0.25"` | — |
| `support_transition_flow_ratio` | `"1"` | — |
| `support_transition_perimeter` | `"1"` | — |
| `support_transition_speed` | `["50"]` | — |
| `top_color_penetration_layers` | `"3"` | — |
| `tree_support_transition_layers` | `"2"` | — |

**(b) 46 个向量迁移键**：`"x"` → `["x"]`，数值不变。与旧 oracle 的 `_VECTOR_MIGRATIONS`
名单完全一致。

`accel_to_decel_enable`、`accel_to_decel_factor`、`bridge_acceleration`、`bridge_speed`、`default_acceleration`、`default_jerk`、`default_junction_deviation`、`enable_overhang_speed`、`extrusion_rate_smoothing_external_perimeter_only`、`gap_infill_speed`、`infill_jerk`、`initial_layer_acceleration`、`initial_layer_infill_speed`、`initial_layer_jerk`、`initial_layer_speed`、`initial_layer_travel_speed`、`inner_wall_acceleration`、`inner_wall_jerk`、`inner_wall_speed`、`internal_bridge_speed`、`internal_solid_infill_acceleration`、`internal_solid_infill_speed`、`ironing_speed`、`max_volumetric_extrusion_rate_slope`、`max_volumetric_extrusion_rate_slope_segment_length`、`outer_wall_acceleration`、`outer_wall_jerk`、`outer_wall_speed`、`overhang_1_4_speed`、`overhang_2_4_speed`、`overhang_3_4_speed`、`overhang_4_4_speed`、`slow_down_layers`、`slowdown_for_curled_perimeters`、`small_perimeter_speed`、`small_perimeter_threshold`、`sparse_infill_acceleration`、`sparse_infill_speed`、`support_interface_speed`、`support_speed`、`top_surface_acceleration`、`top_surface_jerk`、`top_surface_speed`、`travel_acceleration`、`travel_jerk`、`travel_speed`

**(c) 10 个其他改动键**

| 键 | 类别 | 夹具值 → 保存值 |
| --- | --- | --- |
| `version` | schema 版本 | `"2.3.6"` → `"2.4.1"` |
| `print_settings_id` | 预设改名 | `0.40 Standard @Snapmaker U1 (0.8 nozzle)` → `0.40mm Standard @Snapmaker U1 (0.8 nozzle)` |
| `filename_format` | 文件名模板占位符 | `{input_filename_base}_{filament_type[0]}_{print_time}.gcode` → `{input_filename_base}_{filament_type[initial_tool]}_{print_time}.gcode` |
| `machine_start_gcode` | 机器模板 G-code 刷新 | 模板文本换新：116 → 125 行 |
| `machine_end_gcode` | 机器模板 G-code 刷新 | 模板文本换新：8 → 23 行 |
| `change_filament_gcode` | 机器模板 G-code 刷新 | 模板文本换新：47 → 67 行 |
| `exclude_object` | 默认值变更 | `"0"` → `"1"` |
| `max_bridge_length` | 默认值变更 | `"10"` → `"0"` |
| `raft_first_layer_expansion` | 默认值变更 | `"2"` → `"-1"` |
| `tree_support_branch_angle_organic` | 默认值变更 | `"40"` → `"45"` |

合计：夹具 578 键 = 520 个任何改动都拒的键 + 56 个只在基线值上豁免的键 + 2 个有专属规则的键
（wall_loops、different_settings_to_system）；另有 24 个新增键必须等于基线值。

**这些豁免会不会掩盖一次真实的无关改动？**

1. 520 个键：不会，任何改动都拒。其中包括 `initial_layer_print_height`——对照自己的编辑键被
   显式排除在豁免之外（D2、B3、G11）。
2. 56 个豁免键：只有恰好等于基线值才豁免。46 个向量键的豁免值就是原数值的列表形式，不构成
   一次编辑；version、预设名、文件名模板、三个机器模板 G-code 不是操作者在参数页输入的工艺
   参数。真正可能被吸收的只有 4 个默认值变更键，而且只限一种情形：保存值恰好等于迁移后的
   值（如 `exclude_object` "1"）。这个值是加载后未编辑就在用的值：入库基线的 manifest 只记
   `initial_layer_print_height` 与 `mixed_filament_definitions`，这 4 个键不在其中；未编辑的基线
   切片的 G-code 配置回显里，55 个可回显的迁移键全部等于保存件的迁移值（`version` 不回显）。
   所以被吸收的那次「编辑」没有改变任何取值，切片结果与未编辑时相同；改成任何别的值都会被拒
   （豁免只认基线值这一个值）。这一点是从保存件与 G-code 推出的，没有在界面上实测（本任务
   不跑 GUI）。
3. 独立旁证：切片器自己写进 G-code 的配置回显，基线切片对编辑后切片共 590 键，只有
   `wall_loops`（2→3）和 `different_settings_to_system` 两行不同（A、C 皆然）。工程文件之外的
   第二条通道同样没有无关改动。
4. 仍然存在的宽松处。它们不掩盖无关改动，但界定了「通过」证明了什么：
   - 不要求迁移签名（X1、G5）：一份只改了 wall_loops 的 2.3.6 schema 文件，只要身份按相等
     呈现就通过。通过证明的是「相对夹具，除 wall_loops 外只存在基线也产生过的差异」，不是
     「这份文件由该构建写出」。
   - manifest 是上界（X3）：wall_loops 条目缺失也通过。
   - 基线文件的出身不被认证（G6、G7）。
   - 豁免的一般形态（G13）：基线若在 `control_edit.key` 之外还带着自己的真实编辑，那个值就
     成为该键的豁免值。入库基线只动了一个键，且正是登记的键（见下「基线卫生」），所以当前
     不触发；重采基线时，对照运行必须只动登记的那一个键。
   - 删键的拒绝没有错误码（D7、D12）：`KeyError` 被 `run()` 记成 NON_GREEN，error 字段只有
     裸键名。是拒绝，只是未编码。

**基线卫生**（对照对 A、对照对 C，结论相同）：24 个新增键逐个同值；双方都改的 56 个键逐个
同值；只在对照里改的是 `initial_layer_print_height`，只在 run 里改的是 `wall_loops`；无删键；
manifest 各记各账。X4 由入库基线撤掉自身编辑、再加上壁环编辑重建出的配置，与 run A 的配置
完全相同。

## 问题 2：读回与回显的来源

**读回 2/3/3：经 GUI 得到，不是读文件。**

| 相位 | 通道 | 代码位置 |
| --- | --- | --- |
| baseline、reopen（各一个独立进程） | 屏幕截图 + Vision OCR 读 Strength 页「Wall loops」值格 | `runner/macos/project_copy.py:202-236`（`screen_capture`/`screen_ocr`）、`:270-275`（`ocr_wall_read`）；落账 `:423-430` |
| edit | 点击值格后物化的 AXTextField：AX 写入 3，再 AX 读回 | `runner/macos/project_copy.py:305-310`（`edit_walls_and_save`） |
| 宿主断言 | 三相位读回必须为 `["2","3","3"]` | `runner/macos_project_copy.py:216` |

证据文件：`docs/runs/evidence/mac-walls-a5-2026-11-23/walls_run_306d3efe_result.json`
（`guest.phases.{baseline,edit,reopen}.wall`，进程 25404/25754/26039；与
`artifacts/mac_project_copy/306d3efe6882427e806afaaf9e2ad7f1/result.json` 逐字节相同，sha256
`ff694a0a…`）。C 的对应文件是同目录的 `walls_run_ffe0c6e4_nongreen_result.json`
（进程 21385/21645/22022）。

读回的性质需要如实说明：它是**读到期望值才落账**的闸门。baseline/reopen 相位里 worker 轮询
（最长 30 s）直到 OCR 读数等于期望值（"2"/"3"），否则超时进 NON_GREEN（`Strength wall-loops
OCR value mismatch in <phase>`）；edit 相位先断言 AX 读回等于 "3"（否则 `Wall-loops readback
mismatch`）再返回。所以落账的值必然等于期望值：它不会输出一个错的值，只会失败；它证明的是
「在该相位的活界面上读到了期望值」。worker 不解析保存件来取 wall_loops（对保存件只算摘要）。
值的独立佐证来自另外两条通道：保存件里的 `wall_loops: "3"`（与切片 receipt 的 `project_sha256`
绑定）和下面的 G-code 回显。

**G-code 回显 `wall_loops=['3']`：宿主直接读文件。**

- 文件来源：worker 用 `lsof` 找到切片器进程打开的临时盘面 G-code（`runner/macos/project_copy.py:325-346`
  `open_plate`），复制并出具 receipt（sha256、size、pid、`project_sha256`、
  `source: open_process_plate`；`:349-374` `slice_plate`），随 SSH 回执传回宿主落盘
  （`runner/macos_project_copy.py:165-168`）。它不是 GUI「Export G-code」的产物
  （`gui_gcode_export: NOT_TESTED`）。
- 读取：宿主先过 `verify_plate` 的 lineage 核对（`runner/macos_project_copy.py:118-129`），再对
  `edited.gcode` 跑 `config_value_all`（`:225`）。
- 证据文件：`artifacts/mac_project_copy/306d3efe6882427e806afaaf9e2ad7f1/edited.gcode`（sha256
  `cd78d1a8…`，第 7167 行 `; wall_loops = 3`）；同目录 `baseline.gcode`（`2ccfab66…`，第 6291 行
  `; wall_loops = 2`）。结果记在同一个 result.json 的 `wall_loops_gcode_echo` 与
  `guest.slice_receipts.edited`。C 的对应文件是
  `artifacts/mac_project_copy/ffe0c6e45c2c456b94e904ded891c1ac/edited.gcode`（`9e1fdb96…`，第 7167 行）。

## 方法、输入与边界

- 判据未改：`runner/macos_project_copy.py` 工作区与 HEAD 相同（最近提交 `c6c259d`），
  `verify_walls_differential` 函数摘要 `30dd8a0e…`；跑完后 `git status -- runner/` 为空
  （results.json `criterion`、`integrity`）。
- 构造方式：复制 3mf，只重写 `Metadata/project_settings.config`（4 空格缩进，保留原换行符与
  结尾换行；对夹具、基线、A、C 做空改写后回读逐字节相同），按原条目元数据重新打包。每个
  构造件都核验过：配置差异恰为种植的键，其余 zip 条目逐字节相同。构造件只写在临时目录
  （results.json `construction.temp_dir`，可删），证据目录里只有摘要与种植内容。
- 输入绑定：夹具 sha256 == `LAYER_FIXTURE_SHA256`；基线 sha256 == json 摘要；A/C/L 的保存件
  sha256 同时等于各自 receipt 的 `saved_sha256` 与切片 receipt 的 `project_sha256`；A/C 的
  result.json 与入库的 A5 副本逐字节相同。A/C/L 的保存件只在本机 `artifacts/`（gitignored）。
- 没做的：G 的真实异地构建保存件；判据之后的宿主检查（`inspect_project` 等）没有在构造件上
  执行——本包只证明 `verify_walls_differential` 一个函数；C 不重新判定；未写回飞书（任务未
  要求，也没有状态变化）。

## 复跑

```bash
PYTHONHASHSEED=0 .venv/bin/python -B tools/mac_walls_negative_controls.py
```

需要本机的 `artifacts/mac_project_copy/` 产物；退出码 0 表示 52 项全部与预测一致。加 `--out`
可写到别的文件。`PYTHONHASHSEED` 只影响 G7 报出的键名（新增键的集合迭代序），不影响判定。
