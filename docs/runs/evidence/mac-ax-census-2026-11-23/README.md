# Mac AX 半普查（任务 A3）：Orca 2.4.1 参数面板可读面收割

标签 `mac-author`，2026-11-23。宿主 GLM 总控派发，A2 已证 LaunchAgent 后台 Aqua
会话可读 AXValue/AXHelp，本任务对参数设置做纯读取收割，给主线标签图谱补
path 行渲染名旁证（Mac/Win 同源 tooltip 文案）。

## 产物

- `ax_census.json`：`{"version":"2.4.1", "rows":[{"mode":"flat|outline","row":{…}}, …], "meta":{…}}`，
  共 82 行（flat 48 + outline 34）。每行含 role、AXHelp 全文、AXValue（文本+数值）、
  AXDescription/AXIdentifier/AXPlaceholderValue/AXTitle、坐标尺寸、AXEnabled，
  以及从 tooltip `parameter name\t: <key>` 行提取的顶层 `key` 字段。

## 方法（只读纪律）

- 通道与 A2 相同：一次性 LaunchAgent（gui/502 后台 Aqua 会话，签名 Python.app），
  探针 `runner/macos/panel_probe12.py`，驱动 `tools/mac_panel_probe.py panel_probe12.py census_a3`；
  单次启动，GUI 接管约 2 分钟（红线 ≤20 分钟），540s 硬保险丝未触顶，退场
  `orca_left: []`，未触碰前台 coil（console 501）。
- 交互仅视图态：Advanced 复选框 AXPress、视图切换复选框 AXPress、页切换带
  x525/x390 坐标点击、disclosure triangle AXPress（1 次，展开出第 3/4 行）。
  无 AXValue 写入、无焦点抢占、无保存；datadir 一次性播种后丢弃。

## 计数

| 面 | 行数 | 带参数键 | 说明 |
| --- | --- | --- | --- |
| flat（Advanced ON） | 45（24 AXTextField + 21 AXCheckBox†） | 45 | 另有 flat_default 6 行（2 字段+3 开关）与 flat_return 45 行复核 |
| flat 合计（去重后） | 48 | 47 | 唯一无键行 = AXScrollBar（页滚动条） |
| outline | 34 | 0 | 全部自绘 cell，见下 |

† 去重后 22 个 AXCheckBox 带 key：`precise_outer_wall`、`only_one_wall_top`、
`only_one_wall_first_layer` 各在两个分区出现（47 行带键 ↔ 44 个不同键，多对一如实保留）。
键行覆盖 y832-2608（含离屏全量暴露），`wipe_speed` 为 AXStaticText（值列非编辑框）。

44 个不同键（按 y 序）：layer_height, initial_layer_print_height, line_width,
initial_layer_line_width, outer_wall_line_width, precise_outer_wall,
inner_wall_line_width, top_surface_line_width, only_one_wall_top,
sparse_infill_line_width, only_one_wall_first_layer,
internal_solid_infill_line_width, support_line_width, staggered_inner_seams,
seam_gap, role_based_wipe_speed, wipe_speed, wipe_on_loops,
wipe_before_external_loop, slice_closing_radius, resolution,
enable_arc_fitting, xy_hole_compensation, xy_contour_compensation,
elefant_foot_compensation, elefant_foot_compensation_layers,
precise_outer_wall(重复), precise_z_height, hole_to_polyhole, is_infill_first,
top_solid_infill_flow_ratio, bottom_solid_infill_flow_ratio,
only_one_wall_top(重复), min_width_top_surface,
only_one_wall_first_layer(重复), reduce_crossing_wall,
small_area_infill_flow_compensation, bridge_flow, internal_bridge_flow,
bridge_density, internal_bridge_density, thick_bridges,
thick_internal_bridges, detect_overhang_wall, make_overhang_printable,
extra_perimeters_on_overhangs, overhang_reverse。

## outline 面（如实记录的墙）

- AXOutline 物化 2 行（y742/760），triangle 展开 1 次后物化 4 行槽位
  （742/760/767/792，y767 为叶行=参数行，y792 为子组）；行/列/三角形结构、
  坐标、AXIdentifier（列为指针串）全收，但 cell 值均为
  `<wxCustomRendererObject: 0x…>`——自绘渲染，AX 无文本，0 个键线索。
- triangle 自身 AXValue 不可读（非 CFNumber/CFBoolean），无法程序化判断展开态。
- 页切换带 x525 点击后 AXOutline 消失（仅剩滚动条），该 tab 不暴露 outline——
  与 A2「x465 与 x525 切到 outline 页」的粗记有差，以本 census 为准。
- 复核：x390 点回扁平页后 45 行签名与 Advanced 态一致（无状态漂移）。

## Mac 独有差异 / 限制（供主线对照）

1. 扁平页行**标签列不进 AX**（仅值列控件暴露）；可见标签需从 tooltip 首行或
   Win 侧同源文案反查——本 census 的 `key` 即 tooltip 尾部的官方参数名。
2. 复选框勾选态不可读（AXValue 既非文本也非数值）；文本字段值全可读。
3. outline 自绘 cell 无文本（见上），与 A2 的硬虚拟化结论一致。

## 溯源

- 原始收割（本机，git 惯例不入库）：`artifacts/mac_probes/2026-11-22/census_a3/`
  （result.json + 分状态 dump + worker.log）。
- 复跑：`.venv/bin/python -B tools/mac_panel_probe.py panel_probe12.py <name>`。
