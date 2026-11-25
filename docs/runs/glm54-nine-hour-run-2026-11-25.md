# 九小时三机跑批（2026‑11‑25）：没有新增完整覆盖，没有发布 GREEN

本轮 #276、#264 两行只做到纯提速，八行补了部分证据（补覆盖，不计闭环），两次原生模型对照和整条 Mac 线没有通过。最终引擎 `2a17376` 上的 42 行参数族回归已跑完：41 行 SHADOW，#294 是 NON_GREEN，它是 11‑24 就开着的行。客机上的脚本运行都是 SHADOW，两次原生模型对照是 NON_GREEN；fa706g3 和 Mac 按 README 第 6 条最高记 SHADOW。第一次推送之后两台机器继续补覆盖到 08:50 停派，那一部分见文末「追加覆盖」，不计入上面的数字。逐项文件见[证据包](evidence/ninehour-2026-11-25/README.md)。

## 结论与范围

窗口从 T0 2026‑11‑25 01:29:12（北京时间）起九小时。三台机器都从 `636a733` 起跑。要合并的引擎是 `2a17376`：它比 `d5fc2fa` 多一个提交（停滞路径的修正），`d5fc2fa` 又只比引擎提交 `e3bfdfe` 多一个收据工具及其单测。客机 `win11-test` 是回归证据机。人工分钟未测。

| 机器 | 今晚交付 | run 数 | 评级 |
|---|---|---:|---|
| `win11-test` | #276 两种初态、#264 两个模型的基线和全部候选；最终引擎 `2a17376` 上的复核 4 次；最终引擎回归的客机一半（21 行），另给 #294 加跑一次；两次原生模型对照；6 条补覆盖；进行中的自有模型孪生（本版不计） | 75 | SHADOW 71，NON_GREEN 3，派发失败 1 |
| `fa706g3` | #276 Quality 的基线和候选；#264 两个模型的计时版、K1、K2；最终引擎复核 2 次；最终引擎回归的 fa706g3 一半（21 行）；3 条补覆盖；进行中的多形状夹具孪生（本版不计） | 60 | SHADOW 56，NON_GREEN 3，派发失败 1 |
| Mac | 壁环数 2→3 一次，未通过；8 次探针 | 1 | NON_GREEN（只见于 `findings-sheet.md`） |

四类汇总按飞书记录 ID 去重，一行可以落在不止一类里：

- 本轮新增完整覆盖 0 条。
- 补齐部分证据 8 条：#255、#265、#266、#267、#268、#269、#272、#295。都是补覆盖：脚本在空闲机器上多跑一次，过了自检并导出；单独记账，不计闭环，也不改 11‑24 对照表的覆盖列。
- 纯提速 2 条：#264、#276。同机、同构建线、同初态，动作秒分别省约 40 秒和 15 秒；最终引擎 `2a17376` 上复核过，节省还在（第 3 节）。
- 失败或待确认 3 条：#265、#276 的原生模型对照都是 NON_GREEN，配对 0 次；#294 在最终引擎回归里是 NON_GREEN（fa706g3 `1a4c0845`、客机 `9db255d4`），它是 11‑24 就开着的行，不是这次改动造成的。Mac 的壁环数运行不对应飞书原行，不计入行数。
- 已恢复的失败轮 1 条：#268。在 `d5fc2fa` 上失败过，重试通过，最终引擎 `2a17376` 上的回归也通过（第 3 节）。

最终引擎回归的 42 行（41 行 SHADOW）只确认引擎改动没有破坏该行已有的写入和导出，不进这四类，见第 5 节。

## 逐条对照

飞书原文取自仓库里的快照 `docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/`。下面各行的步骤 2–4 都是「使用默认参数完成基准切片并保存产物。一次性应用本用例的组合参数后重新切片。对照基准检查配置、预览、G-code及必要实物。」，预期 1 都是「组合参数写入正确，切片成功并产出G-code。」，不再重复。

| 飞书行 | 前置条件的模型 | 步骤 1（原文） | 预期 2、3（原文） | 今晚的运行 | 未通过项 |
|---|---|---|---|---|---|
| #276 `reczz28b6mRAyH5p` 速度高级-流量与机器上限组合 | 标准模型 > 立方体 | outer_wall_speed（外墙速度）=700；layer_height（层高）=0.20；outer_wall_line_width（外墙线宽）=0.42；filament_max_volumetric_speed（最大体积速度）=15；machine_max_speed_x（X最大速度）=500 | 2. 外墙速度先受体积流量限制到约178mm/s。 3. 同时不超过机器X轴500mm/s，超限部分降速且路径不变。 | 客机 Quality：基线 `ec032d7c`、`eebdf238`，候选 `66048b9d`、`c9e2ee61`，最终引擎 `2a17376` 上的复核 `675a3c27`。客机 Strength：基线 `5359abca`，候选 `fe4a956a`、`37ccc139`，最终引擎复核 `29e6b834`。fa706g3 Quality：基线 `82f53908`，候选 `194e79b5`、`3fe3ff18`，最终引擎复核 `63ee7577`。都是 SHADOW，配对完成。`d5fc2fa` 上的复核 `9bc10b3f`、`db27fe2c`、`9d6d1eb3` 不是最终引擎。最终引擎回归（`uia_param_speed_limits`，fa706g3）`9d89930f` SHADOW。原生模型对照 `2053992c` 是 NON_GREEN | 写入：外墙速度 200→700，槽 1 最大体积速度 12→15；层高、线宽、X 上限本来就是步骤值。预期 2：外墙峰值 202.956 mm/s，不是约 178。预期 3：X 分量峰值 202.956 mm/s，500 的上限没有起作用，「超限部分降速」无从观察；「路径不变」对外墙成立，整份导出件只在 Strength 基线那一次不同（第 3 节）。预览没有核对 |
| #264 `reczz28b6mRB0mjp` 悬垂-识别与分档速度组合 | 实用模型 > 欧特克FDM测试 | detect_overhang_wall（识别悬空外墙）=1；enable_overhang_speed（悬垂降速速度）=1；overhang_1_4_speed（悬垂 10%–25% 速度）=40；overhang_2_4_speed（悬垂 25%–50% 速度）=30；overhang_3_4_speed（悬垂 50%–75% 速度）=20；overhang_4_4_speed（悬垂 75%–100% 速度）=10；overhang_totally_speed（100%速度）=5 | 2. 各悬垂区间的F分别≈2400/1800/1200/600/300。 3. 非悬垂区和桥接区F不变。 | FDM 测试模型（飞书原行）：客机基线 `b697f7c2`、计时版 `9c04338f`、K1 `2910969d` 和 `e15b8b93`、K2 `9ff32b28` 和 `b97452a8`；fa706g3 计时版 `0a337de9`、K1 `c7029cc0` 和 `bed005d7`、K2 `e9167b36` 和 `5a6d113d`。立方体（本行的对照）：客机基线 `7484bd43`、计时版 `778bbfa2`、K1 `b7ce6d2b` 和 `173f72ec`、K2 `95422bb0` 和 `f37f49fd`；fa706g3 基线 `19d61032` 和 `8e207463`、计时版 `76b85931`、K1 `d2358953` 和 `83a295d9`、K2 `d03f10c8` 和 `9d2adda0`。最终引擎 `2a17376` 上的复核：立方体客机 `0f1e7139`、fa706g3 `3f1397b0`；最终引擎回归（fa706g3）`b82b9932`。另有客机多形状夹具补覆盖 `930aa957`。都是 SHADOW | 预期 1：overhang_totally_speed=5 没有写入，2.4.0 没有这个参数。预期 2：FDM 测试模型的 Overhang wall 段只有 F1980 和 F3000。预期 3：桥接段共 7898.1 mm，其中 F3000 从默认切片的 7897.7 mm 降到 7466.2 mm；258 个比较层里 151 层的非墙进给变快。判据不读本行导出件的 G-code（第 4 节）。预览没有核对 |
| #265 `reczz28b6mRAzpVx` 悬垂-风扇与翘边组合 | 实用模型 > 欧特克FDM测试 | enable_overhang_bridge_fan（悬垂/桥接强制冷却）=1；overhang_fan_threshold（冷却悬空阈值）=10%；overhang_fan_speed（悬垂风扇速度）=80%；slowdown_for_curled_perimeters（翘边降速）=1 | 2. 悬垂比例超过10%时M106升至80%。 3. 翘边区域自动降速，普通表面风扇和F不变。 | 客机 `compare_265_quality` 基线 `6da67943`（配对是宿主离线补做的）；最终引擎 `2a17376` 上的复核 `e086a1cb`，回归 `e23232a3`（客机）；fa706g3 补覆盖 `4cc00ac9`。都是 SHADOW。`d5fc2fa` 上的复核 `b7778cd5` 不是最终引擎。原生模型对照 `eefe9d78` 是 NON_GREEN | 本轮没有对照预期核对。11‑24 对照表记的缺口不变：导出中 PWM 204 为 0 条、167 段普通顶面提速；10% 触发边界未证 |

