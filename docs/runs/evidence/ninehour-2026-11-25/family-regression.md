# 参数族 42 行在最终引擎上的回归（进行中，占位）

**状态：进行中。** 最终引擎上的 42 行参数族回归仍在进行。本文件在台账复制时生成，只填台账里已有的结果；没有结果的行留空，由总控在回归结束后补入。

引擎：合并提交 d5fc2fa。git diff --stat e3bfdfe d5fc2fa 只列出 tools/ninehour_receipts.py 和它的单测；引擎相同。
台账复制时共 72 行、71 个 run，末行结束于 04:43:56。两台机器分跑，每行计划一次（失败后的重试也列在该行里）：客机 win11-test 21 行，fa706g3 21 行（客机是回归证据机；fa706g3 最高记 SHADOW）。

已出结果 12 行（客机 4，fa706g3 8；评级计数 NON_GREEN 1, SHADOW 17），其中出现过失败运行的 1 行（#268）。尚未出结果 30 行（#254、#263、#265、#267、#269、#271、#272、#273、#274、#275、#276、#277、#278、#279、#280、#281、#282、#283、#284、#285、#286、#287、#290、#291、#292、#293、#294、#295、#296、#297）。派发失败 1 次（91175532），落在 #256。

- 「出现过失败运行」的行：该行在最终引擎上至少一次运行不是 SHADOW。重试用 `retry-` 标签记，算作同一行的回归运行；重试落在另一台机器时，在该行里注出机器。
- 「派发失败」是队列脚本把行尾的 CR 带进了场景名（台账场景名以 `\r` 结尾，`native_save_run.py` 打印用法后退出，没有 `result.json`，没有收据），不是用例失败；队列脚本修正后重派。
- 回归只回答「引擎改动有没有破坏这 42 行已有的写入和导出」，不逐项核对飞书预期；预期核对见 `feishu-216-ninehour.md` 的「未通过项」和 11-24 的对照表。
- 评级取收据的 `release_verdict`；fa706g3 上的 SHADOW 按 README 第 6 条不作为发布证据。

