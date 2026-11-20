# 跨平台层高候选试跑

本轮请求标签为 `layer-pilot-20261120-01`。输入是仓库的 `fixtures/agent_layer_cube.3mf`，SHA-256 为 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`。目标是保留 0.40 mm 首层，把常规层高从 0.40 改为 0.24 mm，再通过独立重开的工程和实际模型挤出验证 68 → 112 层。候选标签关联同次请求，实际构建由各机的产品版本、二进制身份记录。

## Mac 正常与错误输入

| 运行 ID | GUI 实际改入 | 原始 → 重开后模型挤出层数 | 判定 |
| --- | ---: | ---: | --- |
| `0f805ab9b1604fde874aadaedd6d0ce8` | 0.24 mm | 68 → 112 | 首轮 SHADOW |
| `a209bdc55cf74a9696ece3756ce8764b` | 0.32 mm | 68 → 84 | NON_GREEN，首个独立业务断言在 `verify.saved_project` 拒绝已保存的层高 |
| `a86090fc29b54c08859c82825d213fdc` | 0.24 mm | 68 → 112 | 收紧工程摘要绑定后复跑 SHADOW，纳入本轮汇总 |

Mac 上实际运行的 Orca 为 2.4.1，主程序 SHA-256 为 `a994ff90ca373871f72da103f25d17db0ae6c235c12c8331835521c460fffdcd`。正常样本中，首层均为 0.40 mm，末层从 27.20 mm 变为 27.04 mm。每份临时盘 G-code 通过进程打开文件、inode、窗口、工程摘要和切片完成状态绑定。磁盘上已冻结的 3MF 与新进程重开的参数也符合预期。后台运行期间日常账号一直在前台。当前切片按钮定位只验证了 1200 × 800 的 Prepare 窗口，遇到其他布局会停止。原生另存为和 GUI 导出仍待前台验证。[Mac 后台工程保存与原生面板记录](macos-background-layer-2026-11-20.md)

错误样本在 GUI 中实际输入 0.32 mm，独立工程检查仍以 0.24 mm 为目标，返回 `project_layer_config`。重开界面读到 0.32 / 0.40 mm。按该观测值复核导回的切片可得到 84 层和 26.96 mm 的末层 Z；此诊断结果单独保留。

从宿主运行以下命令，将 `TEST_USER@MAC_HOST` 替换为已配置的测试目标。第二行按设计返回非零，报告工具另行核实是否命中了预定失败点。

```powershell
python -B runner/macos_project_copy.py TEST_USER@MAC_HOST --candidate layer-pilot-20261120-01
python -B runner/macos_project_copy.py TEST_USER@MAC_HOST --candidate layer-pilot-20261120-01 --wrong-layer-control
```

各轮原始产物位于 `artifacts/mac_project_copy/<run_id>/`。其中 `baseline.gcode` 和 `edited.gcode` 是 GUI 切片后当前盘的临时产物，`result.json` 包含 GUI 步骤、进程与构建身份、回收摘要、独立检查及清理结果。

## Windows 首次调度与报告

Windows 使用确定性 UIA 脚本。编辑组为 `uia_replay_layer`，基线组为 `uia_replay_save`，后者保留原参数另存副本并独立重开。合并两组时分别保留运行 ID，并核对请求标签、安装构建、原始夹具和 GUI 导出的文件。

本轮首次在 `win11-test` 调度编辑组，ID 为 `e74954de124c44a0b97928c847893799`。启动前取得安装版本 2.4.0、主程序 SHA-256 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf` 和匹配的夹具摘要。现有客机识别在 `guest.host_guard` 阶段中止，Orca 未启动，基线组未执行。现场检查发现该 VM 的 Hyper-V 键值对交换处于关闭状态，客机服务已停止，客机标识注册表项在两个视图中均不存在。原始启动日志、预检和阻塞收据位于 `artifacts/windows_mcp_harvest/e74954de124c44a0b97928c847893799/`。

首次汇总位于 `artifacts/gui_build_reports/layer-pilot-20261120-01/first-attempt.json`。Windows 为 BLOCKED、Mac 为 SHADOW、错误样本为 EXPECTED_FAILURE。Windows 2.4.0 与 Mac 2.4.1 记录为不同版本。报告可用 `--historical-windows` 引入只读历史参照，历史 68/112 层不计入本轮 Windows 实测。

随后使用新入口单独调度 Windows 基线组。定稿后的运行 ID 为 `030509effe284014b2188b2eada65fe5`。该入口在启动 Orca 前识别到同一客机识别故障，留下独立的 `binding.json` 和 `attempt.json`。本轮两个 Windows 场景都已尝试调度，均未取得 GUI 切片数据。

按当前安排，先配置 Windows 测试机的 SSH，Hyper-V 键值对交换保持关闭。取得 SSH 目标后，先确认目标机器、客机识别结果和已登录的交互桌面，再排两条 GUI 用例。

## 重跑与汇总

在可管理 `win11-test` 的 PowerShell 会话中，从仓库根目录运行以下入口。它通过既有 `hv_go.ps1 -NoSync` 调度，再由 `hv_harvest.ps1` 回收，两次运行都记录客机检出的提交和实际安装包摘要。可用 `-GuestCheckout` 指向已部署的客机目录。新一轮使用新的候选标签，并给两端传入同一标签。

```powershell
.\runner\windows_layer_evidence.ps1 -CandidateId layer-pilot-20261120-01 -Phase Both
```

以下命令从本轮冻结的原始文件重建汇总。对正常完成的 Windows 场景，传对应目录的 `result.json`。遇到启动阻塞时传 `attempt.json`。输出文件使用新路径，保留旧报告。

```powershell
python -B tools/gui_build_report.py --candidate layer-pilot-20261120-01 `
  --macos artifacts/mac_project_copy/a86090fc29b54c08859c82825d213fdc/result.json `
  --negative-control artifacts/mac_project_copy/a209bdc55cf74a9696ece3756ce8764b/result.json `
  --windows artifacts/windows_mcp_harvest/e74954de124c44a0b97928c847893799/attempt.json `
  --windows-baseline artifacts/windows_mcp_harvest/030509effe284014b2188b2eada65fe5/attempt.json `
  --historical-windows artifacts/v3/guest-layer-accepted-6bfe7cb6c9d54994a0106247bab08294/result.json `
  --output artifacts/gui_build_reports/layer-pilot-20261120-01/rebuilt.json
```

本轮定稿汇总为 `artifacts/gui_build_reports/layer-pilot-20261120-01/candidate-report.json`。整体为 `NON_GREEN`，报告命令相应返回退出码 1。Linux 暂缺图形执行机，尚未开始实测。接入候选构建、夜间回归和发布前专项的顺序见[跨平台 GUI 回归安排](../V3_PLAN.md#9-跨平台-gui-回归安排)。