其余被本轮触及的行只有补覆盖或回归，下表由快照和 `feishu-216-ninehour.json` 生成。它们都没有对照飞书预期核对，原有缺口见对照表的「未覆盖项与适用边界」一列。

| 飞书行 | 前置条件的模型 | 步骤 1（原文） | 预期 2、3（原文） | 今晚的运行 |
|---|---|---|---|---|
| #254 `reczz28b6mRB1GVG` 层高-首层与常规层高组合 | 标准模型 > 球 | initial_layer_print_height（首层层高）=0.25；layer_height（层高）=0.20 | 2. 首层Z=0.25mm，第2层起按0.20mm递增。 3. 层数、总高度和后续层Z步进与默认基准一致。 | 最终引擎 2a17376 回归 1 次（fa706g3，`1f6c810a`，SHADOW） |
| #255 `reczz28b6mRB0WGN` 线宽-全特征线宽组合 | 标准模型 > 立方体 | line_width（默认线宽）=0.42；initial_layer_line_width（首层线宽）=0.50；outer_wall_line_width（外墙线宽）=0.42；inner_wall_line_width（内墙线宽）=0.45；top_surface_line_width（顶面线宽）=0.40；sparse_infill_line_width（稀疏填充线宽）=0.45；support_line_width（支撑线宽）=0.42 | 2. 各特征线宽分别等于设置值。 3. 各路径E/mm匹配线宽×层高，误差≤2%，外形不变。 | 补覆盖 1 次（客机 win11-test，`d318815e`，SHADOW）；最终引擎 2a17376 回归 1 次（客机 win11-test，`473c4e7c`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #256 `reczz28b6mRAynyS` 接缝-位置/间隙/擦拭组合 | 标准模型 > 圆柱体 | seam_position（接缝位置）=aligned（对齐）；seam_gap（接缝间隔）=15%；wipe_on_loops（闭环擦拭）=1；wipe_speed（擦拭速度）=50；role_based_wipe_speed（自动擦拭速度）=1 | 2. 接缝位于aligned（对齐）方向，每层1条且间隙≈15%。 3. 外墙结束生成擦拭路径，擦拭F≈3000，正常外墙F不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`fefd58ea`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md）；派发失败 1 次（没有到 GUI，无评级；明细见 family-regression.md） |
| #257 `reczz28b6mRB1nLf` 精度-尺寸补偿组合 | 实用模型 > Orca误差测试 | elefant_foot_compensation（象脚补偿）=0.15；xy_contour_compensation（X-Y 外轮廓尺寸补偿）=0.10；xy_hole_compensation（X-Y 内轮廓尺寸补偿）=-0.10；precise_outer_wall（精准外墙尺寸）=1 | 2. 首层外轮廓内缩≈0.15mm，第2层恢复名义值。 3. 外墙外扩≈0.10mm、孔洞收缩≈0.10mm，精准外墙误差≤0.001mm。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`d64dc969`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #258 `reczz28b6mRAyQE3` 精度-圆弧/分辨率/间隙闭合组合 | 实用模型 > Orca误差测试 | enable_arc_fitting（圆弧拟合）=1；precise_z_height（精准Z高度）=1；resolution（分辨率）=0.012；slice_closing_radius（切片间隙闭合半径）=0.049 | 2. 圆弧输出G2/G3或arc元数据，轮廓误差≤0.012mm。 3. 最终Z误差≤0.001mm，约0.098mm以内缝隙闭合、更宽缝隙保留。 | 最终引擎 2a17376 回归 1 次（fa706g3，`3a43c6fd`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #259 `reczz28b6mRB0WWP` 熨烫-顶面参数组合 | 标准模型 > 立方体 | ironing_type（熨烫类型）=top（仅顶面）；ironing_flow（熨烫流量）=10%；ironing_spacing（熨烫间距）=0.15；ironing_speed（熨烫速度）=60 | 2. 仅顶面生成熨烫路径，线距≈0.15mm。 3. 熨烫E按10%流量生效，F≈3600，非目标表面不变。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`1f79a0ce`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #260 `reczz28b6mRAxxD7` 墙生成器-Arachne薄壁组合 | 标准模型 > 文字浮雕 | wall_generator（墙生成器）=arachne（Arachne薄壁）；min_bead_width（墙最小线宽）=85%；min_feature_size（最小特征尺寸）=25%；wall_distribution_count（墙分布计数）=3；wall_transition_angle（墙过渡阈值角度）=10；wall_transition_length（墙过渡长度）=100%；wall_transition_filter_deviation（墙过渡过滤间距）=25% | 2. 薄壁与变宽度墙路径由Arachne重算，外轮廓连续。 3. 墙线按分布数过渡，无0宽线，外轮廓和总墙数不异常。 | 最终引擎 2a17376 回归 1 次（fa706g3，`ea11c710`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #261 `reczz28b6mRAzTBr` 墙壁和表面-单墙与避墙组合 | 实用模型 > 小船 | only_one_wall_top（顶面单层墙）=1；min_width_top_surface（单层墙阈值）=200%；only_one_wall_first_layer（首层仅单层墙）=1；reduce_crossing_wall（避免跨越外墙）=1；max_travel_detour_distance（避免跨越外墙-最大绕行长度）=2mm | 2. 窄顶面和窄区首层仅1圈墙，无额外填充。 3. 空驶不跨越外墙，必要时绕行且绕行距离不超2mm。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`10c4fed6`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #262 `reczz28b6mRAyIRW` 墙壁和表面-表面流量组合 | 实用模型 > 小船 | top_solid_infill_flow_ratio（顶部表面流量比例）=1.1；bottom_solid_infill_flow_ratio（底部表面流量比例）=0.9；print_flow_ratio（对象流量比率）=1.0 | 2. 顶面E增加≈10%，底面E减少≈10%，对象整体流量不变。 3. 各表面路径和模型外形保持基准。 | 最终引擎 2a17376 回归 1 次（fa706g3，`f3daf5c3`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #263 `reczz28b6mRB1jdF` 搭桥-桥接质量组合 | 实用模型 > 欧特克FDM测试 | bridge_flow（桥接流量）=1.0；bridge_density（外部桥接密度）=100%；thick_bridges（厚桥）=1；bridge_angle（桥接方向）=0；max_bridge_length（最大桥接长度）=30mm | 2. 桥接线方向为0°，线距对应100%密度，桥接区连续锚固。 3. 厚桥开启后桥接层数/流量增加，超过30mm跨度触发支撑或提示。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`7d8d505a`，SHADOW） |
| #266 `reczz28b6mRAyM4X` 墙-圈数与薄壁组合 | 实用模型 > 小船 | wall_loops（墙层数）=4；detect_thin_wall（检查薄壁）=1 | 2. 正常区域总墙数为4圈，薄壁生成单线墙。 3. 每圈闭合无断墙，模型外形尺寸不变。 | 补覆盖 1 次（fa706g3，`51f5d2b0`，SHADOW）；最终引擎 2a17376 回归 1 次（fa706g3，`09b59283`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #267 `reczz28b6mRB1b7s` 外壳-层数/图案/颜色渗透组合 | 标准模型 > 立方体 | top_shell_layers（顶部壳体层数）=5；bottom_shell_layers（底部壳体层数）=3；top_surface_pattern（顶面图案）=concentric（同心）；bottom_surface_pattern（底面图案）=rectilinear（直线）；top_color_penetration_layers（顶部涂色渗透层数）=3 | 2. 顶/底实体层数分别为5/3层，图案按设置切换。 3. 顶部颜色渗透3层，颜色边界与层号一致，模型外形不变。 | 补覆盖 1 次（客机 win11-test，`819d192b`，SHADOW）；最终引擎 2a17376 回归 1 次（客机 win11-test，`2acd39bd`，SHADOW） |
| #268 `reczz28b6mRAz0f1` 填充-密度/图案/方向/重叠组合 | 标准模型 > 立方体 | sparse_infill_density（稀疏填充密度）=20%；sparse_infill_pattern（稀疏填充图案）=gyroid（陀螺螺旋）；infill_direction（填充方向）=45；infill_wall_overlap（填充/墙 重叠）=15%；gap_fill_target（缝隙填充范围）=everywhere（全部区域） | 2. 填充线距对应20%密度，图案和方向符合设置。 3. 填充与墙重叠15%，缝隙填充完整，外墙尺寸不变。 | 补覆盖 1 次（客机 win11-test，`e9089ec1`，SHADOW）；最终引擎 2a17376 回归 1 次（fa706g3，`72f7f6de`，SHADOW）；d5fc2fa 上另有 9 次（NON_GREEN/SHADOW，不是最终引擎，含一次失败和重试；明细见 family-regression.md） |
| #269 `reczz28b6mRB164l` 强度高级-填充结构组合 | 实用模型 > 欧特克FDM测试 | infill_combination（合并填充）=1；internal_bridge_support_thickness（内部桥接支撑厚度）=0.6mm；minimum_sparse_infill_area（稀疏填充最小阈值）=10mm²；bridge_angle（桥接方向）=45；detect_narrow_internal_solid_infill（识别狭窄内部实心填充）=1；ensure_vertical_shell_thickness（确保垂直外壳厚度）=1 | 2. 相邻填充层合并，小区域不生成稀疏填充。 3. 内部桥接有支撑，桥接线45°，狭窄区转实心且垂直壳体完整。 | 补覆盖 1 次（客机 win11-test，`9f8f1169`，SHADOW）；最终引擎 2a17376 回归 1 次（客机 win11-test，`b4129312`，SHADOW） |
| #270 `reczz28b6mRAyhVJ` 首层速度-全速度链组合 | 标准模型 > 立方体 | initial_layer_speed（首层速度）=30；initial_layer_infill_speed（首层填充速度）=40；initial_layer_travel_speed（首层空驶速度）=150 | 2. 首层外墙/内墙F≈1800，填充F≈2400，空驶F≈9000。 3. 第2层起恢复其他层速度，模型路径不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`e15272b8`，SHADOW）；d5fc2fa 上另有 1 次（SHADOW，不是最终引擎；明细见 family-regression.md） |
| #271 `reczz28b6mRAyekU` 其他层速度-特征速度组合 | 实用模型 > 小船 | outer_wall_speed（外墙速度）=100；inner_wall_speed（内墙速度）=150；sparse_infill_speed（稀疏填充速度）=200；top_surface_speed（顶面速度）=120；small_perimeter_threshold（小轮廓阈值速度）=10mm；small_perimeter_speed（小轮廓速度）=50 | 2. 外墙/内墙/填充/顶面F分别≈6000/9000/12000/7200。 3. 周长<10mm的loop使用50mm/s，其他特征F不变。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`7d2fabac`，SHADOW） |
| #272 `reczz28b6mRB1ZL4` 悬垂速度-分档与桥接组合 | 实用模型 > 欧特克FDM测试 | enable_overhang_speed（悬垂降速速度）=1；overhang_1_4_speed（悬垂 10%–25% 速度）=40；overhang_2_4_speed（悬垂 25%–50% 速度）=30；overhang_3_4_speed（悬垂 50%–75% 速度）=20；overhang_4_4_speed（悬垂 75%–100% 速度）=10；overhang_totally_speed（100%速度）=5；bridge_speed（桥接速度）=30 | 2. 各悬垂档F≈2400/1800/1200/600/300。 3. 桥接F≈1800，非悬垂区F不变。 | 补覆盖 1 次（fa706g3，`c087687c`，SHADOW）；最终引擎 2a17376 回归 1 次（fa706g3，`ed9d6ba3`，SHADOW） |
| #273 `reczz28b6mRB1Pm2` 空驶速度-全局映射 | 标准模型 > 立方体，复制为2个对象 | travel_speed（空驶速度）=300 | 2. 所有非首层空驶F≈18000。 3. 挤出路径F和刀路不受影响。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`a88d1138`，SHADOW） |
| #274 `reczz28b6mRAzthX` 加速度-特征组合 | 实用模型 > 小船 | default_acceleration（普通打印加速度）=3000；initial_layer_acceleration（首层加速度）=500；outer_wall_acceleration（外墙加速度）=2000；inner_wall_acceleration（内墙加速度）=4000；sparse_infill_acceleration（稀疏填充加速度）=5000；travel_acceleration（空驶加速度）=8000 | 2. 首层、外墙、内墙、填充、空驶加速度分别匹配设置。 3. 超机器上限时被裁剪，非目标特征不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`5f69c567`，SHADOW） |
| #275 `reczz28b6mRAytbr` 抖动-特征组合 | 标准模型 > 圆柱体 | default_jerk（默认抖动）=8；initial_layer_jerk（首层抖动）=4；outer_wall_jerk（外墙抖动）=5；inner_wall_jerk（内墙抖动）=6；infill_jerk（填充抖动）=9；travel_jerk（空驶抖动）=10 | 2. 首层、外墙、内墙、填充、空驶Jerk分别匹配设置。 3. 拐角速度受限制，直线路径不变。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`dd7ab376`，SHADOW） |
| #277 `reczz28b6mRAydro` 支撑-开启与基础结构组合 | 实用模型 > 欧特克FDM测试 | enable_support（开启支撑）=1；support_threshold_angle（支撑阈值角度）=45；support_type（支撑类型）=normal(auto)（普通自动）；support_on_build_plate_only（仅在打印板生成）=0；support_critical_regions_only（仅支撑关键区域）=0 | 2. 超过45°的悬垂生成支撑，结构为normal(auto)（普通自动）。 3. 允许支撑从模型表面起枝，完整覆盖关键和非关键悬垂。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`cab7609d`，SHADOW） |
| #278 `reczz28b6mRAzKa2` 筏层-结构/间距/扩展组合 | 实用模型 > 小船 | raft_layers（筏层数）=3；raft_contact_distance（筏层Z间距）=0.20mm；raft_expansion（筏层扩展）=5mm；raft_first_layer_density（筏层首层密度）=100%；raft_first_layer_expansion（筏层首层扩展）=5mm | 2. 模型下方生成3层筏层，接触Z间隙≈0.20mm。 3. 筏层XY外扩≈5mm，首层覆盖率100%且不超打印区域。 | 最终引擎 2a17376 回归 1 次（fa706g3，`f8267f3b`，SHADOW） |
| #279 `reczz28b6mRAyV6h` 支撑耗材-主体与界面组合 | 实用模型 > 欧特克FDM测试，并设置2种耗材 | support_filament（支撑主体耗材）=1；support_interface_filament（支撑界面耗材）=0 | 2. 支撑主体使用工具1，接触面使用工具0。 3. 模型本体工具号不变，切换工具时擦料塔和回抽完整。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`98dc9db8`，SHADOW） |
| #280 `reczz28b6mRAz8Gm` 支撑熨烫-开关/流量/间距组合 | 实用模型 > 欧特克FDM测试 | support_ironing（支撑熨烫）=1；support_ironing_flow（支撑熨烫流量）=10%；support_ironing_spacing（支撑熨烫间距）=0.15mm；support_ironing_pattern（支撑熨烫图案）=rectilinear（直线） | 2. 仅支撑接触面生成rectilinear（直线）熨烫路径。 3. 熨烫E按10%流量生效，线距≈0.15mm，模型表面不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`4000ec43`，SHADOW） |
| #281 `reczz28b6mRAz1dW` 支撑高级-距离与界面组合 | 实用模型 > 欧特克FDM测试 | support_top_z_distance（顶部Z距离）=0.20mm；support_bottom_z_distance（底部Z距离）=0.20mm；support_object_xy_distance（支撑/模型xy间距）=0.50mm；support_interface_top_layers（顶部接触面层数）=3；support_interface_spacing（顶部接触面线距）=0mm；support_interface_pattern（支撑面图案）=rectilinear（直线） | 2. 支撑顶/底Z间隙和模型XY间距符合设置。 3. 3层实心接触面生成，线距≈0，支撑不穿插模型。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`50e7445e`，SHADOW） |
| #282 `reczz28b6mRB0dhl` 支撑高级-树状支撑组合 | 实用模型 > 斯坦福兔子 | support_type（支撑类型）=tree(auto)（树状自动）；tree_support_branch_angle（树状支撑分支角度）=40；tree_support_branch_diameter（树状支撑分支直径）=2mm；tree_support_adaptive_layer_height（自适应层高）=1；tree_support_wall_count（支撑外墙层数）=1；max_bridge_length（最大桥接长度）=30mm | 2. 树状支撑分支角度和直径符合设置，分支连续。 3. 支撑层高自适应，超过30mm跨度触发支撑。 | 最终引擎 2a17376 回归 1 次（fa706g3，`b543390b`，SHADOW） |
| #283 `reczz28b6mRAy1At` 擦拭塔-结构/清理/附着组合 | 实用模型 > 小船，并设置2种颜色/耗材 | enable_prime_tower（擦料塔开启）=1；prime_tower_width（擦料塔宽度）=30mm；prime_volume（清理量）=40mm³；prime_tower_brim_width（擦料塔Brim宽度）=5mm；wipe_tower_wall_type（墙体类型）=rib（加强筋）；wipe_tower_no_sparse_layers（擦料塔无稀疏层）=1；wipe_tower_cone_angle（稳定锥体顶角）=15°；wipe_tower_filament（擦料塔耗材）=0 | 2. 多工具换料时生成30mm宽擦料塔，清理量≈40mm³。 3. 塔体为rib（加强筋）墙、无稀疏层、15°锥角并带5mm Brim，模型不碰撞。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`51f2c5a1`，SHADOW） |
| #284 `reczz28b6mRAzFuo` 特征用耗材-塔与支撑映射组合 | 实用模型 > 欧特克FDM测试，并设置2种耗材 | wipe_tower_filament（擦料塔耗材）=0；support_filament（支撑主体耗材）=1；support_interface_filament（支撑界面耗材）=0 | 2. 擦料塔使用工具0，支撑主体工具1，接触面工具0。 3. 模型本体工具号不变，换料顺序和擦料塔路径完整。 | 最终引擎 2a17376 回归 1 次（fa706g3，`85f43119`，SHADOW） |
| #285 `reczz28b6mRB1fwT` Ooze预防-待机与预热组合 | 实用模型 > Orca拉丝地狱，并设置2种耗材 | ooze_prevention（Ooze预防开启）=1；standby_temperature_delta（待机温度差）=-100℃；preheat_steps（预热步骤）=2；preheat_time（预热时间）=15s | 2. 非活动工具进入待机温度，活动工具温度不变。 3. 换料前按2步、每步15s预热，换回后恢复打印温度。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`c27e3d11`，SHADOW） |
| #286 `reczz28b6mRB035T` 换料冲刷-去向与体积组合 | 实用模型 > 小船，并设置2种颜色/耗材 | flush_into_infill（冲刷到对象的填充）=1；flush_into_objects（冲刷到这个对象）=1；flush_into_support（冲刷到对象的支撑）=1；prime_volume（清理量）=40mm³ | 2. 冲刷废料按目标导入填充、对象和支撑。 3. 擦料塔废料减少，冲刷体积≈40mm³，模型外形不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`27bb889e`，SHADOW） |
| #287 `reczz28b6mRAzl7P` 材料高级-界面外壳与工具组合 | 实用模型 > 欧特克FDM测试，并设置2种耗材 | interface_shells（接触面外壳层数）=2；support_filament（支撑主体耗材）=1；support_interface_filament（支撑界面耗材）=0 | 2. 支撑接触面生成2层界面外壳。 3. 主体工具1和界面工具0映射正确，模型外壳不变。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`55065a00`，SHADOW） |
| #290 `reczz28b6mRAyRCt` 裙边-圈数高度距离与风挡组合 | 实用模型 > 小船 | skirt_loops（Skirt圈数）=3；skirt_height（Skirt高度）=2；skirt_distance（Skirt距离）=5mm；draft_shield（风挡）=enabled（开启） | 2. 生成3圈、2层、距模型5mm的裙边。 3. 风挡包围全部模型，模型本体路径和外形不变。 | 最终引擎 2a17376 回归 1 次（fa706g3，`a8f21d45`，SHADOW） |
| #291 `reczz28b6mRAyNfH` Brim-宽度间隙与类型组合 | 实用模型 > 小船 | brim_width（Brim宽度）=5mm；brim_object_gap（Brim与模型的间隙）=0.2mm；brim_type（Brim类型）=outer_only（仅外墙） | 2. 仅外墙生成5mm Brim，与模型间隙≈0.2mm。 3. 内孔无Brim，Brim连续附着且不进入模型内部。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`f6dc29a8`，SHADOW） |
| #292 `reczz28b6mRB1mQt` 特殊模式-逐件打印与碰撞 | 标准模型 > 立方体，复制为2个对象并调整间距 | print_sequence（打印顺序）=by object（逐件打印）；extruder_clearance_radius（挤出机避让半径）=20mm；extruder_clearance_height_to_rod（到横杆的避让高度）=30mm | 2. 间距充足时按对象逐个打印，工具头避让生效。 3. 间距不足时报告碰撞风险并阻止输出G-code。 | 最终引擎 2a17376 回归 1 次（fa706g3，`9ad1b7e2`，SHADOW） |
| #293 `reczz28b6mRB19md` 特殊模式-螺旋花瓶单墙 | 标准模型 > 圆柱体 | spiral_mode（旋转花瓶）=1；单墙模型；seam_position（接缝位置）=nearest（最近） | 2. 单墙模型生成连续上升Z路径，无常规层接缝。 3. 多墙或多对象模型明确限制，不输出不安全螺旋G-code。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`e2dc078f`，SHADOW） |
| #294 `reczz28b6mRAzCq8` 特殊模式-延时与切片模式组合 | 实用模型 > 小船 | timelapse_type（延时摄影模式）=2；slicing_mode（切片模式）=regular（常规） | 2. G-code插入对应延时停靠/拍照指令。 3. regular（常规）切片路径保持不变，层数不减少。 | 最终引擎 2a17376 回归 2 次（fa706g3、客机 win11-test，`1a4c0845`、`9db255d4`，NON_GREEN） |
| #295 `reczz28b6mRAyPQV` 绒毛表面-范围/点距/厚度组合 | 标准模型 > 球 | fuzzy_skin（绒毛表面）=external（仅外表面）；fuzzy_skin_point_distance（绒毛表面点间距）=0.6mm；fuzzy_skin_thickness（绒毛表面厚度）=0.3mm | 2. 仅外表面生成随机扰动，点距≈0.6mm、幅度≈0.3mm。 3. 内部填充和非目标表面路径不变。 | 补覆盖 1 次（客机 win11-test，`344785de`，SHADOW）；最终引擎 2a17376 回归 1 次（客机 win11-test，`c953a014`，SHADOW） |
| #296 `reczz28b6mRAyaVq` G-code输出-注释/行号/标签/文件名组合 | 标准模型 > 立方体，复制为2个对象 | gcode_comments（注释G-code）=1；gcode_add_line_number（标注行号）=1；gcode_label_objects（标注模型）=1；filename_format（文件名格式）={input_filename}_{plate_name}.gcode（输入文件名_盘名.gcode） | 2. G-code包含注释、行号和对象标签，文件名匹配格式。 3. 非注释运动指令和刀路与默认基准完全一致。 | 最终引擎 2a17376 回归 1 次（fa706g3，`2c31895f`，SHADOW） |
| #297 `reczz28b6mRAyshq` G-code输出-排除对象与填充回抽组合 | 标准模型 > 立方体，复制为2个对象 | exclude_object（排除对象）=1；reduce_infill_retraction（减小填充回抽）=1 | 2. 被排除对象无打印路径，保留对象路径完整。 3. 填充区回抽次数减少，外墙和支撑回抽不变。 | 最终引擎 2a17376 回归 1 次（客机 win11-test，`2c581bd4`，SHADOW） |

