# 没有跑起来的派发

共 14 条（客机 13 条，fa706g3 1 条）。它们没有收据，说明什么都没有收割到、没有到 GUI：没有评级，不属于任何一类运行，不记在 SHADOW 里，也不算失败轮。台账复制时共 223 行、210 个 run，末行结束于 08:53:03。

| run ID | 机器 | 起 | 场景 | 标签 | 文件记录下来的 | 原因（一句话） |
|---|---|---|---|---|---|---|
| `467e62b17339413f83fdc00ac131c770` | 客机 win11-test | 02:26:10 | `uia_param_overhang_speeds` | timed-vm-1 | `host checkout must be on a branch`（02:26:11.509 起，02:26:28.941 止） | 暂存 checkout 处在游离的 HEAD 上，hv_go 拒绝启动 |
| `9117553219f14bc58703177577b2ebb9` | fa706g3 | 03:55:54 | `uia_param_seam_wipe`（台账里带行尾 CR） | regress-final | 任务日志 `native_save_run.py: error: argument --scenario: invalid choice`，解析出的场景名带行尾 CR | 场景名带行尾 CR，参数解析拒绝 |
| `65ea51fda43e4947b2b07e7326642847` | 客机 win11-test | 07:04:19 | `uia_param_spiral_vase_shapes` | retry-spiral-shapes-2 | `demo_guest_sync_or_runtime_required`（07:04:20.388 起，07:04:20.954 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `616c52eae7e741c8a4aac515392452c8` | 客机 win11-test | 07:04:22 | `uia_param_seam_wipe_cyl` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:23.983 起，07:04:24.612 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `90b0a97bfce149c788f2fa645c43c7d7` | 客机 win11-test | 07:04:25 | `uia_param_precision_comp_tol` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:26.830 起，07:04:27.424 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `ad3862e9855e4febb169a5da2051cdda` | 客机 win11-test | 07:04:28 | `uia_param_overhang_bridge_fdmt` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:29.720 起，07:04:30.286 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `babd20bcc2494d1c9a0258ccd8dc824b` | 客机 win11-test | 07:04:31 | `uia_param_jerk_cyl` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:33.324 起，07:04:34.041 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `b6605b62161c4495891dce0cf6d797f7` | 客机 win11-test | 07:04:34 | `uia_param_support_filament_fdmt2` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:36.185 起，07:04:36.835 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `fd60d7ef1c6143d6b02b21ae0d5e1385` | 客机 win11-test | 07:04:37 | `uia_param_prime_tower_boat2` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:39.056 起，07:04:39.639 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `c1bbbdbd4651428d8536fc0878174823` | 客机 win11-test | 07:04:40 | `uia_param_filament_features_fdmt2` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:41.942 起，07:04:42.505 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `d9ecf8bc1bf941e89d3f58a8261d1d7a` | 客机 win11-test | 07:04:43 | `uia_param_flush_options_boat2` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:45.516 起，07:04:46.143 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `a744e6db550b4035a0ffee0ba4ddc731` | 客机 win11-test | 07:04:47 | `uia_param_material_advanced_fdmt2` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:48.367 起，07:04:48.971 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `d29a6a0a202b494faeae80bae858a7c8` | 客机 win11-test | 07:04:50 | `uia_param_tree_support_bunny` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:51.236 起，07:04:51.823 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |
| `91e1191c81604409b21f24eaf1062df9` | 客机 win11-test | 07:04:53 | `uia_param_ooze_prevention_hell` | guest-twins-b | `demo_guest_sync_or_runtime_required`（07:04:54.835 起，07:04:55.510 止） | 客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝 |

原因按组各记一次。前一半是文件里有的，后一半（总控的说明）是总控对当晚经过的交代：

- 02:26 的一条：总控的说明：暂存 checkout 当时处在游离的 HEAD 上，hv_go 拒绝启动；切回分支后重跑，是 `778bbfa2`
- 03:55 的一条：总控的说明：队列脚本把一行的行尾（CR）带进了场景名，参数解析拒绝了它；修正队列脚本后重跑，是 `8352f74d`
- 07:04:19–07:04:53 的十二条：总控的说明：为第一次推送把暂存 checkout 快进到 62cddee 时，客机还在 2a17376 上，native_save_demo 的 HEAD 检查拒绝了每一次启动；之后把客机同步到 62cddee，guest-twins-b 的 11 个场景换了新的 run ID 重跑。这是总控的失误，这些 run 什么都没有跑

来源：`dispatch-failures.json`（`scripts/build_dispatches.py`，读台账副本、收据目录和 `C:/coil/Projects/SnapmakerOrca/external/orca-blackbox/artifacts` 下各 run 的启动回执或任务日志）。
