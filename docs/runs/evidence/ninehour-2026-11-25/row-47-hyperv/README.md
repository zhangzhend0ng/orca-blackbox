# 飞书 #47 选色后取消

飞书记录 `recvuCvWgTE4ps`。原用例要求在任意耗材的色盘里选另一色，点击取消关闭色盘，再查看原耗材的登记色。独立场景 `m8x_47_color_cancel` 使用 `mixed_filament_test.3mf` 的第 1 槽 Generic PETG。

2026-11-25 只读复核表 `tblKjIVV8KA53kUQ` 此记录的自动化状态为「已自动化」，无需重复写入状态。

判据记录选择前、选色后和取消后重开读到的颜色。只有读出另一色、找到并点击取消、观察到旧色盘关闭，且重开同一槽时读回原色，才会通过。官方色盘的单边 SKU 缺失、无色名、原生色盘无 RGB 数字、只改动 RGB 文本且 HSL 无变化等情形均拒绝。14 项离线正负对照已过。

## Hyper-V 实跑

2026-11-25 在 `win11-test` 以 `test` 的交互会话跑 Orca 2.4.0。先检查计划任务与 Orca 进程均空闲，通过校验 Git bundle 同步客机提交，再经 `runner/hv_go.ps1` 派发。`runner/hv_harvest.ps1` 取回批次总结及 JUnit，逐批日志通过 SHA-256 核对。

| 验证提交 | 场景 | 客机结果 | 证据 |
| --- | --- | --- | --- |
| `ed922725` | `m8b_official_color` | RED。夹具载入，旧合并场景强制换预设后未打开初始色盘，未执行 #47。 | [日志](ed922725-m8b.log) · [收据](ed922725-receipt.json) |
| `847bc647` | `m8x_47_color_cancel` | RED。独立场景的带模型准备页载入，真实点击未找到目标色盘。 | [日志](847bc647-case47.log) · [收据](847bc647-receipt.json) |
| `80c4ad97` | `m8x_47_color_cancel` | RED。尝试前置 Orca 后，桌面命中测试显示第 1 槽色块仍被遮挡。 | [日志](80c4ad97-case47.log) · [收据](80c4ad97-receipt.json) |
| `93f350f2` | `m8x_47_color_cancel` | RED。通过 Orca 窗口树打开第 1 槽原生色盘并读到 RGB `(217, 166, 58)`。原选色和取消点击没有使色盘选择变化或关闭。 | [日志](93f350f2-case47.log) · [收据](93f350f2-receipt.json) |
| `d0e429ed` | `m8x_47_color_cancel` | RED。取消点击关闭色盘，同一槽重开读回 `(217, 166, 58)`。色盘内的色块输入未改变 RGB。 | [日志](d0e429ed-case47.log) · [收据](d0e429ed-receipt.json) |
| `a91d2946` | `m8x_47_color_cancel` | **GREEN**。2026-11-25 12:58:13 +08:00 派发，12:59:30 客机完成，PASS=1、FAIL=0。 | [日志](a91d2946-case47.log) · [收据](a91d2946-receipt.json) · [JUnit](a91d2946-junit.xml) |
| `a91d2946` 复跑 | `m8x_47_color_cancel` | **GREEN**。13:01:21 +08:00 独立派发，13:02:37 客机完成，PASS=1、FAIL=0。RGB、HSL 和关闭、重开读回结果与上一轮一致。 | [日志](a91d2946-rerun-case47.log) · [收据](a91d2946-rerun-receipt.json) · [JUnit](a91d2946-rerun-junit.xml) |

## #47 原行对照

| 飞书预期 | 客机实证 |
| --- | --- |
| 色盘中的颜色选择已更新 | 第 1 槽 Generic PETG 的原生色盘内键入 Red 后，RGB 从 `(217, 166, 58)` 变为 `(0, 166, 58)`。色盘计算出的 HSL 从 `(27, 162, 129)` 变为 `(94, 240, 78)`。 |
| 色盘关闭 | 点击该色盘的 Cancel 按钮，观察到旧窗口不可见，`cancel_clicked=True`、`closed=True`。 |
| 耗材保持原来登记的颜色 | 重新点击同一槽的编号色块打开新的色盘，读回 RGB `(217, 166, 58)`。 |

## 复跑入口

将已确认空闲的 `win11-test` 同步至待测提交后，在有 Hyper-V 权限的 PowerShell 中执行以下命令。使用项目既有 v3 检出路径时，先通过 `runner/guest_v3_bundle_sync.ps1 -Head <提交完整 SHA>` 同步该路径。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m8x_47_color_cancel -NoSync
# suite 回到 Ready 且 regress_summary.txt 有本轮结果后收割
& .\runner\hv_harvest.ps1
```