最终引擎回归的队列跑的是不带后缀的 `uia_param_<key>` 场景，它打开的是立方体工程（`harness/native_matrix.py`：带 `_std02`、`_shapes`、`_fdmt` 后缀的孪生场景才打开别的工程），不是各行飞书前置条件里的模型和预设；例如 #256 的前置是圆柱体，#264 立方体工程回读的层高是 0.4 mm、线宽 0.82 mm。按各行自己的模型跑的结果是 11‑24 那一轮，在对照表「运行记录与原判」一列里。客机的 6 条补覆盖都跑在多形状夹具上，fa706g3 的 3 条跑在立方体工程上。

## 各动作耗时

动作秒是 `native_worker.json` 的脚本动作阶段。客机的整轮是 `summary.json` 的宿主墙钟（含收割）；fa706g3 不写宿主摘要，整轮用 `process.json` 的机内进程秒。两边各取均值，差为前者减后者，只在同机、同构建线、同初态之间算。逐阶段、逐 run 的表在[stage-timings.md](evidence/ninehour-2026-11-25/stage-timings.md)，下表的数与它一致。

| 场景 | 机器 | 整轮：基线 → 候选，节省 | 动作：基线 → 候选，节省 |
|---|---|---|---|
| #276 Quality | 客机 | 222.828 / 217.984 → 209.469 / 201.391，省 14.976 | 76.422 / 76.109 → 60.734 / 61.000，省 15.398 |
| #276 Quality | fa706g3 | 183.676 → 168.986 / 168.829，省 14.768 | 73.859 → 58.938 / 58.875，省 14.952 |
| #276 Strength（单列） | 客机 | 223.329 → 201.234 / 201.703，省 21.860 | 76.547 → 61.172 / 61.281，省 15.320 |
| #264 立方体 | 客机 | 258.640 → K1 232.953 / 232.922 → K2 213.344 / 213.328；省 25.703、19.602 | 122.828 → K1 102.531 / 102.328 → K2 82.094 / 82.109；省 20.398、20.328 |
| #264 立方体 | fa706g3 | 231.998 / 222.329 → K1 202.464 / 202.356 → K2 182.280 / 182.316；省 24.754、20.112 | 123.000 / 122.156 → K1 102.266 / 102.235 → K2 82.110 / 82.156；省 20.328、20.117 |
| #264 FDM 测试模型 | 客机 | 258.203 → K1 237.578 / 237.172 → K2 216.937 / 218.547；省 20.828、19.633 | 122.390 → K1 102.281 / 102.781 → K2 82.063 / 82.171；省 19.859、20.414 |
| #264 FDM 测试模型 | fa706g3 | 224.345（计时版）→ K1 204.379 / 204.325 → K2 184.261 / 184.255；省 19.993、20.094 | 122.454（计时版）→ K1 102.484 / 102.500 → K2 82.375 / 82.422；省 19.962、20.093 |

