# 原生 Codex + Windows-MCP 客机试点

日期：2026-11-17。目标：验证现成 Agent 能否直接控制 Orca，替代旧的“每步启动 CLI、只输出动作 JSON”循环。

## 结论与范围

**可用于本项目的专用客机业务试点。** 成功 run `9c95fb4b95bc447294534fbe77b5e70a`，冻结源码 `40ecf33`。原生 Codex 的 6 次 MCP 调用全部完成，独立 observer 确认 Prepare→Preview→Prepare；宿主/客机 Job 均 ActiveProcesses=0、forced=false，Orca 自然关闭。仅为 COMPATIBILITY_SHADOW，release_eligible=false。

**配置限制：** 默认桌面控制锁模式返回 CONTROL_UNAVAILABLE，未定位内部 hook/recovery 的具体原因。成功轮采用原版 CLI 的 `--no-control`，关闭物理接管监控/指示，仅可用于无人共享的专用测试客机。不能把该结果推广为共享宿主桌面默认可用。

Windows-MCP 是 Windows 桌面控制工具，不是完整测试平台。本项目用现成 Codex 作为 Agent；测试目标、fixture 和独立 oracle 仍由 harness 提供。不能把页签验证扩大为 87 条业务覆盖或长期稳定性结论。

## 结构

业务目标与约束 → 一次 codex exec 原生工具循环 → 原版 Windows-MCP → win11-test 的 Orca。

- **Codex**：自行看截图/UIA、选工具与坐标、根据返回结果继续操作。没有业务动作 JSON schema、没有预设点击坐标、没有手写 next-action 循环。
- **Windows-MCP 0.8.9**：提供 Snapshot、Screenshot、Click、Wait、ControlStatus；本轮只开放这五项，使用原版包，不修改其源码。Python 3.14.10 便携运行时位于客机 `C:\coil\tools\windows-mcp-0.8.9`，依赖锁与 CycloneDX SBOM 随仓库保存。
- **harness**：只负责隔离 profile/fixture、通过 hv_go 启动、预算与 owned Job 清理、独立双帧页签观察、证据回收。业务内容继续由已有 3MF/G-code 检查器判定，Agent 的完成文字不算通过。
- **传输桥**：客机没有可用 NIC，宿主 stdio → PS Direct 数据转发 → 客机 loopback HTTP `/mcp`。GUI 真正在 INTERACTIVE server 执行。该桥只转发协议，不规划、不生成业务步骤。未来有受控直连网络时可移除它。

## 本轮如何验证

只给“进入 Preview、确认后返回 Prepare”的目标与操作约束。没有给 Agent 坐标。独立 observer 连续两帧确认每次页签状态；保留窗口 PID/HWND、PNG/BMP 哈希、原生 MCP events、server 日志及双端 Job receipt。

| 轮次 / run 前缀 | 结果 | 已验证或失败部位 |
|---|---|---|
| 1 / 7078bc61 | NON_GREEN | 原版服务启动；HTTP redirect 丢认证头，initialize 401；无输入 |
| 2 / 42203831 | NON_GREEN | initialize/tools/list/Snapshot 服务返回成功，桥 UTF-8/SSE 解码错误；无输入 |
| 3 / 50d3d4d3 | NON_GREEN | 原生观察成功，CLI 默认审批阻止 Click；无输入 |
| 4 / fabe9936 | NON_GREEN | 接线和 Click 审批正常，原版桌面控制锁拒绝输入 |
| 5 / 9c95fb4b | COMPATIBILITY_SHADOW | 专用客机 --no-control；6 次原生工具成功，独立页签环和双端清理通过 |

前四轮完整保留，不将一次修复后的成功当作稳定性通过率。13 项专项纯测试及全仓纯单测通过：734 passed，1 skipped；不是 734 条真实 GUI 用例。

完整失败与修复记录见 `docs/reviews/software_testing-2026-11-17-windows-mcp.md`。CLI exit 0、worker exit 0 都不单独代表目标通过。

## 复跑入口

在宿主仓库及客机 checkout 同步到同一冻结提交、核对两端 SHA/clean HEAD、依赖 runtime 已离线安装后，生成一个全新 32-hex run ID。以下 `-NoSync` 仅用于已完成上述校验的离线同步场景；管理员通道使用：

```powershell
$env:ORCA_BB_GUEST_SANDBOX='C:\coil\orca-blackbox-v3-r1'
$probeRun=[guid]::NewGuid().ToString('N')
& runner\hv_go.ps1 -NoSync -WindowsMcpProbe -ProbeRunId $probeRun
python -B tools\windows_mcp_codex_probe.py --run-id $probeRun
& runner\hv_harvest.ps1 -WindowsMcpRunId $probeRun
```

客机离线 git 同步必须先验证两端 SHA/clean HEAD 后才使用 `-NoSync`。长任务经隐藏 detached relay 启动，禁止将 GUI worker 改为 PS Direct 直接运行。

Codex 配置仅作用于该子进程：隔离 MCP server、Click 的工具级 approve、禁 shell/apps/plugins/browser、只读 sandbox；不修改全局配置。服务器仅监听客机 loopback，每轮随机认证 token 不回传模型，PostHog 关闭。

宿主证据：`artifacts/windows_mcp_host/<run-id>` 与 `artifacts/v3_host/<run-id>`；回收证据：`artifacts/windows_mcp_harvest/<run-id>`。artifact 被 gitignore；仓库保留版本、摘要与结论。结果不进入 legacy GREEN/JUnit 或飞书 GREEN 基线。

## 接入前需补的业务验证

下一轮使用同一原生 Agent 做“修改层高 → 切片 → 导出”的完整目标测试，以实际 G-code 层高/层数判定；再测试保存工程与独立 profile 重开。需要时开放原版 Type/Shortcut，仍不引入手写业务动作工具或自建 agent。

稳定性、错误恢复、预算/耗时、原生对话框和跨版本迁移须分别采样。当前 PS Direct 桥仅支持本轮需要的 stateless MCP 请求，非完整通用 MCP 网络代理。

官方说明：[Windows-MCP](https://github.com/CursorTouch/Windows-MCP)、[Codex MCP 与工具级配置](https://learn.chatgpt.com/docs/extend/mcp)。依赖中包含 GPL 项，完整 runtime 不作为商业产品组件分发。
