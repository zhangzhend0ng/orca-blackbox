# 飞书 #140 正常关闭 Orca 且无残留进程

飞书记录 `recvuCvXUuFxXT`。用例要求 Orca 位于准备页，点击窗口右上角关闭按钮，随后检查 Windows 的全机进程列表。飞书现行状态为「已自动化」。

`win11-test` 的 `test` 交互会话在独立种子配置中启动 Orca 2.4.0。启动前通过 CIM Win32_Process 读取全机列表，未发现 Orca。启动后 Prepare 模板得分为 `1.000`，全机仅有本轮启动的 Orca 实例，日志同时记录进程创建时间、会话 ID、可执行文件路径和配置路径。

两轮都从自绘工具栏画面定位右上角 X，双对角笔画读值 `6/6`，屏幕点均为 `(1901, 14)`，并核实目标 HWND 属于 Orca 自绘工具栏。把指针放到该点后向工具栏投递鼠标按下和抬起。进程在约 0.6 秒内退出，窗口销毁，退出码均为 `0`。两轮在任何失败清理以前分别做两次独立的全机进程枚举，均无 Orca 映像或已记录的进程树成员。进程树包含 WebView2 与 crashpad。进程关联用 PID 和创建时间核对。

| 提交 | 派发 → 完成（北京时间） | 场景墙钟 | Orca PID | 结果与证据 |
| --- | --- | ---: | ---: | --- |
| `1b98616f` | 14:06:56.543 → 14:08:05.144 | 68.602 秒 | 11548 | GREEN · [日志](1b98616f-run1-case.log) · [回执](1b98616f-run1-receipt.json) · [JUnit](1b98616f-run1-junit.xml) |
| `1b98616f` 独立复跑 | 14:08:12.381 → 14:09:20.522 | 68.141 秒 | 10348 | GREEN · [日志](1b98616f-run2-case.log) · [回执](1b98616f-run2-receipt.json) · [JUnit](1b98616f-run2-junit.xml) |

14:03:27 领取，4 分 38.144 秒后取得首次 GREEN。原判 RED 0 次。[客机构建回执](../build.json)

## 独立复跑

在有 Hyper-V 权限的宿主 PowerShell 中，将已确认空闲的客机先用 `runner/guest_v3_bundle_sync.ps1 -Head <完整提交>` 同步到待测版本。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_140_close_without_residue -NoSync
# 等待 suite 回到 Ready 且出现本轮摘要
& .\runner\hv_harvest.ps1
```