#264 两步合计，依次是整轮、动作：立方体客机省 45.304、40.727，fa706g3 省 44.866、40.445；FDM 测试模型客机省 40.461、40.273。#276 的节省是两列候选的均值对两列基线的均值；Strength 只有一列基线，单列不与 Quality 比。

构建：#276 是基线 `636a733` → 候选 `eae2376`（输入后的就绪等待）；#264 是基线 `636a733` → K1 `3ef1f94`（就绪等待）→ K2 `e3bfdfe`（滚轮一次到位），客机的 K2 在合并提交 `d5fc2fa` 上跑，引擎相同。fa706g3 的 FDM 测试模型没有 `636a733` 的基线，它的参照是计时版 `008d97b`。

最终引擎 `2a17376` 上的确认（`final2-*`，对同一组的基线均值）：客机 #276 Quality 宿主整轮 201.453，省 18.953；动作 61.031，省 15.235；fa706g3 #276 Quality 机内进程 168.760，省 14.916；动作 58.906，省 14.953；客机 #276 Strength 宿主整轮 202.078，省 21.251；动作 61.187，省 15.360（单列）；客机 #264 立方体 宿主整轮 214.594，省 44.046；动作 82.094，省 40.734；fa706g3 #264 立方体 机内进程 182.314，省 44.850；动作 82.125，省 40.453。候选的节省在修正之后都还在。FDM 测试模型没有在 `2a17376` 上重跑。

