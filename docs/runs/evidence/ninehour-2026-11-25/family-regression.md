# 参数族 42 行在最终引擎上的回归（两台机器）

**结论：42 行里 41 行 SHADOW，1 行 NON_GREEN。** 按各行分到的机器算：客机 win11-test 的 21 行里 21 行 SHADOW；fa706g3 的 21 行里 20 行 SHADOW、1 行 NON_GREEN。fa706g3 的结果按 README 第 6 条最高记 SHADOW，不作为发布证据。

- 引擎：最终引擎是 2a17376（2a17376 的父提交是 d5fc2fa，二者只差一个提交：5b38c80 的拣选，改 harness/process_panel.py 的 scroll_group_into_view 循环体和 unit_tests/test_param_flow.py）。62cddee 是 2a17376 和文档分支的合并，harness、tools、unit_tests 等引擎文件与 2a17376 相同（git diff --stat 2a17376 62cddee 只列出 README.md 和 docs/runs）。
- 台账复制时共 223 行、210 个 run，末行结束于 08:53:03。分到的机器上的回归运行共 42 次（提交：2a17376 42），评级计数 NON_GREEN 1、SHADOW 41。
- #294 `uia_param_timelapse`（分在 fa706g3 的行）fa706g3 `1a4c0845ae0047fca869fcd11bf74455`，06:24:07 起，动作 121.093 秒：NON_GREEN；business unknown: pilot_target_setting_mismatch、path unknown: pilot_target_setting_mismatch。
- #294 是 11‑24 就开着的那一行，不是这次改动造成的回归：11‑24 的对照里它记为「机型不适用」（Timelapse 行只在 BBL 机型上有），写入通过的是 41 条（`docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24/own-models-verdicts.md`）。
- 另一台机器上的运行是同一个场景换一台机器再取证（复核），不改变上面的结论：客机把 fa706g3 那一半跑了 19 行 20 次运行（NON_GREEN 2、SHADOW 18；没跑的 2 行：#254、#296），fa706g3 把客机那一半跑了 15 行 15 次运行（SHADOW 15；没跑的 6 行：#285、#287、#291、#293、#295、#297）。队列被总控用 STOP 文件停下，没跑的行不再补。
- 回归只回答引擎改动有没有破坏该行已有的写入和导出：队列跑的是不带后缀的 `uia_param_<key>` 场景，打开的是立方体工程，不是飞书前置条件里各自的模型和预设；它不逐项核对飞书预期。

## 最终引擎上的回归（每行两个机器）

