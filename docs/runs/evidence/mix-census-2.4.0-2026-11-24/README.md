# 混色用例 #288 / #289 可达性：2.4.0 构建上的普查（2026-11-24）

**结论：不可按用例步骤从界面驱动。** 两条用例涉及的 9 个工程配置键里，只有
`mixed_filament_definitions`（Add Mix 对话框）有编辑控件；其余 8 个在 2.4.0 构建的
Color Mixing 面板、Add Mix 四个页签、混色条目的 Options 菜单里都没有控件。

- 探针：`uia_param_mix_census`（`harness/param_mix_census.py`），fa706g3 run
  `15af746c`（与客机同一份 2.4.0 构建、同版预设），原始输出 `mix_census_15af746c.log`。
- 看到了什么：侧栏「Color Mixing」一条混色 `F3 50%+F2 50%`，Options 菜单 =
  Edit / Merge with / Delete；Add Mix 对话框页签 Ratio / Cycle / Match / Gradient，
  文本只有 Filaments / Target Color / Hex / Filament Selection / Mixing Ratio /
  Min Mix Ratio / Preview / Mix Effect / Legend / Blend result / Color preview /
  Exact preset mixes / Mixing Recommendations；输入框只有 Cycle 的 `12` 与 Match 的 `94C3C`。
  对话框横幅：`Filament 1 and Filament 2 cannot be mixed. Please select filaments of the same type.`
- 关键词命中说明：`gradient` 是页签名（条目内部的分配模式），不是工程键
  `mixed_filament_gradient_mode`；`layer height` / `surface` 来自右侧 Process 面板的行
  （Layer height / First layer height），不是混色控件。
- 源码对照（两份树一致）：2.3.5（fa706g3 agent 调研：带 Bias 数值框的行编辑面板被无条件
  `Hide(); return;` + `#if 0`，Plater.cpp:6824-6835；`update_mixed_filament_panel` 只把读到的
  值原样写回，:6677-6698 / :6770-6778）；2.4.1（宿主源码树：Plater.cpp:7387-7390 读、
  :7463-7470 写回；工艺页「Color Mixing (Experimental)」组只有 3 个 `dithering_local_z_*` 行，
  Tab.cpp:2287-2311 把这些键列为不显示）。`mixed_filament_region_collapse` 面板连读都不读。
- 附带事实（2.3.5 源码，未在 2.4.0 上复测）：层高 A/B 的生效值被钳到
  `[height_lower_bound, height_upper_bound]`（默认 [0.04, 0.16]），0.20 / 0.40 都按 0.16 生效；
  点彩两项在序列化时会被移出定义串，不影响 G-code。

含义：#288 的 5 个键里 4 个、#289 的 4 个键里 3 个只能随工程或预设载入（夹具播种），
不是界面编辑。按「只走界面、不改配置」的纪律，这两条在本构建上记为**不可界面驱动**，
不写参数场景模块。