| 场景 | 机器 | 变了的阶段：基线 → K1 → K2（秒） |
|---|---|---|
| #276 Quality | 客机 | 三个字段的 `edit_readback`：6.090 / 6.099 → 1.083 / 1.117；6.083 / 6.071 → 1.089 / 1.088；6.163 / 6.138 → 1.149 / 1.154 |
| #276 Quality | fa706g3 | 6.016 → 1.043 / 1.042；6.045 → 1.043 / 1.044；6.065 → 1.084 / 1.091 |
| #276 Strength | 客机 | 6.106 → 1.108 / 1.114；6.108 → 1.096 / 1.099；6.125 → 1.180 / 1.176 |
| #264 立方体 | 客机 | `checkbox.Detect overhang` 26.372 → 26.317 / 26.229 → 7.937 / 7.944；`checkbox.Slow down` 8.197 → 8.162 / 8.234 → 6.093 / 6.111；四个 `edit_readback` 6.116–6.135 → 1.130–1.211 → 1.139–1.190 |
| #264 立方体 | fa706g3 | 26.993 → 26.991 / 26.979 → 9.021 / 9.027；8.034 → 8.027 / 8.027 → 5.869 / 5.872；6.058–6.068 → 1.078–1.100 → 1.082–1.115 |
| #264 FDM 测试模型 | 客机 | 26.362 → 26.332 / 26.333 → 7.961 / 7.955；8.204 → 8.205 / 8.299 → 6.095 / 6.058；6.087–6.143 → 1.086–1.165 → 1.093–1.192 |
| #264 FDM 测试模型 | fa706g3 | 26.986 → 26.985 / 26.993 → 9.022 / 9.027；8.028 → 8.034 / 8.027 → 5.869 / 5.881；6.041–6.065 → 1.044–1.097 → 1.041–1.103 |