| 飞书编号 | record ID | 用例标题 | 飞书状态 | 场景 | 机器 | 顺序 | run ID | 提交 | 起 | 止 | 宿主整轮秒 | 机内进程秒 | 动作秒 | 评级 | 状态 |
|---|---|---|---|---|---|---:|---|---|---|---|---:|---:|---:|---|---|
| 255 | `reczz28b6mRB0WGN` | 线宽-全特征线宽组合 | 待实现 | uia_param_line_width_all | 客机 win11-test | 1 | `cfaa8a0d3aa94d929028838c8dc71310` | d5fc2fa | 04:11:57 | 04:15:50 | 232.922 | 208.298 | 103.391 | SHADOW | regress-final |
| 257 | `reczz28b6mRB1nLf` | 精度-尺寸补偿组合 | 待实现 | uia_param_precision_comp | 客机 win11-test | 2 | `ee33d983b0c04517ab418bc3f1e85c3d` | d5fc2fa | 04:15:51 | 04:19:04 | 193.297 | 167.845 | 63.469 | SHADOW | regress-final |
| 259 | `reczz28b6mRB0WWP` | 熨烫-顶面参数组合 | 待实现 | uia_param_ironing_top | 客机 win11-test | 3 | `8ef072a97c2042b597b567014922f6ac` | d5fc2fa | 04:19:04 | 04:22:18 | 193.703 | 167.629 | 63.110 | SHADOW | regress-final |
| 261 | `reczz28b6mRAzTBr` | 墙壁和表面-单墙与避墙组合 | 待实现 | uia_param_single_wall_avoid | 客机 win11-test | 4 | `b0f9538396a34f9ea1eb1d182ed5e3e1` | d5fc2fa | 04:22:18 | 04:25:31 | 192.922 | 165.355 | 61.031 | SHADOW | regress-final |
| 263 | `reczz28b6mRB1jdF` | 搭桥-桥接质量组合 | 待实现 | uia_param_bridge | 客机 win11-test | 5 | - | - | - | - | - | - | - | - | - |
| 265 | `reczz28b6mRAzpVx` | 悬垂-风扇与翘边组合 | 待实现 | uia_param_overhang_curl | 客机 win11-test | 6 | - | - | - | - | - | - | - | - | - |
| 267 | `reczz28b6mRB1b7s` | 外壳-层数/图案/颜色渗透组合 | 待实现 | uia_param_shells_pattern | 客机 win11-test | 7 | - | - | - | - | - | - | - | - | - |
| 269 | `reczz28b6mRB164l` | 强度高级-填充结构组合 | 待实现 | uia_param_infill_structure | 客机 win11-test | 8 | - | - | - | - | - | - | - | - | - |
| 271 | `reczz28b6mRAyekU` | 其他层速度-特征速度组合 | 待实现 | uia_param_feature_speeds | 客机 win11-test | 9 | - | - | - | - | - | - | - | - | - |
| 273 | `reczz28b6mRB1Pm2` | 空驶速度-全局映射 | 待实现 | uia_param_travel_speed | 客机 win11-test | 10 | - | - | - | - | - | - | - | - | - |
| 275 | `reczz28b6mRAytbr` | 抖动-特征组合 | 待实现 | uia_param_jerk | 客机 win11-test | 11 | - | - | - | - | - | - | - | - | - |
| 277 | `reczz28b6mRAydro` | 支撑-开启与基础结构组合 | 待实现 | uia_param_support_basic | 客机 win11-test | 12 | - | - | - | - | - | - | - | - | - |
| 279 | `reczz28b6mRAyV6h` | 支撑耗材-主体与界面组合 | 待实现 | uia_param_support_filament | 客机 win11-test | 13 | - | - | - | - | - | - | - | - | - |
| 281 | `reczz28b6mRAz1dW` | 支撑高级-距离与界面组合 | 待实现 | uia_param_support_interface | 客机 win11-test | 14 | - | - | - | - | - | - | - | - | - |
| 283 | `reczz28b6mRAy1At` | 擦拭塔-结构/清理/附着组合 | 待实现 | uia_param_prime_tower | 客机 win11-test | 15 | - | - | - | - | - | - | - | - | - |
| 285 | `reczz28b6mRB1fwT` | Ooze预防-待机与预热组合 | 待实现 | uia_param_ooze_prevention | 客机 win11-test | 16 | - | - | - | - | - | - | - | - | - |
| 287 | `reczz28b6mRAzl7P` | 材料高级-界面外壳与工具组合 | 待实现 | uia_param_material_advanced | 客机 win11-test | 17 | - | - | - | - | - | - | - | - | - |
| 291 | `reczz28b6mRAyNfH` | Brim-宽度间隙与类型组合 | 待实现 | uia_param_brim | 客机 win11-test | 18 | - | - | - | - | - | - | - | - | - |
| 293 | `reczz28b6mRB19md` | 特殊模式-螺旋花瓶单墙 | 待实现 | uia_param_spiral_vase | 客机 win11-test | 19 | - | - | - | - | - | - | - | - | - |
| 295 | `reczz28b6mRAyPQV` | 绒毛表面-范围/点距/厚度组合 | 待实现 | uia_param_fuzzy | 客机 win11-test | 20 | - | - | - | - | - | - | - | - | - |
| 297 | `reczz28b6mRAyshq` | G-code输出-排除对象与填充回抽组合 | 待实现 | uia_param_exclude_objects | 客机 win11-test | 21 | - | - | - | - | - | - | - | - | - |
| 256 | `reczz28b6mRAynyS` | 接缝-位置/间隙/擦拭组合 | 待实现 | uia_param_seam_wipe | fa706g3 | 1 | `9117553219f14bc58703177577b2ebb9` | d5fc2fa | 03:55:54 | 03:57:03 | - | - | - | - | regress-final no worker.json |
|  |  |  |  |  |  |  | `8352f74d3bb6492db7333d850447b2f9` | d5fc2fa | 03:58:34 | 04:02:08 | - | 160.031 | 59.797 | SHADOW | regress-final |
| 258 | `reczz28b6mRAyQE3` | 精度-圆弧/分辨率/间隙闭合组合 | 待实现 | uia_param_arc_resolution | fa706g3 | 2 | `925fe20fbfcd474380ff3f77743aed56` | d5fc2fa | 04:02:08 | 04:05:42 | - | 146.608 | 46.438 | SHADOW | regress-final |
| 260 | `reczz28b6mRAxxD7` | 墙生成器-Arachne薄壁组合 | 待实现 | uia_param_wall_generator | fa706g3 | 3 | `afc73d60a48b4dbc892f77f942e69c76` | d5fc2fa | 04:05:42 | 04:09:15 | - | 143.874 | 43.656 | SHADOW | regress-final |
| 262 | `reczz28b6mRAyIRW` | 墙壁和表面-表面流量组合 | 待实现 | uia_param_surface_flow | fa706g3 | 4 | `c7c8a5475e404cc2a3849a1a8bf8df5b` | d5fc2fa | 04:09:15 | 04:12:49 | - | 151.782 | 51.500 | SHADOW | regress-final |
| 264 | `reczz28b6mRB0mjp` | 悬垂-识别与分档速度组合 | 待实现 | uia_param_overhang_speeds | fa706g3 | 5 | `9e687519d15a4b77a6cfb7fa12ddba47` | d5fc2fa | 04:12:49 | 04:16:50 | - | 182.284 | 82.157 | SHADOW | regress-final |
| 266 | `reczz28b6mRAyM4X` | 墙-圈数与薄壁组合 | 待实现 | uia_param_wall_thin | fa706g3 | 6 | `ac15b9ca5fad4b7da33e02c42f192b89` | d5fc2fa | 04:16:50 | 04:20:23 | - | 142.467 | 42.297 | SHADOW | regress-final |
| 268 | `reczz28b6mRAz0f1` | 填充-密度/图案/方向/重叠组合 | 待实现 | uia_param_infill_combo | fa706g3 | 7 | `62a3cd012aa549f593e3c6630db4c6b9` | d5fc2fa | 04:20:23 | 04:23:03 | - | 85.499 | 34.578 | NON_GREEN | regress-final（失败） |
|  |  |  |  |  |  |  | `47d680529b2140968547bcc48351edfc` | d5fc2fa | 04:28:45 | 04:32:46 | - | 179.893 | 79.766 | SHADOW | retry-infill-1 |
|  |  |  |  |  |  |  | `d58abb248fb14ddf9e3baed84c90ba13` | d5fc2fa | 04:28:45 | 04:32:18 | 213.594 | 185.281 | 80.890 | SHADOW | retry-infill-1（客机 win11-test） |
|  |  |  |  |  |  |  | `3f5f22d753684e6797dbc3808b8ed039` | d5fc2fa | 04:32:18 | 04:35:52 | 213.109 | 184.993 | 80.609 | SHADOW | retry-infill-2（客机 win11-test） |
|  |  |  |  |  |  |  | `cad6b0103b834310b4836c08979930f7` | d5fc2fa | 04:32:46 | 04:36:46 | - | 180.012 | 79.782 | SHADOW | retry-infill-2 |
|  |  |  |  |  |  |  | `da86773c154c4f7698da7eb2f2509cd1` | d5fc2fa | 04:36:49 | 04:40:23 | 213.172 | 184.792 | 80.578 | SHADOW | retry-infill-3（客机 win11-test） |
|  |  |  |  |  |  |  | `0b51fb837ff44727951931dc769bb61b` | d5fc2fa | 04:40:23 | 04:43:56 | 213.328 | 185.228 | 80.860 | SHADOW | retry-infill-4（客机 win11-test） |
| 270 | `reczz28b6mRAyhVJ` | 首层速度-全速度链组合 | 待实现 | uia_param_first_speeds | fa706g3 | 8 | `74f17375bbda48fb9e06d91f0a8b3e4a` | d5fc2fa | 04:23:03 | 04:26:36 | - | 153.929 | 53.688 | SHADOW | regress-final |
| 272 | `reczz28b6mRB1ZL4` | 悬垂速度-分档与桥接组合 | 待实现 | uia_param_overhang_bridge | fa706g3 | 9 | - | - | - | - | - | - | - | - | - |
| 274 | `reczz28b6mRAzthX` | 加速度-特征组合 | 待实现 | uia_param_accelerations | fa706g3 | 10 | - | - | - | - | - | - | - | - | - |
| 276 | `reczz28b6mRAyH5p` | 速度高级-流量与机器上限组合 | 待实现 | uia_param_speed_limits | fa706g3 | 11 | - | - | - | - | - | - | - | - | - |
| 278 | `reczz28b6mRAzKa2` | 筏层-结构/间距/扩展组合 | 待实现 | uia_param_raft | fa706g3 | 12 | - | - | - | - | - | - | - | - | - |
| 280 | `reczz28b6mRAz8Gm` | 支撑熨烫-开关/流量/间距组合 | 待实现 | uia_param_support_ironing | fa706g3 | 13 | - | - | - | - | - | - | - | - | - |
| 282 | `reczz28b6mRB0dhl` | 支撑高级-树状支撑组合 | 待实现 | uia_param_tree_support | fa706g3 | 14 | - | - | - | - | - | - | - | - | - |
| 284 | `reczz28b6mRAzFuo` | 特征用耗材-塔与支撑映射组合 | 待实现 | uia_param_filament_features | fa706g3 | 15 | - | - | - | - | - | - | - | - | - |
| 286 | `reczz28b6mRB035T` | 换料冲刷-去向与体积组合 | 待实现 | uia_param_flush_options | fa706g3 | 16 | - | - | - | - | - | - | - | - | - |
| 290 | `reczz28b6mRAyRCt` | 裙边-圈数高度距离与风挡组合 | 待实现 | uia_param_skirt | fa706g3 | 17 | - | - | - | - | - | - | - | - | - |
| 292 | `reczz28b6mRB1mQt` | 特殊模式-逐件打印与碰撞 | 待实现 | uia_param_by_object | fa706g3 | 18 | - | - | - | - | - | - | - | - | - |
| 294 | `reczz28b6mRAzCq8` | 特殊模式-延时与切片模式组合 | 待实现 | uia_param_timelapse | fa706g3 | 19 | - | - | - | - | - | - | - | - | - |
| 296 | `reczz28b6mRAyaVq` | G-code输出-注释/行号/标签/文件名组合 | 待实现 | uia_param_gcode_output | fa706g3 | 20 | - | - | - | - | - | - | - | - | - |
| 254 | `reczz28b6mRB1GVG` | 层高-首层与常规层高组合 | 待实现 | uia_param_layer_pair | fa706g3 | 21 | - | - | - | - | - | - | - | - | - |

来源：`family-regression.json`（`scripts/build_family.py`）。
