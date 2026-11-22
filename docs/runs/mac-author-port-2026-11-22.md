# macOS 轨道 macos_project_copy 移植首跑（mac-author）

本轮请求标签 `mac-author-20261122-01`，产出分支 `codex/mac-author`（基于 `codex/glm-flash-expansion-20261121-0217` @ 7d46381）。执行机为 Mac mini coilwin@172.18.6.213（macOS 26.6.2 arm64），测试登录 `coilwin`(502) 在自己的后台 Aqua 会话运行 GUI，日常账号 `coil`(501) 全程占用物理 console 前台。SUT：Snapmaker Orca 2.4.1，`/Applications/Snapmaker Orca.app`（只读），主程序 SHA-256 `a994ff90ca373871f72da103f25d17db0ae6c235c12c8331835521c460fffdcd`，与 2026-11-20 实录一致。夹具 `fixtures/agent_layer_cube.3mf`（SHA-256 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`）。

预检（`artifacts/mac_probes/2026-11-22/probe2.json`）：Xcode 签名 Python.app 在测试登录内 `AXIsProcessTrusted=true`、`CGPreflightPostEventAccess=true`、`check_session` 通过；`screencapture -l<windowid>` 超时，**无屏幕录制权限**（不绕过）。宿主侧在本机以专用密钥 SSH localhost（`~/.ssh/orca_bb_local` + `~/.ssh/orca_bb_known_hosts`）驱动既有仓库入口，未改传输协议。

## 实现改动（本分支）

- `runner/macos_project_copy.py`（宿主入口）：新增 `--goal {layer,walls,pan}` 与 `--pan-presses`；按目标打包 goal/copy-name/pan-presses；walls 判据 = 3MF `project_settings.config` 独立核对（`inspect_preserved_settings` 允许且仅允许 `wall_loops 2→3`）+ 三相位 AX 读回 `2/3/3` + 两侧切片层数均 68 + gcode `wall_loops` 回显；pan 判据 = 直接复用 Windows 侧 `pilot_transform.verify_translation(axis="x", distance=10)`（build item transform index9 精确 +10.0、Y/Z 不变、网格一致、68 层、挤出 XY 落在平移后包围盒）。负对照逻辑保持 layer 目标专用。
- `runner/macos/project_copy.py`（worker）：按 goal 分发编辑相位——layer 走原层高链；walls 新增 `open_tab`/`wall_field`/`edit_walls_and_save`（Strength 页首字段 2→3 + 未保存标记 + Save Project）；pan 新增 `pan_and_save`（画布中心点击 + N 次 Right 键 + 标记 + 保存）。重开相位按 goal 读回（walls：Strength 首字段=3；pan：层高字段保持 0.4/0.4）。三相位进程身份、清理与收尾纪律不变。
- `runner/macos/accessibility.py`：`click_slice` 重构为通用 `click_point(pid,root,window,title,x,depth)`（1200×800 布局约束不变）；新增 `post_key`（CGEventCreateKeyboardEvent 直发目标进程）。

## 逐条目标结果

| 目标 | 运行 ID | 结果 | 首个失败阶段 |
| --- | --- | --- | --- |
| 1a 层高 0.40→0.24 正例 | `0a24557a0c5f49809b14ad6a52d47c5e` | **SHADOW** | — |
| 1b 层高 0.32 负对照 | `b715f843c4a447eb8f8abf5a50e6c22e` | NON_GREEN（按合同预期拒绝） | `verify.saved_project` |
| 2 壁环数 2→3 | `03f21d119f5242a8809f329dc8047706` | NON_GREEN（UI 寻址缺口，非权限问题） | `baseline.wall` |
| 3 画布平移 X+10mm | `bc793ed0eb0349678cae67306e0b7524` | NON_GREEN（画布合成输入无效果） | `edit.pan_save` |

各轮原始产物在 `artifacts/mac_project_copy/<run_id>/`（本机，git 惯例不入库）；探针证据在 `artifacts/mac_probes/2026-11-22/`。

### 1a 层高正例（SHADOW）

三相位独立进程 PID 42621/42664/42692；编辑相位对具名副本 `layer-024-copy.3mf` 改入 0.24 并 Save Project，冻结后新进程重开读到 `['0.24','0.4']`。独立检查：原始盘 68 层/末层 Z 27.20/正挤出 XY 段 1,907 → 重开盘 112 层/27.04/2,882，与 Windows 侧 68→112 口径及 11-20 实录一致；工程检查器确认网格 8 顶点 12 三角形一致、两层高字段 0.24/0.40。原始夹具前后摘要不变，LaunchAgent 卸载与 Orca 进程清零均验证。

### 1b 负对照（NON_GREEN，预期失败点命中）

GUI 实际改入 0.32，worker 完成全链（重开界面如实读到 `['0.32','0.4']`），宿主独立工程检查以 0.24 为目标在 `verify.saved_project` 拒绝（`project_layer_config`）——与 11-20 实录的失败点相同，证明独立断言未被 GUI 输入污染。

### 2 壁环数（NON_GREEN：工艺面板对 AX 不可寻址）

worker 在 baseline 相位 `open_tab("Strength")` 即失败：`No Strength tab candidate in the process panel`。探针归因（`artifacts/mac_probes/2026-11-22/`）：

1. 简易模式工艺区只有两个层高 AXTextField；勾选 "Advanced" 复选框（真实 AXCheckBox，位于 Process 头行）后变为 **24 个字段的扁平常用参数列表**，无任何 AX 页签/AXTabButton，列表中不存在值为 `2` 的整数字段（wall_loops 不可见）。
2. 自绘控件 AXTitle/AXDescription 全空；静态文本 description 的暴露**跨启动非确定**（同脚本一次 10+ 条、重跑 0 条），不能作定位依据。
3. 面板 AXScrollBar 的下箭头 AXPress 18 次字段集纹丝不动；页头其余按钮（730,689)/(756,689) 点击无效；工艺下拉弹层为自绘（模态标志触发，但枚举只回 Apple 系统菜单项）。
4. 无屏幕录制权限（screencapture 超时），无视觉定位通道；亦无 OCR 依赖可用。

判据侧移植已完成待用：`inspect_preserved_settings` 的 `{"wall_loops": "3"}` 变更域（期望 2→3）本就是仓库预期合同，gcode `wall_loops` 回显与 68 层保持检查已接线。**后续可行路径**：给测试登录的签名 Python 授屏幕录制权限（需管理员在系统设置操作）、或接入 OCR、或等上游把工艺面板参数树暴露为可寻址 AX。

### 3 画布平移（NON_GREEN：后台会话画布合成输入无效）

worker 按设计完成画布中心点击（经窗口/PID/边界三重绑定的 `click_point`）+ 10 次 Right 键（CGEvent 直发进程）后，窗口标题未出现未保存标记 → `Missing unsaved marker`。探针（`final2.log`）：7 个画布坐标（490,420 至 540,470 覆盖立方体可能位置）× 点击+单键、以及 2 组"点击立方体+猜测 gizmo Move 图标"组合，**全部未产生任何工程状态变化**。对照：同一通道对 wx 工具栏（Slice plate 按钮）合成点击有效（1a/1b 两次切片证明），故缺口特定于 OpenGL/ImGui 画布对后台会话合成事件的消费，且无法在无视觉反馈下盲定位 gizmo。判据侧已就绪：`verify_translation(axis="x", distance=10)`（Windows `uia_hybrid_canvas`/`pilot_model_move_x` 同源口径）已接入宿主验证链。

## 纪律与预算

GUI 自动化全程在 coilwin 后台 Aqua 会话，物理前台（coil 的 console）未被触碰；会话前后 Orca 进程为零、临时 LaunchAgent 全部卸载（各 result.json `cleanup_verified=true`）。墙钟超出了 30 分钟接管预算（探针轮次较多），如实在此声明；后续应把探针并入带快照的单轮侦察作业。

## 复跑命令（本机）

```bash
.venv/bin/python -B runner/macos_project_copy.py coilwin@localhost \
  --identity ~/.ssh/orca_bb_local --known-hosts ~/.ssh/orca_bb_known_hosts \
  --candidate mac-author-20261122-01 --goal layer            # 1a；加 --wrong-layer-control 得 1b
# --goal walls / --goal pan [--pan-presses N] 为新目标（当前在此构建上按上表失败并留证）
```

## 推送状态

提交 `c18d0a5` 已落在本地分支 `codex/mac-author`（基于 7d46381）。本机无 GitHub 推送凭据（无 gh CLI、keychain 无 github.com 条目、无 GITHUB_TOKEN、无对 GitHub 的 SSH 公钥；匿名 HTTPS 仅能 fetch 公库），**push 阻塞**，如实记录。需凭据后 `git push origin codex/mac-author` 即可（无冲突：远端该分支仍为 7d46381）。