- 节省全部来自两处。#276 的 `edit_readback` 原来每个字段约 6 秒，几乎全是输入后的固定 `pause(6)`，候选换成有上限的就绪检查后是 1.0–1.2 秒。#264 的 K1 是同一处，四个输入框各省约 5 秒；K2 是长页定位：`Detect overhang` 的标题在页面顶部下 26–27 格，原来一次滚一格、每格带 0.75 秒停顿，K2 按标题距离一次滚够（提交 `e3bfdfe` 的说明）。
- 没变的：两次切页各 9.545–9.810 秒，保存 7.547–8.093 秒，#264 第一档的定位在 fa706g3 是 3.43–3.46 秒、在客机是 5.12–5.19 秒，各构建之间没有差别。切页的固定停顿今晚没有动（`findings-sheet.md`）。
- 计时版只加了阶段行，没有改动作：#264 立方体的动作秒客机 122.828 → 122.672，fa706g3 123.000 / 122.156 → 122.187；FDM 测试模型客机 122.390 → 122.281。fa706g3 的计时版 `76b85931` 台账里没有记提交号。
- 候选的 run 没有失败：两行所有候选的 `verified_pass` 为真，没有 `ok=0` 的阶段，清理都确认。`d5fc2fa` 上的复核（`9bc10b3f`、`db27fe2c`、`9d6d1eb3`、`b7778cd5`）不是最终引擎，只留作记录。
- 导出件和保存件。立方体上，候选与基线的导出件去掉时间戳、缩略图和对象编号后逐行相同，保存工程设置 586 键全同。`2a17376` 上的 4 次复核（#276 Quality 两次、#264 立方体两次）也与基线逐行相同；Strength 的 `29e6b834` 与 Quality 的导出件相同，对不上的是 Strength 基线 `5359abca` 自己，见下一条。FDM 测试模型上同一构建的两次运行行序就不同，所以另按「类型段 × 层 × 进给」的挤出长度和「类型段 × 层」的耗料求和比较：fa706g3 的 4 次候选都与计时版相同；客机 K1 的 `2910969d` 与基线相同，K1 的 `e15b8b93` 和两次 K2（`9ff32b28`、`b97452a8`）内部实心填充少 2023 段（挤出移动 161235 对 163258 段，117 个「类型段 × 层」格的耗料不同），保存的设置相同。
- 这不是构建或机器造成的。当晚同一模型的 run 放在一起看：#276 立方体 16 次里 15 次相同，不同的是 636a733 的 `5359abca`（挤出移动 6093 对 6123 段）；#264 立方体 15 次里 14 次相同，不同的是 `83a295d9`（挤出移动 1896 对 1908 段）；FDM 测试模型 11 次里 8 次相同，不同的是 `e15b8b93`（挤出移动 161235 对 163258 段）、`9ff32b28`（挤出移动 161235 对 163258 段）、`b97452a8`（挤出移动 161235 对 163258 段）。不同的几次都只差在内部实心填充，保存的设置都相同。原因今晚没有查。在这几个模型上拿一次导出件当「基线 G-code」逐行比，要先把它算进去（`stage-timings.md`「切片复现」）。

失败轮：

| 运行 | 场景 | 到了哪一步 | 失败签名 | 评级 |
|---|---|---|---|---|
| #265 `eefe9d78` | `compare_265_quality`，原生模型 | 工具调用 20 次（Snapshot 10、Click 7、Wait 2、Screenshot 1），宿主 672.703 秒 | `RuntimeError:zcode_actor_failed:agent_deadline` | NON_GREEN |
| #276 `2053992c` | `compare_276_quality`，原生模型 | 工具调用 41 次（Snapshot 20、Click 16、Shortcut 2、Type 2、Screenshot 1），宿主 437.125 秒 | `RuntimeError:zcode_actor_failed:native_action_budget` | NON_GREEN |
| #268 `62a3cd01`（fa706g3，d5fc2fa） | `uia_param_infill_combo` 回归 | 动作 34.578 秒后中止 | `ProtocolError:param_combo_readback:Gyroid:Grid`：点选 Gyroid 后回读到 Grid | NON_GREEN |
| #294 `1a4c0845`（fa706g3）、`9db255d4`（客机），2a17376 | `uia_param_timelapse` 回归 | 脚本走完编辑和保存，动作 121.093 / 122.453 秒 | business 和 path 都是 `pilot_target_setting_mismatch` | NON_GREEN |

- 两次原生模型运行都是 ZCode 的 actor（供应商 Snapmaker，模型 glm-5.4），在 `eae2376`、Quality 初态、只给目标不给步骤的模式下跑；各有一次工具调用停在 pending，清理都确认。没有经独立验证的 GUI 结果，所以没有和 Script 配对。模型请求数（11 次和 42 次）只见于 `findings-sheet.md`。签名与[11‑24 的对照](glm54-maintenance-265-276.md)里的 `agent_deadline`、`native_action_budget` 相同。
- #268 是一次失败加重试。失败的那次和最终引擎上通过的那次（`72f7f6de`），两份 `native_worker.log` 到点击为止逐行相同（第 1–27 行只差 run 号、pid、句柄）：都是把弹出的列表停靠 3 格，在 (323,740) 点 Gyroid；点击之后一份回读到 Grid，一份回读到 Gyroid。总控据此判断点击时列表的滚动位置不同，点到了 Grid 上；日志本身不记滚动位置，原因没有再查。失败点在 `harness/param_combo_row.py` 的 `pick_combo_at_label`，是下拉列表点选后的回读，不在滚轮改动所在的 `scroll_group_into_view`。之后两台机器各重试 4 次，共 8 次，都是 SHADOW；最终引擎 `2a17376` 上 fa706g3 的回归 `72f7f6de` 也通过。
- #294 两次都是脚本走完编辑和保存之后，业务和路径两项检查都报 `pilot_target_setting_mismatch`。它是 11‑24 就开着的行（当时记为机型不适用：Timelapse 行只在 BBL 机型上有，见 11‑24 的对照表），不是这次改动造成的回归。

Mac 线没有走通。壁环数 2→3 的首次运行是 NON_GREEN（run `5bb1a766`，只见于 `findings-sheet.md`，宿主上没有收割件），随后的 8 次探针（01:42–02:21）都停在这个阻塞上。阻塞是前台账号 coil 的控制台会话自 2026‑11‑24 19:25:27 起锁屏：测试会话仍受信，窗口服务器也列得出 179 个窗口，但这个会话里每个应用（测试 Orca、Finder、Safari、iTerm2、UURemote）的 `AXWindows`、`AXMainWindow` 都返回一个标题为应用名、自指的 `AXApplication` 节点，工作器等不到带工程标题的窗口，报 `Named project window did not open`。截图里测试实例在渲染，工程已装进窗口，所以不是应用的问题。恢复条件是 coil 的控制台会话由它的用户解锁；证据和两次不算数的探针见 [mac/README.md](evidence/ninehour-2026-11-25/mac/README.md)。

## 判据复核与反例

