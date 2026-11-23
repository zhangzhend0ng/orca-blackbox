# macOS 壁环数 2→3 首次闭环（任务 A5）：SHADOW 运行记录

本轮请求标签 `mac-author-20261123-01`（续 `codex/mac-author`）。宿主 GLM 总控派发
三选一：SHADOW（run id+证据）| SCREEN_TCC_MISSING（截屏测试细节）| blocked。
**结论：SHADOW —— run `306d3efe6882427e806afaaf9e2ad7f1`**，全证据包见
[evidence/mac-walls-a5-2026-11-23/](evidence/mac-walls-a5-2026-11-23/README.md)。

执行环境与前轮相同：Mac mini coilwin@172.18.6.213（macOS 26.6.2 arm64），测试登录
`coilwin`(502) 后台 Aqua 会话（console 由 coil 501 占用），SUT
`/Applications/Snapmaker Orca.app` 2.4.1 只读（exe sha256 `a994ff90…ffdcd`，与
2026-11-20 实录一致），夹具 `fixtures/agent_layer_cube.3mf`。通道：既有
LaunchAgent（gui/502，签名 Python.app）+ SSH localhost 驱动仓库入口，未改传输协议。

## 第一步：屏录授权验证——可用（细节修正 A2 归因）

任务书判据"超时=未授权"在 probe14 上再次触发（`screencapture -x` 两次 10s 超时，
红线 ≤2 次遵守）。但收割目录里发现 **`.full.png` / `.full_retry.png`（各 1.6MB，
1920×1080 RGBA 有效 PNG）**：screencapture 在该会话**写完图后进程挂起**，图片落
隐藏名 `.name.png`；此前 A2/上轮探针只等退出+查非隐藏名，把"挂起"误归因为
"无屏录 TCC"。宿主侧 Vision（`tools/ocr_probe.swift`，无需 TCC）对截图的 OCR
完整读出 Orca 界面（"Snapmaker Orca File Edit View…"、标题 "probe"、Process
(368,689) 与 A2 的 AX 地图逐像素吻合）→ 按任务书判据"拿到非空图=授权已给"，
继续壁环数目标。Worker/探针统一封装：捕获=跑 screencapture 8s 后杀掉、读
`.name.png`；OCR=`/usr/bin/swift ocr.swift`（入库 `runner/macos/ocr.swift`，
crop 坐标已修为裁剪图尺寸+偏移回全局）。

## 解锁路径（任务书路线 a/b 的实际走法）

- A3 复核：扁平页 48 行 44 键中**无 wall_loops**（总控提示的"AXHelp 收过
  wall_loops"不成立——A2 已用 3MF 578 键对照证明 wall_loops 只在参数树页），
  路线 a（扁平页滚动）死路，走路线 b。
- 路线 b 的关键修正：OCR 读出 y~767 自绘页带为五页签
  Quality/Strength/Support/Multimaterial/Others——**A2 所称"outline 页"就是
  Strength 页**。probe15 实证：OCR 点击 Strength 页签后，"• Walls" 区段与
  **"Wall loops" 行免滚动直接可见**（硬虚拟化只影响 AX 暴露，不影响渲染），
  值 token "=2" 在 (608,833) 同行可读。
- probe16 实证编辑机制：点击值格（token 左端，避 spinner 箭头）→ 行编辑器
  **物化为真 AXTextField**（AXHelp 带 `parameter name: wall_loops`）→ 键入 3 后
  AX 读回 `3`。此后复用 panel2 已证的 AXFocused+AXValue+AXConfirm 通道。

## 判据链与两次 run

Worker walls 路径重写（`runner/macos/project_copy.py`）：`open_tab("Strength")`
（03f21d11 的失败点，AX 无候选）→ OCR 定位页签坐标点击；三相位 wall 读回改为
OCR 读值（baseline/reopen）与物化编辑器 AX 读回（edit）；其余（层高双字段核对、
菜单保存、切片 receipt、独立重开、进程清理）不动。宿主判据不变项：3MF 差分+
三相位读回 `2/3/3`+两侧 68 层+gcode 回显 `wall_loops=3`+挤出 XY 移动对比。

- **run `ffe0c6e4`（NON_GREEN，保留）**：GUI 全链首次走通，卡在宿主
  `inspect_preserved_settings`：2.4.1 保存时把 2.3.6 夹具做**保存期架构迁移**
  （version 升级、新增 24 键、标量→向量、预设改名、机器模板 gcode 刷新），
  `pilot_config_unknown_addition`。此为 Windows 轨道 oracle 首次在 Mac 2.4.1
  保存上曝光（layer 目标走的是另一 oracle `inspect_project`，未触及）。
- **对照实验（probe17，`control_save4_a5`）**：净零往返（2→3→2）会使工程回
  干净态、Save 灰死（三轮迭代留痕），故对照改为**异键编辑**：扁平页
  initial_layer_print_height 0.4→0.44（纯 AX）后保存。对照噪声与 walls run
  **逐键同值**（added 24/24 一致、changed 56 键同值、唯一互异=各自编辑键、
  manifest 各记各账）→ 迁移噪声=编辑无关，实证而非断言。
- **判据升级（`verify_walls_differential`）**：对照基线入库
  （`runner/macos/walls_control.3mf`+`walls_control.json`，锁定 SUT 身份；构建
  变更自动拒绝并要求重采）。逐键规则：judged 保存差异必须 (a) wall_loops 2→3、
  (b) manifest 恰好增记 wall_loops、或 (c) 与对照**同键同值**。不做任何"洗白
  式"键剔除——只接受对照实验证过的差异。
- **run `306d3efe`（SHADOW）**：三相位独立进程 25404/25754/26039；wall 读回
  2/3/3；两侧切片 68 层（open_process_plate receipt）；gcode 回显
  `wall_loops=['3']`；挤出 XY 移动 1907→2154；geometry_unchanged；差分判据
  通过；cleanup_verified。

## 纪律与预算

后台 Aqua 会话全程未触碰前台 coil；每轮 LaunchAgent bootout 验证、Orca 清零。
GUI 累计约 25 分钟（红线 ≤30，含对照三轮迭代），红线"屏录失败不重试超过 2 次"
遵守（probe14 恰两次）。无密钥、无上游源码修改。

## 复跑

```bash
.venv/bin/python -B runner/macos_project_copy.py coilwin@localhost \
  --identity ~/.ssh/orca_bb_local --known-hosts ~/.ssh/orca_bb_known_hosts \
  --candidate <label> --goal walls
```

探针：`.venv/bin/python -B tools/mac_panel_probe.py panel_probe14.py <tag>`（14=屏录
自检、15=Strength OCR 寻址、16=编辑机制、17=对照保存）。OCR 单测：
`swift tools/ocr_probe.swift <png> [x y w h]`。

## 推送状态

与前轮相同：本机无 GitHub 推送凭据，提交落本地 `codex/mac-author`，push 待凭据。