| 飞书编号 | record ID | 用例标题 | 飞书状态 | 场景 | 机器 | run ID | 提交 | 起 | 止 | 宿主整轮秒 | 机内进程秒 | 动作秒 | 评级 | 另一台机器上的运行 |
|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|
| 255 | `reczz28b6mRB0WGN` | 线宽-全特征线宽组合 | 待实现 | uia_param_line_width_all | 客机 win11-test | `473c4e7c5e8e4419aa45ab2b0db9ed13` | 2a17376 | 05:22:39 | 05:26:34 | 234.734 | 207.449 | 103.188 | SHADOW | fa706g3 `1f87f19262394a55b32b2c81e030cb21`（2a17376）SHADOW，动作 101.562 秒，机内进程 201.727 秒 |
| 257 | `reczz28b6mRB1nLf` | 精度-尺寸补偿组合 | 待实现 | uia_param_precision_comp | 客机 win11-test | `d64dc969eca34b7f9f4bee3aa08ffa2e` | 2a17376 | 05:26:34 | 05:29:43 | 188.890 | 165.032 | 60.609 | SHADOW | fa706g3 `80708d3721434ab1a84c05ca2bf6158b`（2a17376）SHADOW，动作 59.968 秒，机内进程 160.135 秒 |
| 259 | `reczz28b6mRB0WWP` | 熨烫-顶面参数组合 | 待实现 | uia_param_ironing_top | 客机 win11-test | `1f79a0cedd23462fb69c3e738a7f8bf7` | 2a17376 | 05:29:43 | 05:32:56 | 193.515 | 167.464 | 63.078 | SHADOW | fa706g3 `68ffe89eb4634f4ca94aa7c18ca51a2e`（2a17376）SHADOW，动作 63.578 秒，机内进程 163.771 秒 |
| 261 | `reczz28b6mRAzTBr` | 墙壁和表面-单墙与避墙组合 | 待实现 | uia_param_single_wall_avoid | 客机 win11-test | `10c4fed642c74b72a96947d384e447db` | 2a17376 | 05:32:57 | 05:36:09 | 192.891 | 166.444 | 61.266 | SHADOW | fa706g3 `44d9459b105e4e78ab198db99c266e3d`（2a17376）SHADOW，动作 60.875 秒，机内进程 160.982 秒 |
| 263 | `reczz28b6mRB1jdF` | 搭桥-桥接质量组合 | 待实现 | uia_param_bridge | 客机 win11-test | `7d8d505a659946bc961f053ef0164971` | 2a17376 | 05:36:10 | 05:39:19 | 188.890 | 161.710 | 57.468 | SHADOW | fa706g3 `17cbb75b4b3c42838af8d3e2560a38fc`（2a17376）SHADOW，动作 56.766 秒，机内进程 156.898 秒 |
| 265 | `reczz28b6mRAzpVx` | 悬垂-风扇与翘边组合 | 待实现 | uia_param_overhang_curl | 客机 win11-test | `e23232a376d14c6b9d05a827bc3884e7` | 2a17376 | 05:39:19 | 05:42:08 | 169.063 | 141.086 | 36.579 | SHADOW | fa706g3 `c09780e97b664941a079b53066a0c4a6`（2a17376）SHADOW，动作 35.969 秒，机内进程 136.101 秒 |
| 267 | `reczz28b6mRB1b7s` | 外壳-层数/图案/颜色渗透组合 | 待实现 | uia_param_shells_pattern | 客机 win11-test | `2acd39bdd1ab47bb8073d1636c473de9` | 2a17376 | 05:42:08 | 05:45:21 | 193.297 | 167.404 | 60.281 | SHADOW | fa706g3 `e8982afaad47467bbe18d54bffa97d71`（2a17376）SHADOW，动作 59.141 秒，机内进程 159.268 秒 |
| 269 | `reczz28b6mRB164l` | 强度高级-填充结构组合 | 待实现 | uia_param_infill_structure | 客机 win11-test | `b4129312f198479fb8650609d5aa2024` | 2a17376 | 05:45:22 | 05:48:31 | 188.891 | 164.170 | 59.891 | SHADOW | fa706g3 `201afcf85b3b4f2c9e646f564c38a5ce`（2a17376）SHADOW，动作 59.016 秒，机内进程 159.132 秒 |
| 271 | `reczz28b6mRAyekU` | 其他层速度-特征速度组合 | 待实现 | uia_param_feature_speeds | 客机 win11-test | `7d2fabac2af5479ea1b1245974e10260` | 2a17376 | 05:48:31 | 05:52:08 | 217.516 | 192.540 | 88.344 | SHADOW | fa706g3 `4cf48ca94d0b438fa00f95cd9a2c62d5`（2a17376）SHADOW，动作 84.531 秒，机内进程 184.677 秒 |
| 273 | `reczz28b6mRB1Pm2` | 空驶速度-全局映射 | 待实现 | uia_param_travel_speed | 客机 win11-test | `a88d113829be47169c58acf8eb897a59` | 2a17376 | 05:52:08 | 05:54:58 | 169.079 | 142.408 | 38.156 | SHADOW | fa706g3 `3903e250d66d4de0bce579506b810a03`（2a17376）SHADOW，动作 37.593 秒，机内进程 137.632 秒 |
| 275 | `reczz28b6mRAytbr` | 抖动-特征组合 | 待实现 | uia_param_jerk | 客机 win11-test | `dd7ab37630b5420d98d51ae553cbec06` | 2a17376 | 05:54:58 | 05:58:31 | 213.313 | 187.701 | 83.235 | SHADOW | fa706g3 `7878899400ed492ea8608e6081ef7dc6`（2a17376）SHADOW，动作 82.171 秒，机内进程 182.303 秒 |
| 277 | `reczz28b6mRAydro` | 支撑-开启与基础结构组合 | 待实现 | uia_param_support_basic | 客机 win11-test | `cab7609dfda84f60ba51b00d2118d97e` | 2a17376 | 05:58:31 | 06:01:29 | 177.484 | 151.789 | 47.375 | SHADOW | fa706g3 `ffc75806825f4f4da23d2a41e8a8f139`（2a17376）SHADOW，动作 46.265 秒，机内进程 146.354 秒 |
| 279 | `reczz28b6mRAyV6h` | 支撑耗材-主体与界面组合 | 待实现 | uia_param_support_filament | 客机 win11-test | `98dc9db83bb5417088d3bf48985cefbf` | 2a17376 | 06:01:29 | 06:04:26 | 176.875 | 150.290 | 45.843 | SHADOW | fa706g3 `06a0db440bbd4f228251da63d4aab16f`（2a17376）SHADOW，动作 44.813 秒，机内进程 144.946 秒 |
| 281 | `reczz28b6mRAz1dW` | 支撑高级-距离与界面组合 | 待实现 | uia_param_support_interface | 客机 win11-test | `50e7445eae1d4b39b124d154414e3971` | 2a17376 | 06:04:26 | 06:08:11 | 224.906 | 197.911 | 93.578 | SHADOW | fa706g3 `4f10697c624c4705884f3520c8c84176`（2a17376）SHADOW，动作 103.656 秒，机内进程 203.783 秒 |
| 283 | `reczz28b6mRAy1At` | 擦拭塔-结构/清理/附着组合 | 待实现 | uia_param_prime_tower | 客机 win11-test | `51f2c5a1be9c42458cb0bfbd61dae68e` | 2a17376 | 06:08:11 | 06:11:56 | 225.110 | 198.764 | 94.375 | SHADOW | fa706g3 `21eedd20f0a6430bb0f136e947e9e445`（2a17376）SHADOW，动作 78.110 秒，机内进程 178.152 秒 |
| 285 | `reczz28b6mRB1fwT` | Ooze预防-待机与预热组合 | 待实现 | uia_param_ooze_prevention | 客机 win11-test | `c27e3d11da3c460c994a5f4d96dd8ec1` | 2a17376 | 06:11:56 | 06:15:06 | 189.281 | 160.842 | 56.469 | SHADOW | - |
| 287 | `reczz28b6mRAzl7P` | 材料高级-界面外壳与工具组合 | 待实现 | uia_param_material_advanced | 客机 win11-test | `55065a003b19456da086f600474bb42b` | 2a17376 | 06:15:06 | 06:18:23 | 197.313 | 169.024 | 64.593 | SHADOW | - |
| 291 | `reczz28b6mRAyNfH` | Brim-宽度间隙与类型组合 | 待实现 | uia_param_brim | 客机 win11-test | `f6dc29a855044611be03ed93a7eed870` | 2a17376 | 06:18:23 | 06:21:29 | 185.078 | 157.556 | 53.218 | SHADOW | - |
| 293 | `reczz28b6mRB19md` | 特殊模式-螺旋花瓶单墙 | 待实现 | uia_param_spiral_vase | 客机 win11-test | `e2dc078f7d384e5693b18ffee354845a` | 2a17376 | 06:21:29 | 06:24:34 | 184.875 | 157.235 | 52.875 | SHADOW | - |
| 295 | `reczz28b6mRAyPQV` | 绒毛表面-范围/点距/厚度组合 | 待实现 | uia_param_fuzzy | 客机 win11-test | `c953a01499a24423b5b7f28f794970a3` | 2a17376 | 06:24:34 | 06:27:39 | 184.875 | 159.859 | 55.312 | SHADOW | - |
| 297 | `reczz28b6mRAyshq` | G-code输出-排除对象与填充回抽组合 | 待实现 | uia_param_exclude_objects | 客机 win11-test | `2c581bd4b35f4d358dbde5cefac710c2` | 2a17376 | 06:27:39 | 06:30:28 | 169.063 | 141.737 | 37.156 | SHADOW | - |
| 256 | `reczz28b6mRAynyS` | 接缝-位置/间隙/擦拭组合 | 待实现 | uia_param_seam_wipe | fa706g3 | `fefd58ea53cb432bb97433c828b2576a` | 2a17376 | 05:17:18 | 05:20:51 | - | 160.006 | 59.781 | SHADOW | 客机 `02d7bf394c374d7f95807c93e28710f4`（62cddee）SHADOW，动作 60.890 秒，宿主整轮 194.938 秒 |
| 258 | `reczz28b6mRAyQE3` | 精度-圆弧/分辨率/间隙闭合组合 | 待实现 | uia_param_arc_resolution | fa706g3 | `3a43c6fd450147f8a2a011d45b63e5e1` | 2a17376 | 05:20:51 | 05:24:25 | - | 146.721 | 46.468 | SHADOW | 客机 `04e231ffd70741969e79756c520d73fb`（62cddee）SHADOW，动作 47.360 秒，宿主整轮 177.313 秒 |
| 260 | `reczz28b6mRAxxD7` | 墙生成器-Arachne薄壁组合 | 待实现 | uia_param_wall_generator | fa706g3 | `ea11c71012154f1c9f1640aa1db2d8c4` | 2a17376 | 05:24:25 | 05:27:59 | - | 143.910 | 43.672 | SHADOW | 客机 `80821d98a4ea469895b75c714d7de7a8`（62cddee）SHADOW，动作 44.094 秒，宿主整轮 174.703 秒 |
| 262 | `reczz28b6mRAyIRW` | 墙壁和表面-表面流量组合 | 待实现 | uia_param_surface_flow | fa706g3 | `f3daf5c3e30e4cba8303e2418f99d0a0` | 2a17376 | 05:27:59 | 05:31:32 | - | 151.732 | 51.515 | SHADOW | 客机 `dee9cd5a447f4dd7a00599a838072212`（62cddee）SHADOW，动作 51.718 秒，宿主整轮 182.718 秒 |
| 264 | `reczz28b6mRB0mjp` | 悬垂-识别与分档速度组合 | 待实现 | uia_param_overhang_speeds | fa706g3 | `b82b9932762a446f9386182e9501aaa9` | 2a17376 | 05:31:32 | 05:35:33 | - | 182.286 | 82.140 | SHADOW | 客机 `0165cedec6ec4c71ba78ec9ee07a3953`（62cddee）SHADOW，动作 81.843 秒，宿主整轮 214.953 秒 |
| 266 | `reczz28b6mRAyM4X` | 墙-圈数与薄壁组合 | 待实现 | uia_param_wall_thin | fa706g3 | `09b59283ea2049de9213b0a2b20d01e1` | 2a17376 | 05:35:33 | 05:39:07 | - | 142.549 | 42.297 | SHADOW | 客机 `1b314163f78645e5a76018039f87a4d7`（62cddee）SHADOW，动作 43.046 秒，宿主整轮 174.500 秒 |
| 268 | `reczz28b6mRAz0f1` | 填充-密度/图案/方向/重叠组合 | 待实现 | uia_param_infill_combo | fa706g3 | `72f7f6ded4174e2db24d6844d7cc8921` | 2a17376 | 05:39:07 | 05:43:08 | - | 179.906 | 79.750 | SHADOW | 客机 `aaa49b9ef15e49d1831e2995f8c92b61`（62cddee）SHADOW，动作 80.828 秒，宿主整轮 213.531 秒 |
| 270 | `reczz28b6mRAyhVJ` | 首层速度-全速度链组合 | 待实现 | uia_param_first_speeds | fa706g3 | `e15272b87a904d0ab18e02dd3f45ff0a` | 2a17376 | 05:43:08 | 05:46:41 | - | 153.962 | 53.688 | SHADOW | 客机 `66f63d335dc3433bb1b5c7a68538e24d`（62cddee）SHADOW，动作 55.953 秒，宿主整轮 186.516 秒 |
| 272 | `reczz28b6mRB1ZL4` | 悬垂速度-分档与桥接组合 | 待实现 | uia_param_overhang_bridge | fa706g3 | `ed9d6ba332314cb28c2a8b9229b3470e` | 2a17376 | 05:46:42 | 05:50:42 | - | 181.931 | 81.796 | SHADOW | 客机 `cbe8a4335d7f4515ac2993841d2419ef`（62cddee）SHADOW，动作 81.297 秒，宿主整轮 213.329 秒 |
| 274 | `reczz28b6mRAzthX` | 加速度-特征组合 | 待实现 | uia_param_accelerations | fa706g3 | `5f69c567baa94d1d8653b35c9276fbf4` | 2a17376 | 05:50:42 | 05:54:43 | - | 189.569 | 89.438 | SHADOW | 客机 `815c099d3d30423f9c9f7801bbfe5cfb`（62cddee）SHADOW，动作 100.312 秒，宿主整轮 228.969 秒 |
| 276 | `reczz28b6mRAyH5p` | 速度高级-流量与机器上限组合 | 待实现 | uia_param_speed_limits | fa706g3 | `9d89930fbff44e2f9c35323d0d7f54b8` | 2a17376 | 05:54:43 | 05:58:44 | - | 164.649 | 64.391 | SHADOW | 客机 `73d9f22ebb7e40a7886e811341327783`（62cddee）SHADOW，动作 65.437 秒，宿主整轮 197.625 秒 |
| 278 | `reczz28b6mRAzKa2` | 筏层-结构/间距/扩展组合 | 待实现 | uia_param_raft | fa706g3 | `f8267f3b550e428bb7ee86c71a85d346` | 2a17376 | 05:58:44 | 06:02:45 | - | 177.285 | 77.032 | SHADOW | 客机 `daf3216f04904db09960ada51ddd5401`（62cddee）SHADOW，动作 77.515 秒，宿主整轮 209.125 秒 |
| 280 | `reczz28b6mRAz8Gm` | 支撑熨烫-开关/流量/间距组合 | 待实现 | uia_param_support_ironing | fa706g3 | `4000ec43039e49e68a75b947e13eb87a` | 2a17376 | 06:02:45 | 06:06:19 | - | 159.248 | 58.922 | SHADOW | 客机 `8a1d5cdf9f344cc7a3f5a56309c7d5d8`（62cddee）SHADOW，动作 59.922 秒，宿主整轮 189.500 秒 |
| 282 | `reczz28b6mRB0dhl` | 支撑高级-树状支撑组合 | 待实现 | uia_param_tree_support | fa706g3 | `b543390be2fb4083939b585f2248ec10` | 2a17376 | 06:06:19 | 06:10:19 | - | 184.715 | 84.531 | SHADOW | 客机 `8389410639784112a8fc26ce647b9be9`（62cddee）SHADOW，动作 85.188 秒，宿主整轮 218.750 秒 |
| 284 | `reczz28b6mRAzFuo` | 特征用耗材-塔与支撑映射组合 | 待实现 | uia_param_filament_features | fa706g3 | `85f43119a4b84389b6bf4b5e4cdca8fb` | 2a17376 | 06:10:20 | 06:13:53 | - | 145.009 | 44.766 | SHADOW | 客机 `b232861c7b0b4c93a55f3834ddcf75ed`（62cddee）SHADOW，动作 46.141 秒，宿主整轮 177.109 秒 |
| 286 | `reczz28b6mRB035T` | 换料冲刷-去向与体积组合 | 待实现 | uia_param_flush_options | fa706g3 | `27bb889edf9b413c917b0e0c21bd0da2` | 2a17376 | 06:13:53 | 06:17:27 | - | 145.869 | 45.531 | SHADOW | 客机 `1af4dc1b0ed344aa8f68cf2c565d9a00`（62cddee）SHADOW，动作 46.234 秒，宿主整轮 177.094 秒 |
| 290 | `reczz28b6mRAyRCt` | 裙边-圈数高度距离与风挡组合 | 待实现 | uia_param_skirt | fa706g3 | `a8f21d45f0334cc3b0c13f5a1d827173` | 2a17376 | 06:17:27 | 06:21:01 | - | 159.501 | 59.219 | SHADOW | 客机 `749da4390b2f4b898065dfebc645fb66`（62cddee）SHADOW，动作 60.203 秒，宿主整轮 190.719 秒 |
| 292 | `reczz28b6mRB1mQt` | 特殊模式-逐件打印与碰撞 | 待实现 | uia_param_by_object | fa706g3 | `9ad1b7e263cd4a609dc47c8ef86123a1` | 2a17376 | 06:21:01 | 06:24:07 | - | 134.938 | 34.594 | SHADOW | 客机 `698cf755ae45401abd52ee1b01d7ef65`（62cddee）SHADOW，动作 35.094 秒，宿主整轮 165.125 秒 |
| 294 | `reczz28b6mRAzCq8` | 特殊模式-延时与切片模式组合 | 待实现 | uia_param_timelapse | fa706g3 | `1a4c0845ae0047fca869fcd11bf74455` | 2a17376 | 06:24:07 | 06:29:02 | - | 221.134 | 121.093 | NON_GREEN；business unknown: pilot_target_setting_mismatch、path unknown: pilot_target_setting_mismatch | 客机 `9db255d48fe64f2db8564a1c476ae48d`（2a17376）NON_GREEN；business unknown: pilot_target_setting_mismatch、path unknown: pilot_target_setting_mismatch，动作 122.453 秒，宿主整轮 253.000 秒；客机 `ed62daca9e32493db81ae78155a6d709`（62cddee）NON_GREEN；business unknown: pilot_target_setting_mismatch、path unknown: pilot_target_setting_mismatch，动作 122.359 秒，宿主整轮 254.968 秒 |
| 296 | `reczz28b6mRAyaVq` | G-code输出-注释/行号/标签/文件名组合 | 待实现 | uia_param_gcode_output | fa706g3 | `2c31895fb3994cb193a020beca14b979` | 2a17376 | 06:29:02 | 06:33:03 | - | 164.318 | 63.860 | SHADOW | - |
| 254 | `reczz28b6mRB1GVG` | 层高-首层与常规层高组合 | 待实现 | uia_param_layer_pair | fa706g3 | `1f6c810ad1ca4ebba0b286f07e23a8e9` | 2a17376 | 06:33:03 | 06:36:10 | - | 127.626 | 27.391 | SHADOW | - |