**今晚没有改任何判据。** 任务要求保持原判据，分别写出保存了什么、切片证明了什么、哪项尚未验证。`636a733..2a17376` 之间 `harness/param_comparison.py`、`harness/native_pilots.py`、`harness/native_save_session.py` 没有改动，`harness/pilot_param_264_overhang_speeds.py` 只改了 7 行注释；合并的提交是计时、等待方式、滚轮、注释、收据工具和那一处停滞路径的修正。

反例在副本上做（[negative-controls.json](evidence/ninehour-2026-11-25/negative-controls.json)，319 条）。该拒的都拒了：差一档、留在默认值或没设、目标对但带一个无关设置、把输入夹具当结果、脏列表里带无关键，两行都是。该拒不拒的有 41 条，都是判据的洞：

| 对象 | 反例 | 业务判据（`checks.business` 背后的调用） | 整目录验证器 |
|---|---|---|---|
| #264 FDM 测试模型 `b697f7c2` | 目标值正确，G-code 换成同夹具的默认参数导出件、另一个模型的导出件、截到 2000 字节、配置块写回默认值、默认移动接在改过的配置块后面（反例 6、6b、6c、6d、6e） | 5 条都接受 | 5 条都接受 |
| #264 立方体 `7484bd43`、`8e207463`、`19d61032` | 同上 | 「另一个模型」被拒（`gcode_layer_height_mismatch`），其余 4 条接受 | 同左；只在客机的 `7484bd43` 上跑了 |
| #276 `ec032d7c`、`eebdf238`、`5359abca` | 默认移动接在改过的配置块后面（反例 6e） | 运行内判据接受（`pair_status: baseline_required`）；宿主配对判据拒绝（`comparison_outer_wall_volumetric_cap`） | 接受 |
| 以上 7 次 | 改 manifest.json 的 case_id、executor、contract_sha256、metadata（反例 m1） | 接受 | 接受（整目录验证器只在 5 次客机运行上跑了，5 次都接受） |

- #264 的判据不看本行导出件的 G-code，也不把导出件的配置块和保存件比。`checks.business` 的通过只靠保存下来的设置：`b697f7c2` 的 `result.json` 里它是通过，同一份记录里带着 `schedule_error: gcode_fixture_height_mismatch`。所以这一行的「切片成功并产出 G-code」和「各悬垂区间的 F」，判据现在管不到。
- #276 只有宿主侧的配对判据会看 G-code，而它永远不会给 PASS：`harness/param_comparison.py:208` 要求 `x_limit_effect` 等于 `observed`，第 132 行返回的却是常量 `not_exercised_by_flow_limited_outer_walls`。
- 整目录验证器不读 manifest.json 的 case_id、executor、contract_sha256 和 metadata；它拒得掉 `started_at_ns` 被挪后一小时和 `scope.json` 里的场景改名。

飞书预期与实测不一致的地方：

| 行 | 预期（原文） | 实测 | 来源 |
|---|---|---|---|
| #276 | 外墙速度先受体积流量限制到约178mm/s | 外墙峰值 202.956 mm/s。178.571 是按矩形截面 15÷(0.20×0.42) 算的；切片用的截面积是 0.073908 mm²（已含流量比 0.98） | `facts.json` 的 `arithmetic` |
| #276 | 同时不超过机器X轴500mm/s，超限部分降速且路径不变 | 外墙被流量限制在约 203 mm/s，没有一段接近 500 mm/s，X 上限没有介入 | `facts.json` 的 `expectation_2`、`expectation_3` |
| #264 | 步骤 1 的 overhang_totally_speed（100%速度）=5 | 2.4.0 没有这个参数，这一行只有四个输入框，第五个和这个键是 2.4.1 才有的（`b070bcfaff`，2026‑11‑05）。今晚没有把它映射到桥接速度，因为预期 3 要求桥接区 F 不变（`findings-sheet.md`） | 提交 `6e4d7cf` 的说明；`facts.json` 的 `expectation_1` |
| #264 | 各悬垂区间的F分别≈2400/1800/1200/600/300 | Overhang wall 段（146 段、452 条移动）只有 F1980 和 F3000，和默认切片相同；最低一档走的是桥接速度（`slowdown_for_curled_perimeters` 关着） | `facts.json` 的 `row264` |
| #264 | 非悬垂区和桥接区F不变 | 桥接段共 7898.1 mm，F3000 从 7897.7 mm 降到 7466.2 mm；258 个比较层里 151 层的非墙进给变快 | `facts.json` 的 `expectation_3` |
| #264、#276 | 路径不变 | 保存的设置相同时，两次切片会在内部实心填充上不同（第 3 节） | `stage-timings.md`「切片复现」 |

## 合并与回归

合并的提交，都在 `636a733` 之上（提交时间取自仓库）：

| 提交 | 时间 | 一句话 |
|---|---|---|
| `49439ab` | 02:11 | 给 #264 立方体场景加阶段行（切页、复选框、字段、保存）；没有度量时每个调用和停顿照旧 |
| `eae2376` | 02:34 | #276 输入后的固定 `pause(6)` 换成有上限的就绪检查：字段显示目标值、控件树连续三次读数相同才算完，上限仍是 6 秒 |
| `008d97b` | 02:53 | #264 的 FDM 测试模型孪生场景也加阶段行；只加计时 |
| `3ef1f94` | 03:03 | 同一个就绪检查给到 #264 的两个场景；其它 634 个场景交给的操作调用不变 |
| `6e4d7cf` | 03:08 | 把 #264 注释里的「五个输入框」改成这个构建实际有的四个；只改注释 |
| `e3bfdfe` | 03:34 | 长页定位由一次一格的滚轮改成按标题距离一次滚够，不超过切页复位用的 40 格；只改 `scroll_group_into_view` |
| `115b8a9`、`fff5df5` | 02:17、02:44 | 收据工具 `tools/ninehour_receipts.py` 及其单测；能读宿主离线补做的配对 |
| `d5fc2fa` | 03:42 | 把收据工具并入引擎分支；引擎与 `e3bfdfe` 相同 |
| `2a17376` | 05:04 | 要合并的引擎：`d5fc2fa` 加 `5b38c80` 的拣选，对应独立评审 `636a733..d5fc2fa` 提出的那一处应当修的问题（评审没有阻塞项；评审意见本身不在证据包里）。它改的是停滞路径：页面停住之后，下一次滚轮只发一格。原先按滚轮之后才计数的 `stuck` 判断，停住的页面会把整段滚轮再发一遍（27、27、1…），如果吞掉滚轮的是一个一格一步的控件，它会被多步。现在按滚轮之前的状态判断（27、1、1…）。只改 `scroll_group_into_view` 的循环体和它的单测；普通路径不走这段，不受影响 |

提交说明里的「未对 GUI 实跑」是写提交时的状态，实跑就是上面这些 run。

**闸门。** `tools/pre_merge.py` 在 `d5fc2fa` 和 `2a17376` 上都是 PASS：引擎套件 175 项检查 0 失败（229.7 秒、230.3 秒），单元测试 1742 通过、3 跳过、4 个子测试通过，操作表对图集 PASS，红证 PASS（`pre_merge_d5fc2fa.log`、`pre_merge_2a17376.log`；日志本身不记提交号，对应关系来自文件名）。`2a17376` 的日志末行另提示磁盘只剩 16.1 GB，低于 20 GB。

**最终引擎回归。** 42 行在 `2a17376` 上两台机器分跑，每行在分到的那台机器上跑一次（客机 21 行、fa706g3 21 行），客机另给 #294 加跑了一次：41 行 SHADOW（客机 21 行全部，fa706g3 20 行），NON_GREEN 1 行（#294：fa706g3 `1a4c0845`、客机 `9db255d4`）。回归只回答引擎改动有没有破坏该行已有的写入和导出，不逐项核对飞书预期；名单和逐行结果见 [family-regression.md](evidence/ninehour-2026-11-25/family-regression.md)。在 `d5fc2fa` 上先跑过的那一部分不是最终引擎：客机 4 行、fa706g3 7 行 SHADOW，#268 失败一次（第 3 节），已被最终引擎上的结果取代。

