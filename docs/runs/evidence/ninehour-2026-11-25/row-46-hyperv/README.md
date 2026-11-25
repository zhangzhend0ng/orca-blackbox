# 飞书 #46 更改颜色后点击确定颜色生效

飞书记录 `recvuCvWgTEtIi`。原用例允许使用任意耗材，要求在色盘选另一种颜色，点击确定关闭色盘，再查看耗材当前颜色。独立用例 `m8x_46_color_confirm` 使用 `mixed_filament_test.3mf` 的第 1 槽 Generic PETG 和 Windows 原生色盘。这条飞书记录已标为「已自动化」。

离线运行一组正向对照和八组负向对照。各负向对照分别验证 RGB 未变、HSL 未变、起始 RGB 数值非法、未点击确定、旧色盘仍可见、未能重开色盘、复用了旧窗口句柄和重开读到原色时，均会拒绝通过。

## Hyper-V 实跑

2026-11-25 在 `win11-test` 由 `test` 的交互会话运行 Orca 2.4.0。两轮使用同一个提交 `53e58c34e4b8ae9b2dc8484954ba44631a7036c4`，独立派发，分别启动 Orca PID `4484` 和 `4032`。场景日志与客机 SHA-256 一致。

| 轮次 | 派发（北京时间） | 场景完成（北京时间） | 场景墙钟 | 结论 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 首轮 | 13:21:48.234 | 13:23:13.659 | 85.42 秒 | GREEN | [日志](53e58c34-run1-case.log) · [收据](53e58c34-run1-receipt.json) · [JUnit](53e58c34-run1-junit.xml) |
| 独立复跑 | 13:24:15.669 | 13:25:39.880 | 84.21 秒 | GREEN | [日志](53e58c34-run2-case.log) · [收据](53e58c34-run2-receipt.json) · [JUnit](53e58c34-run2-junit.xml) |

13:17:23 领取，约 5 分 51 秒达到首次 GREEN，两轮 GUI 失败 0 次。首轮的收集脚本转换时间戳时出错，随后从已完成的同一轮补收，核对了派发时间、客机提交和日志哈希。

| 飞书预期 | 两轮客机读数 |
| --- | --- |
| 色盘中的颜色选择已更新 | 第 1 槽的色盘内输入新的 Red 通道值，RGB 从 `(217, 166, 58)` 变为 `(0, 166, 58)`，色盘计算的 HSL 从 `(27, 162, 129)` 变为 `(94, 240, 78)`。 |
| 色盘关闭 | 点击原生色盘的 OK 后，独立确认该窗口不可见，`ok_clicked=True`、`closed=True`。 |
| 耗材颜色已更改为新选择的颜色 | 再点第 1 槽色块，新窗口句柄与旧色盘不同，从新色盘读回 `(0, 166, 58)`。 |

## 复跑入口

确认 `win11-test` 空闲，在具备 Hyper-V 权限的 PowerShell 中同步待测提交，再启动独立单例。使用项目既有 v3 检出时，先执行 `runner/guest_v3_bundle_sync.ps1 -Head <完整 SHA>`。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m8x_46_color_confirm -NoSync
# 等 suite 回到 Ready 且 regress_summary.txt 写入本轮结果后收割
& .\runner\hv_harvest.ps1
```