## 不是最终引擎上的回归（d5fc2fa，已被上表取代）

这是修正提交之前先跑的那一部分，不计入最终引擎的结果。SHADOW 的行：客机 4 行（#255、#257、#259、#261），fa706g3 7 行（#256、#258、#260、#262、#264、#266、#270）。fa706g3 上失败 1 次（`62a3cd01`），之后两台机器重试 8 次（客机 4、fa706g3 4；SHADOW 8）。

| 机器 | 飞书编号 | 场景 | run ID | 标签 | 起 | 动作秒 | 评级 |
|---|---|---|---|---|---|---:|---|
| 客机 win11-test | #255 | uia_param_line_width_all | `cfaa8a0d3aa94d929028838c8dc71310` | regress-final | 04:11:57 | 103.391 | SHADOW |
| 客机 win11-test | #257 | uia_param_precision_comp | `ee33d983b0c04517ab418bc3f1e85c3d` | regress-final | 04:15:51 | 63.469 | SHADOW |
| 客机 win11-test | #259 | uia_param_ironing_top | `8ef072a97c2042b597b567014922f6ac` | regress-final | 04:19:04 | 63.110 | SHADOW |
| 客机 win11-test | #261 | uia_param_single_wall_avoid | `b0f9538396a34f9ea1eb1d182ed5e3e1` | regress-final | 04:22:18 | 61.031 | SHADOW |
| fa706g3 | #256 | uia_param_seam_wipe | `8352f74d3bb6492db7333d850447b2f9` | regress-final | 03:58:34 | 59.797 | SHADOW |
| fa706g3 | #258 | uia_param_arc_resolution | `925fe20fbfcd474380ff3f77743aed56` | regress-final | 04:02:08 | 46.438 | SHADOW |
| fa706g3 | #260 | uia_param_wall_generator | `afc73d60a48b4dbc892f77f942e69c76` | regress-final | 04:05:42 | 43.656 | SHADOW |
| fa706g3 | #262 | uia_param_surface_flow | `c7c8a5475e404cc2a3849a1a8bf8df5b` | regress-final | 04:09:15 | 51.500 | SHADOW |
| fa706g3 | #264 | uia_param_overhang_speeds | `9e687519d15a4b77a6cfb7fa12ddba47` | regress-final | 04:12:49 | 82.157 | SHADOW |
| fa706g3 | #266 | uia_param_wall_thin | `ac15b9ca5fad4b7da33e02c42f192b89` | regress-final | 04:16:50 | 42.297 | SHADOW |
| fa706g3 | #268 | uia_param_infill_combo | `62a3cd012aa549f593e3c6630db4c6b9` | regress-final | 04:20:23 | 34.578 | NON_GREEN：`ProtocolError:param_combo_readback:Gyroid:Grid`；business unknown: not checked、path unknown: not checked |
| fa706g3 | #268 | uia_param_infill_combo | `47d680529b2140968547bcc48351edfc` | retry-infill-1 | 04:28:45 | 79.766 | SHADOW |
| 客机 win11-test | #268 | uia_param_infill_combo | `d58abb248fb14ddf9e3baed84c90ba13` | retry-infill-1 | 04:28:45 | 80.890 | SHADOW |
| 客机 win11-test | #268 | uia_param_infill_combo | `3f5f22d753684e6797dbc3808b8ed039` | retry-infill-2 | 04:32:18 | 80.609 | SHADOW |
| fa706g3 | #268 | uia_param_infill_combo | `cad6b0103b834310b4836c08979930f7` | retry-infill-2 | 04:32:46 | 79.782 | SHADOW |
| 客机 win11-test | #268 | uia_param_infill_combo | `da86773c154c4f7698da7eb2f2509cd1` | retry-infill-3 | 04:36:49 | 80.578 | SHADOW |
| 客机 win11-test | #268 | uia_param_infill_combo | `0b51fb837ff44727951931dc769bb61b` | retry-infill-4 | 04:40:23 | 80.860 | SHADOW |
| fa706g3 | #268 | uia_param_infill_combo | `f4d9633d9b784e85897741bda3609b91` | retry-infill-3 | 04:41:01 | 79.766 | SHADOW |
| fa706g3 | #268 | uia_param_infill_combo | `38cf0c29f7ec4f98bc9bd1ef98594354` | retry-infill-4 | 04:45:02 | 79.719 | SHADOW |
| fa706g3 | #270 | uia_param_first_speeds | `74f17375bbda48fb9e06d91f0a8b3e4a` | regress-final | 04:23:03 | 53.688 | SHADOW |

没有收割件的派发（没有到 GUI，没有评级，不属于任何一类运行）见 [dispatch-failures.md](dispatch-failures.md)，其中带着回归标签、场景是这 42 行之一的有 1 条（`91175532`）。

来源：`family-regression.json`（`scripts/build_family.py`）。