第 1 节到这里的数字是第一次推送（`62cddee`）时的状态。第一次推送之后两台机器又补跑到 08:50 停派（标签 `guest-twins`、`guest-twins-b`、`fa-shapes`、`second-sample`，以及 fa706g3 那一半在客机上的交叉运行），结果见文末「追加覆盖」；`ledger.jsonl` 和 `receipts/` 已随之刷新，其余各表没有重新生成。

本轮没有回写飞书：没有一行是 GREEN 或已覆盖。

复跑入口，测试同事可以直接用：

| 线 | 入口 | 条件 |
|---|---|---|
| 客机 | 在已同步到该提交的分支型 checkout 里，先 `runner\guest_v3_bundle_sync.ps1 -Head <sha>`，再 `python -B tools/native_save_demo.py --actor script --scenario <name> --run-id <新的 32 位十六进制>` | checkout 的 `artifacts\windows_mcp_harvest` 里要有两份固定的对照基线 `e9aa6f88…`（#276）和 `0cccce4a…`（#265；它也是 #264 FDM 测试模型的默认切片基线）。配对完成但业务没有全过时退出码是 1，看 `summary.json` 的 `comparison` |
| fa706g3 | `fa_run.py <name>`：宿主脚本把作业交给计划任务 `glm_line`，在交互会话里带 `ORCA_BB_ALLOW_TESTBOX=1` 跑 | 结果只能记 SHADOW；同一个 HEAD 在跑批期间不要换。今晚用的脚本是 `C:\coil\vm_setup\ninehour_1125\fa_run.py`，不在仓库里 |
| Mac | `runner/macos_project_copy.py coilwin@localhost --identity ~/.ssh/orca_bb_local --known-hosts ~/.ssh/orca_bb_known_hosts --candidate <label> --goal walls` | 只在 coil 的控制台会话解锁之后跑 |
| 收据 | `python -B tools/ninehour_receipts.py <harvest root> --runs <ids> --ledger <ledger> --json <dir>` | 只读收割件 |

人工分钟未测。台账能算出的机器占用（到 06:57:35）：客机第一条 01:34:09 开始、最后一条 06:57:35 结束，75 个 run 的宿主编排秒合计 15984 秒（266.4 分钟），占这段时间的 82.4%；fa706g3 第一条 01:34:43 开始、最后一条 06:57:05 结束，60 个 run 从投递到收割合计 13802 秒（230.0 分钟），占 71.3%。按机内 `process.json` 算，客机合计 13984 秒，fa706g3 9976 秒；脚本动作分别 5168 秒和 4059 秒。台账只有每个 run 的启动和结束时刻，没有派工时刻，所以算不出排队时间，只能算相邻两个 run 之间的空档：客机合计 3422 秒（最长 1517 秒，`0b51fb83` 之后），fa706g3 合计 5584 秒（最长 2004 秒，`8e207463` 之后）。宿主编排里启动应用和收割各占多少没有分开记；fa706g3 的合计含 10 秒一次的轮询；Mac 的 `ledger.txt` 只有起始时刻，没有时长。

## 追加覆盖（第一次推送之后）

第一次推送（`62cddee`）之后，两台机器继续补覆盖到 08:50 停派，最后一条 run 约 08:54 结束。引擎没有变化：`62cddee` 与 `2a17376` 的引擎文件相同。这些都是补覆盖或第二样本，单独记账，不计闭环，也不改变 42 行回归 41 行 SHADOW 的结论。

| 追加项 | 机器、提交 | 结果 |
|---|---|---|
| 8 行各自飞书模型的孪生场景（此前只有 fa706g3 证据）：#258 `arc_resolution_tol`、#260 `wall_generator_text`、#263 `bridge_fdmt`、#277 `support_basic_fdmt`、#280 `support_ironing_fdmt`、#281 `support_interface_fdmt`、#292 `by_object_cubesfar`、#293 `spiral_vase_cyl` | 客机，`2a17376`，标签 `guest-twins` | 8 次，8 次 SHADOW |
| 另 11 行各自飞书模型的孪生场景（11‑24 在 fa706g3 上的结论是「有出入」或「看不到」）：#256 `seam_wipe_cyl`、#257 `precision_comp_tol`、#272 `overhang_bridge_fdmt`、#275 `jerk_cyl`、#279 `support_filament_fdmt2`、#282 `tree_support_bunny`、#283 `prime_tower_boat2`、#284 `filament_features_fdmt2`、#286 `flush_options_boat2`、#287 `material_advanced_fdmt2`、#285 `ooze_prevention_hell` | 客机，`62cddee`，标签 `guest-twins-b` | 11 次，11 次 SHADOW |
| fa706g3 那一半 21 行在客机上的交叉运行 | 客机，`62cddee`，标签 `regress-final` | 18 次：17 次 SHADOW，#294 `uia_param_timelapse` NON_GREEN（`ed62daca`）；另 3 行未跑 |
| 客机那一半在 fa706g3 上的第二样本 | fa706g3，`2a17376`，标签 `second-sample` | 15 次，15 次 SHADOW；另 6 行未跑 |
| 22 条多形状夹具孪生场景（连同客机在 `49439ab` 上先跑的 6 条，11‑24 备用队列里未跑的 27 条副本各有一次运行） | fa706g3，`2a17376`，标签 `fa-shapes` | 22 次：19 次 SHADOW，3 次 NON_GREEN |

孪生场景在客机上的 SHADOW 只说明写入、保存、独立重开、切片和导出在这台机器上走通，不说明该行的飞书预期已经满足；11‑24 对照表里各行的预期缺口不变。

`fa-shapes` 的三次失败：

- `uia_param_spiral_vase_shapes`（`83f09dc3`）：`ProtocolError:slice_button_unavailable`（SS Jump to (spiral mode)）。同一场景在客机上也以同一签名失败（`a51409f7`，标签 `retry-spiral-shapes-1`），与机器无关。原因未查。
- `uia_param_ironing_top_shapes`（`0b240d24`）和 `uia_param_layer_pair_shapes`（`919dcaf8`）：编辑、保存、重开、切片、导出都完成，判据回答 `gcode_multiple_object_tools`（unknown），是判据对多对象盘的限制，不是 GUI 失败。

没有运行的派发，共 14 次，都不计入任何运行类别：

- 客机 `467e62b1`（02:26）：暂存检出处于 detached 状态，`hv_go` 拒绝启动。
- fa706g3 `91175532`（03:55）：场景名里带了 CRLF 行尾，参数解析拒绝。
- 客机 12 次（07:04:19–07:04:53，标签 `guest-twins-b` 与 `retry-spiral-shapes-2`，台账行带 `dispatch_failed`）：总控为第一次推送把暂存检出快进到 `62cddee` 时客机还在 `2a17376`，启动预检在 3 秒内拒绝；随后把客机同步到 `62cddee` 重排队列。这是总控的失误，没有任何东西在错误的版本上运行。

全晚合计（按飞书记录 ID 去重前的运行次数）：客机 SHADOW 101、NON_GREEN 5（两次原生模型对照、#294 两次、`spiral_vase_shapes` 一次），fa706g3 SHADOW 85、NON_GREEN 5（#294、`d5fc2fa` 上的 #268 一次、三条多形状夹具）。

Mac：控制台会话到 08:20 的最后一次检查仍在锁屏。07:51 清掉了今晚探针在 Mac 上留下的 9 个草稿目录和 `/tmp/ninehour_mac`；测试账号下没有残留的测试进程，`coil` 自己的 Orca 进程没有被触碰。
