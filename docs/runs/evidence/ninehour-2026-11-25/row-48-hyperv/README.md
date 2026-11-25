# 飞书 #48 官方耗材色盘的模态和头部布局

飞书记录 `recvuCvWgT6IkZ` 的前置条件是已选择官方耗材。用例以 `mixed_filament_test.3mf` 第 2 槽的 Snapmaker PLA Silk 启动。该槽位保存的两种颜色 `#ECED17` 和 `#44ADE5` 对应官方色库的 Mint Lemonade、SKU `34205`。2026-11-25 只读复核确认飞书状态为「已自动化」。

| 飞书预期 | 判据 |
| --- | --- |
| 点击耗材色块弹出弹窗 | 定位第 2 槽编号色块，点击后读回同一 Orca 进程中带有 `Official Filaments` 标记的弹窗。 |
| 背景区域不可操作 | 请求将键盘焦点移到第 1 槽编号色块，读取 GUI 线程的实际活动窗和焦点。弹窗打开时，主窗保持禁用，焦点须留在弹窗树中。另在弹窗外的同一背景色块位置尝试真实鼠标交互，并读取光标、命中窗口、预设值和 Orca 窗口集合。取消后，主窗恢复启用，同一色块须获得键盘焦点并可打开原生色盘、读回 RGB。 |
| 第一行显示颜色卡片、颜色名称及 SKU | 读取网格上方可见标签 `Mint Lemonade` 和 `sku 34205`，定向截取弹窗并检查标签左侧头部区域的两种官方色卡像素。 |

头部判据的 5 项离线对照和窗口坐标裁剪映射已通过。正确的双配色和标签通过，缺 SKU、仅有底色、缺一种配色、SKU 出现在网格下方均被拒绝。

## Hyper-V 实跑

领取时间为 2026-11-25 13:17:31 +08:00。以下场景均由 `runner/hv_go.ps1` 在 `win11-test` 的 `test` 交互会话中启动，经 `runner/hv_harvest.ps1` 回收 JUnit 与日志。客机 Orca 文件和产品版本均为 2.4.0，执行文件 SHA-256 为 `5C48644D7DA18B50636CEEEE4EF9FD2EAF6D4E8AC05BD88752F40E3717FC47BF`。

| 提交 | 派发及完成时间（+08:00） | 结果 | 证据 |
| --- | --- | --- | --- |
| `53e58c34` | 13:27:31 → 13:28:43，72.35 秒 | RED。官方弹窗打开并读到名称和 SKU。弹窗可见且主窗口保持禁用。真实点击后旧判据的前景检查失败，桌面裁剪中的两种色卡颜色占比均为零。 | [日志](53e58c34-case48.log) · [收据](53e58c34-receipt.json) · [JUnit](53e58c34-junit.xml) |
| `f6f47018` | 13:32:50 → 13:34:07，77.40 秒 | 候选版本报告 GREEN。主窗点击前后保持禁用，弹窗客户区截取的两种官方色各占头部采样区的 33%。客机桌面命中的窗口句柄与编号色块不同，取消后的正对照经 Orca 窗口树定向点击打开原生色盘并读回 RGB `(217, 166, 58)`。 | [日志](f6f47018-case48.log) · [收据](f6f47018-receipt.json) · [JUnit](f6f47018-junit.xml) |
| `f6f47018` 候选复跑 | 13:34:11 → 13:35:27，76.51 秒 | 候选版本报告 GREEN。复现该版本首次运行的窗口状态、头部颜色读数和正对照。 | [日志](f6f47018-rerun-case48.log) · [收据](f6f47018-rerun-receipt.json) · [JUnit](f6f47018-rerun-junit.xml) |
| `b5deb4ff` | 13:39:13 → 13:40:20，67.27 秒 | RED。主窗已进入前景，桌面命中仍返回其他窗口句柄。严格鼠标路线在打开色盘之前终止。 | [日志](b5deb4ff-case48.log) · [收据](b5deb4ff-receipt.json) · [JUnit](b5deb4ff-junit.xml) |
| `00235a01` | 13:46:43 → 13:48:01，77.74 秒 | RED。客机报告鼠标背景位置命中 `Shell_SystemDim`。点击后前台句柄为空，尝试恢复弹窗前景失败，该轮未取得模态期间焦点读数。取消后同一背景色块获得焦点并打开原生色盘，RGB 和头部两色读数通过。 | [日志](00235a01-case48.log) · [收据](00235a01-receipt.json) · [JUnit](00235a01-junit.xml) |
| `d5adec56` | 13:49:27 → 13:50:43，76.74 秒 | RED。将焦点实验提前后，直接调用窗口激活 API 改变了活动窗口。背景色块只有在取消后获得焦点。头部和取消后的正对照通过。 | [日志](d5adec56-case48.log) · [收据](d5adec56-receipt.json) · [JUnit](d5adec56-junit.xml) |
| `7101f2c9` | 13:52:39 → 13:53:55，76.11 秒 | **GREEN**。模态时同一槽位的 `SetFocus` 返回 0、Win32 错误 87，活动窗和焦点保持在原弹窗树中。取消后对同一色块调用 `SetFocus` 成功，并打开原生色盘读到 RGB `(217, 166, 58)`。两种官方色像素各占头部采样区的 33%。 | [日志](7101f2c9-case48.log) · [收据](7101f2c9-receipt.json) · [JUnit](7101f2c9-junit.xml) |
| `7101f2c9` 独立复跑 | 13:54:00 → 13:55:16，76.26 秒 | **GREEN**。独立 Orca 进程复现窗口焦点、两种颜色像素占比和取消后的原生色盘 RGB。 | [日志](7101f2c9-rerun-case48.log) · [收据](7101f2c9-rerun-receipt.json) · [JUnit](7101f2c9-rerun-junit.xml) |

从领取到首次完整 GREEN 用时 36 分 23.41 秒。此前有 4 次 RED，另有两次候选版本的脚本 GREEN。客机的 `Shell_SystemDim` 覆盖层接收了色块坐标处的桌面命中。鼠标输入和窗口命中均保留在日志中。背景不可操作的结论依据 Win32 的原生焦点请求与取消后的同控件正对照。该正对照通过 Orca 窗口树点击已经取得焦点的背景色块，读取了原生色盘的原 RGB。

## 复跑入口

将已确认空闲的 `win11-test` 同步至待测提交。在宿主有 Hyper-V 权限的 PowerShell 中运行以下命令。项目既有 v3 检出路径通过 `runner/guest_v3_bundle_sync.ps1 -Head <提交完整 SHA>` 同步。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m8x_48_modal_color_header -NoSync
# 等待 suite 回到 Ready 且 regress_summary.txt 有本轮结果
& .\runner\hv_harvest.ps1
```
