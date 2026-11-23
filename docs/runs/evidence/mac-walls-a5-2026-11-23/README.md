# Mac 壁环数闭环（任务 A5）：证据包

标签 `mac-author-20261123-01`（续 `codex/mac-author`），2026-11-23。宿主 GLM 总控
三选一命题：SHADOW（run id+证据）| SCREEN_TCC_MISSING | blocked。
**结论：SHADOW —— run `306d3efe6882427e806afaaf9e2ad7f1`**（叙事与判据修改论证见
[运行记录](../../mac-author-walls-2026-11-23.md)）。

## 通道发现（本包两个前提性修正）

1. **屏录实际可用**（修正 A2「screencapture 超时=无 TCC」的归因细节）：
   `/usr/sbin/screencapture -x <path>` 在 gui/502 会话内**写完 PNG 后进程挂起**，
   图片落在隐藏名 `.name.png`——探针此前只检查非隐藏名+等待退出，误判"超时无图"。
   1920×1080 RGBA 有效图 ×2（尺寸互异≈实时内容），Vision OCR 完整读出 Orca 窗口
   （菜单栏/标题/Process/预设行）。证据：`tcc_probe14_result.json`（两次尝试）+
   本机 `artifacts/mac_probes/2026-11-22/tcc_a5/`（out/.full*.png 不入库）。
2. **A2 页带地图修正**：y~767 自绘带 OCR 读出五页签
   Quality/Strength/Support/Multimaterial/Others——A2 所谓"outline 页"即 **Strength
   页**（参数树）。`strength_probe15_result.json`：OCR 全局坐标与 AX 坐标逐像素
   吻合（Process(368,689) 等），"Wall loops" 行在 Strength 页**免滚动直接可见**
   （标签≈(388,835)，值 token "=2"≈(608,833)）。

## 编辑机制（probe16）

点击值格（避右侧 spinner 箭头，取 token 左端+12px）→ 该行编辑器**物化为真
AXTextField**（(627,832)，AXHelp 尾部 `parameter name: wall_loops`）→ 键入后 AX
读回 `3`。证据：`edit_probe16_result.json` 的 `ax_fields_after`。

## 判据链（两次 run + 一个对照）

| run | 结论 | 阶段 |
| --- | --- | --- |
| `ffe0c6e4`（walls，判据修改前） | NON_GREEN | GUI 全链成功（三相位 wall 读回 2/3/3、切片 receipt、独立重开），宿主 `inspect_preserved_settings` 拒绝：保存的 3MF 除 wall_loops 2→3 外还带 2.4.1 的**保存期架构迁移**（version 2.3.6→2.4.1、新增 24 键、向量迁移、预设改名 0.40→0.40mm、模板 gcode 刷新）→ `pilot_config_unknown_addition` |
| 对照 `control_save4_a5`（probe17） | ok | 编辑**另一个**参数（扁平页 initial_layer_print_height 0.4→0.44，纯 AX）后保存：噪声与 walls run **逐键同值**（added 24/24 一致；changed 57 键同值；唯一互异=各自编辑键；manifest 各记各账）→ 迁移噪声=编辑无关，实证。差分证明：`control_differential_proof.json` |
| `306d3efe`（walls，判据修改后） | **SHADOW** | 三相位独立进程 25404/25754/26039；wall 读回 2/3/3；两侧切片 68 层 receipt 验证；gcode 回显 `wall_loops=3`；挤出 XY 移动 1907→2154；工程 geometry_unchanged；差分判据通过（对照基线外仅 wall_loops 2→3）；cleanup_verified |

对照基线入库：`runner/macos/walls_control.3mf`（sha256 `2e8a5caf…834d9`）+
`runner/macos/walls_control.json`（SUT 身份 2.4.1/`a994ff90…` 锁定；构建变更时
判据自动拒绝并要求重采对照）。差分判据实现：`runner/macos_project_copy.py`
`verify_walls_differential()`——逐键规则：保存差异必须 (a) 是 wall_loops 2→3，
(b) manifest 恰好增记 wall_loops，或 (c) 与对照基线**同键同值**（编辑无关迁移）。

探针失败留痕（均为设计迭代）：`control_save_a5`（干净工程 Save 灰）、
`control_save2_a5`（往返后 `*` 标题使 slice_window 失配）、`control_save3_a5`
（2→3→2 净零往返使工程回干净态，Save 仍灰——证明"值级脏跟踪"，对照因此改为
异键编辑设计）。本机 `artifacts/mac_probes/2026-11-22/` 留有全部原始 JSON/PNG。

## GUI 预算

LaunchAgent 会话累计约 25 分钟（probe14 ~1 + probe15 ~3.5 + probe16 ~2 + walls#1 ~7
+ 对照三轮 ~3.5 + walls#2 ~7），≤30 分钟红线内。后台 Aqua 会话，未触碰前台 coil；
每轮 bootout 验证、Orca 清零（各 result `orca_left: []`）。
